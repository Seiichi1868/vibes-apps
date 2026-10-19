"""Toolbox 管理ログインと試行制限。他アプリは import しない。

Flask セッションに署名付きフラグを置く。試行回数は JSON に flock 付きで書き、
gunicorn の複数ワーカーで共有する。
"""
from __future__ import annotations

import fcntl
import json
import os
import threading
import time
from pathlib import Path

from flask import jsonify, request, session

SESSION_KEY = "toolbox_admin_panel_until"
WINDOW_SEC = 15 * 60
MAX_FAIL_PER_IP = 5
MAX_FAIL_GLOBAL = 30
LOCK_SEC = 15 * 60
GLOBAL_KEY = "__global__"
TOO_MANY = "試行回数が多すぎます。15分ほど待ってからやり直してください。"
ENV_TTL = "TOOLBOX_ADMIN_SESSION_TTL_SEC"

_guard = threading.Lock()
_locks: dict[str, "_ProcessFileLock"] = {}


class _ProcessFileLock:
    def __init__(self, path: Path):
        self._path = path
        self._thread = threading.RLock()
        self._fh = None
        self._depth = 0

    def __enter__(self):
        self._thread.acquire()
        try:
            if self._depth == 0:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._fh = self._path.open("a+")
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
            self._depth += 1
        except Exception:
            self._thread.release()
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self._depth -= 1
            if self._depth <= 0:
                self._depth = 0
                handle = self._fh
                self._fh = None
                if handle is not None:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    finally:
                        handle.close()
        finally:
            self._thread.release()
        return False


def _named_lock(path: Path) -> _ProcessFileLock:
    key = str(path)
    with _guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _ProcessFileLock(path)
            _locks[key] = lock
        return lock


def _attempts_path() -> Path:
    root = Path(os.environ.get("TOOLBOX_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data" / "toolbox"))).expanduser()
    return root / "admin_auth" / "attempts.json"


def _session_ttl_sec() -> int:
    try:
        return int(os.environ.get(ENV_TTL, str(8 * 3600)))
    except (TypeError, ValueError):
        return 8 * 3600


def configure_session_cookie(app) -> None:
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if os.environ.get("RENDER"):
        app.config["SESSION_COOKIE_SECURE"] = True


def client_ip() -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return parts[-1]
    return (request.remote_addr or "unknown").strip() or "unknown"


def is_admin_session() -> bool:
    try:
        return float(session.get(SESSION_KEY) or 0) > time.time()
    except (TypeError, ValueError):
        return False


def establish_admin_session() -> None:
    session.permanent = True
    session[SESSION_KEY] = time.time() + _session_ttl_sec()
    session.modified = True


def clear_admin_session() -> None:
    session.pop(SESSION_KEY, None)
    session.modified = True


def _prune(data: dict, now: float) -> dict:
    cleaned = {}
    cutoff = now - WINDOW_SEC
    for key, value in data.items():
        if not isinstance(value, list):
            continue
        kept = [stamp for stamp in value if isinstance(stamp, (int, float)) and stamp >= cutoff]
        if kept:
            cleaned[key] = kept
    return cleaned


def _with_attempts(mutator):
    path = _attempts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _named_lock(path.with_name(path.name + ".lock")):
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            try:
                data = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                data = {}
            if not isinstance(data, dict):
                data = {}
        else:
            data = {}
        now = time.time()
        data = _prune(data, now)
        result = mutator(data, now)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)
        return result


def is_locked(ip: str) -> bool:
    def check(data, now):
        mine = data.get(ip, [])
        everyone = data.get(GLOBAL_KEY, [])
        if len(mine) >= MAX_FAIL_PER_IP and now - mine[-1] < LOCK_SEC:
            return True
        if len(everyone) >= MAX_FAIL_GLOBAL and now - everyone[-1] < LOCK_SEC:
            return True
        return False

    return bool(_with_attempts(check))


def record_failure(ip: str) -> None:
    def add(data, now):
        data.setdefault(ip, []).append(now)
        data.setdefault(GLOBAL_KEY, []).append(now)
        return None

    _with_attempts(add)


def clear_failures(ip: str) -> None:
    def drop(data, now):
        data.pop(ip, None)
        return None

    _with_attempts(drop)


def limiter_denied_response():
    return jsonify({"ok": False, "error": TOO_MANY}), 429


def check_admin_password_attempt(provided, *, matches, configured) -> tuple | None:
    if not configured():
        return jsonify({"ok": False, "error": "管理パスワードが設定されていません。"}), 503
    ip = client_ip()
    if is_locked(ip):
        return limiter_denied_response()
    if not matches(provided):
        record_failure(ip)
        if is_locked(ip):
            return limiter_denied_response()
        return jsonify({"ok": False, "error": "管理パスワードが違います。"}), 403
    clear_failures(ip)
    return None
