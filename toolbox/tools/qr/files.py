"""教室QR用のアップロードファイル。メタは JSON、本体は隣に置く。"""
from __future__ import annotations

import re
import secrets
from datetime import timedelta
from pathlib import Path

from toolbox import config
from toolbox.storage import _lock, _read_json, _write_json, new_id, now_dt, now_iso

_MAGIC = {
    "pdf": (b"%PDF",),
    "pptx": (b"PK\x03\x04",),
    "docx": (b"PK\x03\x04",),
    "xlsx": (b"PK\x03\x04",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
}


class QrFileError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _dir() -> Path:
    config.ensure_dirs()
    return config.QR_FILES_DIR


def _meta_path(file_id: str) -> Path:
    return _dir() / f"{file_id}.json"


def _body_path(file_id: str, ext: str) -> Path:
    return _dir() / f"{file_id}.{ext}"


def _safe_id(file_id: str) -> str | None:
    if re.fullmatch(r"[0-9a-f]{12}", file_id or ""):
        return file_id
    return None


def _load_meta(path: Path) -> dict | None:
    data = _read_json(path, None)
    if not isinstance(data, dict) or not data.get("id"):
        return None
    return data


def _iter_metas() -> list[dict]:
    rows = []
    root = _dir()
    for path in root.glob("*.json"):
        if path.name.endswith(".tmp"):
            continue
        data = _load_meta(path)
        if data:
            rows.append(data)
    return rows


def _is_expired(row: dict, now=None) -> bool:
    from toolbox.storage import _parse_dt

    expires = _parse_dt(row.get("expires_at"))
    if expires is None:
        return True
    return expires <= (now or now_dt())


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _write_bytes(path: Path, data: bytes) -> None:
    config.ensure_dirs()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def magic_ok(ext: str, data: bytes) -> bool:
    signatures = _MAGIC.get(ext)
    if not signatures or not data:
        return False
    return any(data.startswith(sig) for sig in signatures)


def require_title(raw: str) -> str:
    title = (raw or "").strip()
    if not title:
        raise QrFileError("タイトルを入力してください。")
    if len(title) > 80:
        raise QrFileError("タイトルは80文字以内にしてください。")
    return title


def normalize_ttl(raw) -> int:
    try:
        days = int(raw)
    except (TypeError, ValueError):
        days = config.QR_FILE_TTL_DAYS_DEFAULT
    if days not in config.QR_FILE_TTL_DAYS_CHOICES:
        raise QrFileError("有効期限は1日、7日、30日から選んでください。")
    return days


def extension_of(filename: str) -> str:
    name = Path(filename or "").name
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in config.QR_FILE_ALLOWED_EXT:
        raise QrFileError("この種類のファイルはアップロードできません。PDF・PowerPoint・Word・Excel・画像のみです。")
    return ext


def purge_expired() -> int:
    now = now_dt()
    removed = 0
    with _lock:
        for row in _iter_metas():
            if not _is_expired(row, now):
                continue
            file_id = str(row.get("id") or "")
            ext = str(row.get("ext") or "")
            _unlink(_meta_path(file_id))
            if ext:
                _unlink(_body_path(file_id, ext))
            removed += 1
    return removed


def list_files(user_id: str, device_id: str) -> list[dict]:
    purge_expired()
    rows = []
    for row in _iter_metas():
        if row.get("user_id") != user_id or row.get("device_id") != device_id:
            continue
        if _is_expired(row):
            continue
        rows.append(row)
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return rows


def get_by_token(token: str) -> dict | None:
    if not token or "/" in token or ".." in token:
        return None
    for row in _iter_metas():
        if row.get("token") != token:
            continue
        if _is_expired(row):
            return None
        return row
    return None


def extend_file(file_id: str, user_id: str, device_id: str, ttl_days) -> dict:
    safe = _safe_id(file_id)
    if not safe:
        raise QrFileError("このQRは見つかりません。", 404)
    days = normalize_ttl(ttl_days)
    now = now_dt()
    with _lock:
        row = _load_meta(_meta_path(safe))
        if not row or row.get("user_id") != user_id or row.get("device_id") != device_id:
            raise QrFileError("このQRは見つかりません。", 404)
        if _is_expired(row, now):
            raise QrFileError("このQRは見つかりません。", 404)
        from toolbox.storage import _parse_dt

        base = _parse_dt(row.get("expires_at")) or now
        if base < now:
            base = now
        row["expires_at"] = (base + timedelta(days=days)).isoformat(timespec="seconds")
        _write_json(_meta_path(safe), row)
    return row


def delete_file(file_id: str, user_id: str, device_id: str) -> bool:
    safe = _safe_id(file_id)
    if not safe:
        return False
    with _lock:
        row = _load_meta(_meta_path(safe))
        if not row:
            return False
        if row.get("user_id") != user_id or row.get("device_id") != device_id:
            return False
        ext = str(row.get("ext") or "")
        _unlink(_meta_path(safe))
        if ext:
            _unlink(_body_path(safe, ext))
    return True


def save_upload(*, user_id: str, device_id: str, original_name: str, data: bytes, ttl_days: int, title: str) -> dict:
    title = require_title(title)
    ext = extension_of(original_name)
    if len(data) > config.QR_FILE_MAX_BYTES:
        raise QrFileError("ファイルは20MBまでです。", 413)
    if not data:
        raise QrFileError("空のファイルはアップロードできません。")
    if not magic_ok(ext, data):
        raise QrFileError("ファイルの中身が拡張子と一致しません。")
    days = normalize_ttl(ttl_days)
    display_name = Path(original_name or "").name.strip() or f"file.{ext}"
    if len(display_name) > 180:
        display_name = display_name[:180]
    now = now_dt()
    file_id = new_id()
    row = {
        "id": file_id,
        "token": secrets.token_urlsafe(16),
        "user_id": user_id,
        "device_id": device_id,
        "title": title,
        "original_name": display_name,
        "ext": ext,
        "size": len(data),
        "mime": config.QR_FILE_MIME[ext],
        "created_at": now_iso(),
        "expires_at": (now + timedelta(days=days)).isoformat(timespec="seconds"),
    }
    with _lock:
        used = 0
        for existing in _iter_metas():
            if existing.get("user_id") != user_id or existing.get("device_id") != device_id:
                continue
            if _is_expired(existing, now):
                continue
            used += int(existing.get("size") or 0)
        if used + len(data) > config.QR_FILE_DEVICE_QUOTA:
            raise QrFileError("この端末の保存容量（200MB）を超えます。不要なファイルを削除してください。", 413)
        _write_bytes(_body_path(file_id, ext), data)
        _write_json(_meta_path(file_id), row)
    return row


def body_path_for(row: dict) -> Path | None:
    file_id = _safe_id(str(row.get("id") or ""))
    ext = str(row.get("ext") or "")
    if not file_id or ext not in config.QR_FILE_ALLOWED_EXT:
        return None
    path = _body_path(file_id, ext)
    if not path.is_file():
        return None
    return path
