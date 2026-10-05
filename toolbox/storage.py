"""JSON ファイルによる永続化（既存アプリと同じ方式。SQLite は導入しない）。"""
from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from toolbox.config import (
    APP_SETTINGS_FILE,
    CLASSES_FILE,
    DEFAULT_ASSUME_INPUT_TOKENS,
    DEFAULT_ASSUME_OUTPUT_TOKENS,
    DEFAULT_ASSUME_TRANSCRIBE_SEC,
    DEFAULT_DAILY_LIMIT_USD,
    DEFAULT_GENERATE_MODEL,
    DEFAULT_LOGIN_REQUIRED,
    DEFAULT_PARALLEL_BROWSER_STT,
    DEFAULT_TRANSCRIBE_MODEL,
    FAVORITES_FILE,
    LOGIN_ATTEMPTS_FILE,
    RECENT_TOOLS_FILE,
    TALK_AUDIO_DIR,
    TALK_SESSIONS_DIR,
    TOOL_SETTINGS_FILE,
    USAGE_LOG_FILE,
    USERS_FILE,
    ensure_dirs,
)
from toolbox.registry import all_tools

_lock = threading.Lock()
JST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def now_dt() -> datetime:
    return datetime.now(JST)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _read_json(path: Path, default):
    if not path.is_file():
        return deepcopy(default)
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return deepcopy(default)


def _write_json(path: Path, data) -> None:
    ensure_dirs()
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt.astimezone(JST)


# ── users ───────────────────────────────────────────────────

def list_users() -> list[dict]:
    with _lock:
        return _read_json(USERS_FILE, [])


def get_user(user_id: str | None = None, username: str | None = None) -> dict | None:
    for user in list_users():
        if user_id and user.get("id") == user_id:
            return user
        if username and user.get("username") == username:
            return user
    return None


def save_user(user: dict) -> dict:
    with _lock:
        users = _read_json(USERS_FILE, [])
        replaced = False
        for index, existing in enumerate(users):
            if existing.get("id") == user["id"]:
                users[index] = user
                replaced = True
                break
        if not replaced:
            users.append(user)
        _write_json(USERS_FILE, users)
    return user


def delete_user(user_id: str) -> bool:
    with _lock:
        users = _read_json(USERS_FILE, [])
        next_users = [user for user in users if user.get("id") != user_id]
        if len(next_users) == len(users):
            return False
        _write_json(USERS_FILE, next_users)
    return True


def count_active_admins(exclude_id: str | None = None) -> int:
    return sum(
        1
        for user in list_users()
        if user.get("role") == "admin"
        and user.get("is_active")
        and user.get("id") != exclude_id
    )


def public_user(user: dict) -> dict:
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "role": user.get("role"),
        "is_active": bool(user.get("is_active")),
        "created_at": user.get("created_at"),
        "last_login_at": user.get("last_login_at"),
        "is_guest": bool(user.get("is_guest")),
    }


# ── login attempts ──────────────────────────────────────────

def add_login_attempt(username: str, ip: str, success: bool) -> None:
    with _lock:
        rows = _read_json(LOGIN_ATTEMPTS_FILE, [])
        cutoff = now_dt() - timedelta(hours=24)
        kept = []
        for row in rows:
            dt = _parse_dt(row.get("attempted_at"))
            if dt and dt >= cutoff:
                kept.append(row)
        kept.append(
            {
                "username": username,
                "ip": ip,
                "attempted_at": now_iso(),
                "success": bool(success),
            }
        )
        _write_json(LOGIN_ATTEMPTS_FILE, kept)


def login_lock_remaining(username: str, ip: str) -> int:
    window_start = now_dt() - timedelta(seconds=900)
    failures: list[datetime] = []
    with _lock:
        rows = _read_json(LOGIN_ATTEMPTS_FILE, [])
    for row in rows:
        if row.get("username") != username or row.get("ip") != ip or row.get("success"):
            continue
        dt = _parse_dt(row.get("attempted_at"))
        if dt and dt >= window_start:
            failures.append(dt)
    if len(failures) < 5:
        return 0
    last = max(failures)
    unlock_at = last + timedelta(seconds=900)
    remaining = int((unlock_at - now_dt()).total_seconds())
    return max(0, remaining)


# ── tool settings ───────────────────────────────────────────

def _default_tool_settings() -> dict:
    return {
        tool["id"]: {"enabled": bool(tool["default_enabled"]), "updated_at": None}
        for tool in all_tools()
    }


def load_tool_settings() -> dict:
    stored = _read_json(TOOL_SETTINGS_FILE, {})
    merged = _default_tool_settings()
    for tool_id, value in stored.items():
        if tool_id in merged and isinstance(value, dict):
            merged[tool_id]["enabled"] = bool(value.get("enabled", merged[tool_id]["enabled"]))
            merged[tool_id]["updated_at"] = value.get("updated_at")
    return merged


def is_tool_enabled(tool_id: str) -> bool:
    settings = load_tool_settings()
    if tool_id not in settings:
        return False
    return bool(settings[tool_id]["enabled"])


def set_tool_enabled(tool_id: str, enabled: bool) -> dict:
    with _lock:
        settings = load_tool_settings()
        if tool_id not in settings:
            raise KeyError(tool_id)
        settings[tool_id] = {"enabled": bool(enabled), "updated_at": now_iso()}
        _write_json(TOOL_SETTINGS_FILE, settings)
        return settings[tool_id]


# ── favorites / recent ──────────────────────────────────────

def list_favorites(user_id: str) -> list[str]:
    data = _read_json(FAVORITES_FILE, {})
    return list(data.get(user_id, []))


def toggle_favorite(user_id: str, tool_id: str) -> bool:
    with _lock:
        data = _read_json(FAVORITES_FILE, {})
        current = list(data.get(user_id, []))
        if tool_id in current:
            current = [item for item in current if item != tool_id]
            favored = False
        else:
            current.append(tool_id)
            favored = True
        data[user_id] = current
        _write_json(FAVORITES_FILE, data)
    return favored


def list_recent(user_id: str, limit: int = 5) -> list[dict]:
    data = _read_json(RECENT_TOOLS_FILE, {})
    rows = list(data.get(user_id, []))
    rows.sort(key=lambda row: row.get("last_used_at") or "", reverse=True)
    return rows[:limit]


def record_recent(user_id: str, tool_id: str) -> None:
    with _lock:
        data = _read_json(RECENT_TOOLS_FILE, {})
        rows = [row for row in data.get(user_id, []) if row.get("tool_id") != tool_id]
        rows.insert(0, {"tool_id": tool_id, "last_used_at": now_iso()})
        data[user_id] = rows[:20]
        _write_json(RECENT_TOOLS_FILE, data)


# ── classes ─────────────────────────────────────────────────

def list_classes(user_id: str) -> list[dict]:
    rows = _read_json(CLASSES_FILE, [])
    return [row for row in rows if row.get("user_id") == user_id]


def get_class(class_id: str, user_id: str | None = None) -> dict | None:
    for row in _read_json(CLASSES_FILE, []):
        if row.get("id") != class_id:
            continue
        if user_id and row.get("user_id") != user_id:
            return None
        return row
    return None


def save_class(row: dict) -> dict:
    with _lock:
        rows = _read_json(CLASSES_FILE, [])
        replaced = False
        for index, existing in enumerate(rows):
            if existing.get("id") == row["id"]:
                rows[index] = row
                replaced = True
                break
        if not replaced:
            rows.append(row)
        _write_json(CLASSES_FILE, rows)
    return row


def delete_class(class_id: str, user_id: str) -> bool:
    with _lock:
        rows = _read_json(CLASSES_FILE, [])
        next_rows = [
            row for row in rows if not (row.get("id") == class_id and row.get("user_id") == user_id)
        ]
        if len(next_rows) == len(rows):
            return False
        _write_json(CLASSES_FILE, next_rows)
    return True


# ── app settings ────────────────────────────────────────────

DEFAULT_APP_SETTINGS = {
    "daily_limit_usd": DEFAULT_DAILY_LIMIT_USD,
    "transcribe_model": DEFAULT_TRANSCRIBE_MODEL,
    "generate_model": DEFAULT_GENERATE_MODEL,
    "assume_transcribe_sec": DEFAULT_ASSUME_TRANSCRIBE_SEC,
    "assume_input_tokens": DEFAULT_ASSUME_INPUT_TOKENS,
    "assume_output_tokens": DEFAULT_ASSUME_OUTPUT_TOKENS,
    "parallel_browser_stt": DEFAULT_PARALLEL_BROWSER_STT,
    "login_required_enabled": DEFAULT_LOGIN_REQUIRED,
    "model_overrides": {},
}


def load_app_settings() -> dict:
    stored = _read_json(APP_SETTINGS_FILE, {})
    merged = deepcopy(DEFAULT_APP_SETTINGS)
    if isinstance(stored, dict):
        merged.update(stored)
        if not isinstance(merged.get("model_overrides"), dict):
            merged["model_overrides"] = {}
    return merged


def get_setting(key: str, default=None):
    settings = load_app_settings()
    return settings.get(key, default)


def update_app_settings(updates: dict) -> dict:
    with _lock:
        settings = load_app_settings()
        settings.update(updates)
        _write_json(APP_SETTINGS_FILE, settings)
        return settings


# ── usage log ───────────────────────────────────────────────

def append_usage(entry: dict) -> dict:
    row = dict(entry)
    row.setdefault("id", new_id())
    row.setdefault("ts", now_iso())
    with _lock:
        rows = _read_json(USAGE_LOG_FILE, [])
        rows.append(row)
        _write_json(USAGE_LOG_FILE, rows[-5000:])
    return row


def list_usage() -> list[dict]:
    return _read_json(USAGE_LOG_FILE, [])


# ── talk sessions ───────────────────────────────────────────

def _session_path(session_id: str) -> Path:
    return TALK_SESSIONS_DIR / f"{session_id}.json"


def save_talk_session(session: dict) -> dict:
    ensure_dirs()
    path = _session_path(session["id"])
    with _lock:
        _write_json(path, session)
    return session


def load_talk_session(session_id: str, user_id: str | None = None) -> dict | None:
    path = _session_path(session_id)
    if not path.is_file():
        return None
    data = _read_json(path, None)
    if not isinstance(data, dict):
        return None
    if user_id and data.get("user_id") != user_id:
        return None
    return data


def list_talk_sessions(user_id: str) -> list[dict]:
    ensure_dirs()
    rows = []
    for path in TALK_SESSIONS_DIR.glob("*.json"):
        data = _read_json(path, None)
        if isinstance(data, dict) and data.get("user_id") == user_id:
            rows.append(data)
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return rows


def delete_talk_session(session_id: str, user_id: str) -> bool:
    session = load_talk_session(session_id, user_id)
    if not session:
        return False
    path = _session_path(session_id)
    audio_name = session.get("audio_file")
    if audio_name:
        try:
            (TALK_AUDIO_DIR / Path(str(audio_name)).name).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        path.unlink()
    except OSError:
        return False
    return True
