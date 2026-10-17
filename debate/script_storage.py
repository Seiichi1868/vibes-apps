"""観戦用スクリプトの永続化（data/debate/scripts/<script_id>.json）。

書き込みはセッションと同じく、IDごとのロックと tmp→replace。
音声ファイルは data/debate/script_audio/<script_id>/。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from debate.config import (
    DATA_DIR,
    PART_ORDER,
    SCRIPT_AUDIO_DIR,
    SCRIPTS_DIR,
    ensure_dirs,
    format_score_total,
    side_score_totals,
)
from debate.file_lock import get_named_lock

_lock = threading.Lock()

PREVIEW_TOKEN_TTL_SEC = 15 * 60
FAILED_KEEP = 20

MAX_TEACHER_NOTE_LEN = 500


def _safe_id(script_id: str) -> str:
    return "".join(c for c in str(script_id or "") if c.isalnum() or c == "-")


def script_path(script_id: str) -> Path:
    return SCRIPTS_DIR / f"{_safe_id(script_id)}.json"


def checks_path(script_id: str) -> Path:
    return SCRIPTS_DIR / f"{_safe_id(script_id)}.checks.json"


def script_audio_dir(script_id: str) -> Path:
    return SCRIPT_AUDIO_DIR / _safe_id(script_id)


def get_script_lock(script_id: str):
    """スクリプトJSONと照合JSONの更新を、ワーカーをまたいで直列化する。"""
    safe_id = _safe_id(script_id)
    return get_named_lock(DATA_DIR / "locks" / f"script-{safe_id}.lock")


def save_script(script: dict) -> dict:
    from debate.models import now_iso

    script["updated_at"] = now_iso()
    ensure_dirs()
    path = script_path(script["script_id"])
    with _lock:
        tmp_path = path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(script, handle, ensure_ascii=False, indent=2)
        tmp_path.replace(path)
    return script


def save_checks(script_id: str, checks: dict) -> dict:
    from debate.models import now_iso

    checks["script_id"] = _safe_id(script_id)
    checks["updated_at"] = now_iso()
    ensure_dirs()
    path = checks_path(script_id)
    with _lock:
        tmp_path = path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(checks, handle, ensure_ascii=False, indent=2)
        tmp_path.replace(path)
    return checks


def load_checks(script_id: str) -> dict | None:
    ensure_dirs()
    path = checks_path(script_id)
    if not path.is_file():
        return None
    with _lock:
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return None
    if not isinstance(data, dict):
        return None
    return data


def load_script(script_id: str) -> dict | None:
    ensure_dirs()
    path = script_path(script_id)
    if not path.is_file():
        return None
    with _lock:
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return None
    if not isinstance(data, dict) or not data.get("script_id"):
        return None
    return data


def list_scripts() -> list[dict]:
    ensure_dirs()
    items = []
    for path in SCRIPTS_DIR.glob("*.json"):
        if path.name.endswith(".checks.json"):
            continue
        script = load_script(path.stem)
        if script:
            items.append(script)
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items


def list_published_scripts() -> list[dict]:
    return [item for item in list_scripts() if item.get("status") == "published"]


def delete_script(script_id: str) -> bool:
    ensure_dirs()
    path = script_path(script_id)
    audio_dir = script_audio_dir(script_id)
    existed = path.is_file() or audio_dir.is_dir()
    checks = checks_path(script_id)
    with _lock:
        if path.is_file():
            path.unlink()
        tmp_path = path.with_suffix(".json.tmp")
        if tmp_path.is_file():
            tmp_path.unlink()
        if checks.is_file():
            checks.unlink()
        checks_tmp = checks.with_suffix(".json.tmp")
        if checks_tmp.is_file():
            checks_tmp.unlink()
    if audio_dir.is_dir():
        shutil.rmtree(audio_dir, ignore_errors=True)
    return existed


def part_audio_path(script_id: str, part: str) -> Path | None:
    if part not in PART_ORDER:
        return None
    return script_audio_dir(script_id) / f"{part}.mp3"


def write_part_audio(script_id: str, part: str, audio_bytes: bytes) -> Path:
    path = part_audio_path(script_id, part)
    if path is None:
        raise ValueError("不明なパートです。")
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".mp3.tmp")
    tmp_path.write_bytes(audio_bytes)
    tmp_path.replace(path)
    return path


def part_audio_ready(script_id: str, part: dict) -> bool:
    if not isinstance(part, dict):
        return False
    name = str(part.get("part") or "")
    audio = part.get("audio") if isinstance(part.get("audio"), dict) else {}
    if str(audio.get("status") or "") != "ready":
        return False
    if str(audio.get("text_hash") or "") != str(part.get("text_hash") or ""):
        return False
    path = part_audio_path(script_id, name)
    return bool(path and path.is_file() and path.stat().st_size > 0)


def _preview_secret() -> bytes | None:
    secret = (os.environ.get("DEBATE_PREVIEW_SECRET") or "").strip()
    if not secret:
        return None
    return secret.encode("utf-8")


def issue_preview_token(script_id: str) -> str:
    """ワーカーが複数でも同じトークンを検証できるよう署名する。"""
    secret = _preview_secret()
    if not secret:
        raise RuntimeError("DEBATE_PREVIEW_SECRET is not set")
    expires = int(time.time()) + PREVIEW_TOKEN_TTL_SEC
    body = f"{_safe_id(script_id)}.{expires}"
    sig = hmac.new(secret, body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def preview_token_valid(script_id: str, token: str) -> bool:
    wanted = _safe_id(script_id)
    raw = str(token or "").strip()
    secret = _preview_secret()
    if not wanted or not raw or not secret:
        return False
    parts = raw.split(".")
    if len(parts) != 3:
        return False
    stored_id, expires_text, sig = parts
    if stored_id != wanted:
        return False
    try:
        expires = int(expires_text)
    except ValueError:
        return False
    if expires < time.time():
        return False
    body = f"{stored_id}.{expires_text}"
    expected = hmac.new(secret, body.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def failed_scripts_dir() -> Path:
    return SCRIPTS_DIR / "_failed"


def save_failed_script_response(record: dict) -> Path:
    """失敗時の生レスポンス。管理者向け。最新20件だけ残す。"""
    from debate.models import now_iso

    ensure_dirs()
    folder = failed_scripts_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = f"{now_iso().replace(':', '').replace('+', '')}-{uuid.uuid4().hex[:6]}"
    payload = dict(record)
    payload["saved_at"] = now_iso()
    path = folder / f"{stamp}.json"
    with _lock:
        tmp_path = path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        tmp_path.replace(path)
        kept = sorted(folder.glob("*.json"), key=lambda item: item.name)
        while len(kept) > FAILED_KEEP:
            oldest = kept.pop(0)
            oldest.unlink(missing_ok=True)
    return path


def audio_is_stale(part: dict) -> bool:
    audio = part.get("audio") if isinstance(part.get("audio"), dict) else {}
    text_hash = str(part.get("text_hash") or "")
    audio_hash = str(audio.get("text_hash") or "")
    status = str(audio.get("status") or "none")
    if status in ("none", "error"):
        return False
    return bool(text_hash) and audio_hash != text_hash


def script_admin_summary(script: dict) -> dict:
    parts = []
    for part in script.get("parts") or []:
        if not isinstance(part, dict):
            continue
        audio = part.get("audio") if isinstance(part.get("audio"), dict) else {}
        parts.append(
            {
                "part": part.get("part"),
                "side": part.get("side"),
                "word_count": part.get("word_count") or 0,
                "key_point_ja": part.get("key_point_ja") or "",
                "audio_status": audio.get("status") or "none",
                "audio_stale": audio_is_stale(part),
                "audio_error": audio.get("error") or "",
            }
        )
    from debate.ai_script import normalize_warning

    warnings = [normalize_warning(item) for item in (script.get("warnings") or [])]
    argument_map = script.get("argument_map") or []
    score_line = format_score_total(side_score_totals(argument_map)) if argument_map else ""
    return {
        "script_id": script.get("script_id"),
        "motion": script.get("motion") or "",
        "level": script.get("level") or "",
        "intended_winner": script.get("intended_winner") or "",
        "status": script.get("status") or "draft",
        "generation_status": script.get("generation_status") or "idle",
        "generation_error": script.get("generation_error") or "",
        "generation_seconds": script.get("generation_seconds"),
        "warnings": warnings,
        "score_line": score_line,
        "created_at": script.get("created_at") or "",
        "gen_cost_usd": script.get("gen_cost_usd") or 0,
        "speech_cost_usd": script.get("speech_cost_usd") or 0,
        "generation_attempts": script.get("generation_attempts") or 0,
        "generation_attempt_seconds": script.get("generation_attempt_seconds") or [],
        "generation_calls": script.get("generation_calls") or [],
        "script_model": script.get("script_model") or "",
        "teacher_note": script.get("teacher_note") or "",
        "check_cost_usd": _check_cost(script.get("script_id")),
        "parts": parts,
    }


def _check_cost(script_id: str | None) -> float:
    checks = load_checks(str(script_id or ""))
    if not checks:
        return 0.0
    try:
        return round(float(checks.get("total_cost_usd") or 0), 6)
    except (TypeError, ValueError):
        return 0.0


def normalize_teacher_note(note: str) -> str:
    return str(note or "").strip()[:MAX_TEACHER_NOTE_LEN]
