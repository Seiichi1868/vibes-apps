"""観戦用スクリプトの永続化（data/debate/scripts/<script_id>.json）。

書き込みはセッションと同じく、IDごとのロックと tmp→replace。
音声ファイルは data/debate/script_audio/<script_id>/。
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from pathlib import Path

from debate.config import PART_ORDER, SCRIPT_AUDIO_DIR, SCRIPTS_DIR, ensure_dirs, format_score_total, side_score_totals

_lock = threading.Lock()
_script_locks: dict[str, threading.Lock] = {}
_script_locks_guard = threading.Lock()

_preview_tokens: dict[str, tuple[str, float]] = {}
_preview_guard = threading.Lock()
PREVIEW_TOKEN_TTL_SEC = 15 * 60

MAX_TEACHER_NOTE_LEN = 500


def _safe_id(script_id: str) -> str:
    return "".join(c for c in str(script_id or "") if c.isalnum() or c == "-")


def script_path(script_id: str) -> Path:
    return SCRIPTS_DIR / f"{_safe_id(script_id)}.json"


def script_audio_dir(script_id: str) -> Path:
    return SCRIPT_AUDIO_DIR / _safe_id(script_id)


def get_script_lock(script_id: str) -> threading.Lock:
    safe_id = _safe_id(script_id)
    with _script_locks_guard:
        lock = _script_locks.get(safe_id)
        if lock is None:
            lock = threading.Lock()
            _script_locks[safe_id] = lock
        return lock


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
    with _lock:
        if path.is_file():
            path.unlink()
        tmp_path = path.with_suffix(".json.tmp")
        if tmp_path.is_file():
            tmp_path.unlink()
    if audio_dir.is_dir():
        shutil.rmtree(audio_dir, ignore_errors=True)
    return existed


def part_audio_path(script_id: str, part: str) -> Path | None:
    if part not in PART_ORDER:
        return None
    return script_audio_dir(script_id) / f"{part}.mp3"


def issue_preview_token(script_id: str) -> str:
    token = uuid.uuid4().hex
    expires = time.time() + PREVIEW_TOKEN_TTL_SEC
    with _preview_guard:
        _preview_tokens[token] = (_safe_id(script_id), expires)
        _prune_preview_tokens_locked()
    return token


def preview_token_valid(script_id: str, token: str) -> bool:
    wanted = _safe_id(script_id)
    raw = str(token or "").strip()
    if not wanted or not raw:
        return False
    now = time.time()
    with _preview_guard:
        _prune_preview_tokens_locked(now)
        found = _preview_tokens.get(raw)
        if not found:
            return False
        stored_id, expires = found
        return stored_id == wanted and expires >= now


def _prune_preview_tokens_locked(now: float | None = None) -> None:
    current = time.time() if now is None else now
    expired = [key for key, (_sid, expires) in _preview_tokens.items() if expires < current]
    for key in expired:
        _preview_tokens.pop(key, None)


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
        "script_model": script.get("script_model") or "",
        "teacher_note": script.get("teacher_note") or "",
        "parts": parts,
    }


def normalize_teacher_note(note: str) -> str:
    return str(note or "").strip()[:MAX_TEACHER_NOTE_LEN]
