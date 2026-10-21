"""URLのQRアーカイブ。期限を過ぎたものは一覧のときに消す。"""
from __future__ import annotations

from datetime import timedelta

from toolbox.config import QR_ARCHIVE_FILE
from toolbox.storage import _lock, _parse_dt, _read_json, _write_json, new_id, now_dt, now_iso
from toolbox.tools.qr.files import QrFileError, normalize_ttl, require_title


def _load() -> list[dict]:
    data = _read_json(QR_ARCHIVE_FILE, [])
    return data if isinstance(data, list) else []


def _save(items: list[dict]) -> None:
    _write_json(QR_ARCHIVE_FILE, items)


def _purge(items: list[dict], now) -> list[dict]:
    kept = []
    for item in items:
        expires = _parse_dt(item.get("expires_at"))
        if expires and expires > now:
            kept.append(item)
    return kept


def list_links(user_id: str, device_id: str) -> list[dict]:
    now = now_dt()
    with _lock:
        items = _purge(_load(), now)
        _save(items)
    rows = [
        item for item in items
        if item.get("user_id") == user_id and item.get("device_id") == device_id
    ]
    rows.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return rows


def save_link(*, user_id: str, device_id: str, title: str, url: str, ttl_days) -> dict:
    title = require_title(title)
    days = normalize_ttl(ttl_days)
    now = now_dt()
    item = {
        "id": new_id(),
        "user_id": user_id,
        "device_id": device_id,
        "title": title,
        "url": url,
        "created_at": now_iso(),
        "expires_at": (now + timedelta(days=days)).isoformat(timespec="seconds"),
    }
    with _lock:
        items = _purge(_load(), now)
        items.append(item)
        _save(items)
    return item


def delete_link(item_id: str, user_id: str, device_id: str) -> bool:
    with _lock:
        items = _load()
        kept = []
        found = False
        for item in items:
            if item.get("id") == item_id:
                if item.get("user_id") != user_id or item.get("device_id") != device_id:
                    return False
                found = True
                continue
            kept.append(item)
        if found:
            _save(kept)
        return found


def extend_link(item_id: str, user_id: str, device_id: str, ttl_days) -> dict:
    days = normalize_ttl(ttl_days)
    now = now_dt()
    with _lock:
        items = _purge(_load(), now)
        found = None
        for item in items:
            if item.get("id") != item_id:
                continue
            if item.get("user_id") != user_id or item.get("device_id") != device_id:
                raise QrFileError("このQRは見つかりません。", 404)
            base = _parse_dt(item.get("expires_at")) or now
            if base < now:
                base = now
            item["expires_at"] = (base + timedelta(days=days)).isoformat(timespec="seconds")
            found = item
            break
        if not found:
            raise QrFileError("このQRは見つかりません。", 404)
        _save(items)
    return found
