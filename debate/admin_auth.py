"""Debate 管理ログインと試行制限。他アプリは import しない。

Flask セッションに署名付きフラグを置く。試行回数は data/debate 配下の JSON に
flock 付きで書き、gunicorn の複数ワーカーで共有する。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from flask import jsonify, request, session

from debate.file_lock import get_named_lock

SESSION_KEY = "debate_admin_until"
WINDOW_SEC = 15 * 60
MAX_FAIL_PER_IP = 5
MAX_FAIL_GLOBAL = 30
LOCK_SEC = 15 * 60
GLOBAL_KEY = "__global__"
TOO_MANY = "試行回数が多すぎます。15分ほど待ってからやり直してください。"


def _attempts_path() -> Path:
    root = Path(
        os.environ.get("DEBATE_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data" / "debate"))
    ).expanduser()
    return root / "admin_auth" / "attempts.json"


def _session_ttl_sec() -> int:
    try:
        return int(os.environ.get("DEBATE_ADMIN_SESSION_TTL_SEC", str(8 * 3600)))
    except (TypeError, ValueError):
        return 8 * 3600


def configure_debate_session_cookie(app) -> None:
    """管理ログインが使う Flask セッション Cookie の属性。アプリ全体で Cookie は一つ。"""
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if os.environ.get("RENDER"):
        app.config["SESSION_COOKIE_SECURE"] = True


def client_ip() -> str:
    """Render 配下の実クライアント IP。

    X-Forwarded-For は「元のクライアント, 途中のプロキシ…」の順で、各プロキシが末尾に足す。
    1 段だけ信用する場合（Werkzeug ProxyFix の x_for=1 と同じ）は右端を使う。
    左端を使うと、呼び出し元がヘッダーを付けて制限をすり抜けられる。
    この環境では Render の実ホップ数をパケットで確認していないので、PR に未検証と書く。
    """
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
    session.clear()
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
    with get_named_lock(path.with_name(path.name + ".lock")):
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


def check_admin_password_attempt(provided) -> tuple | None:
    """成功なら None。失敗なら (response, status)。ログインと生徒側パスワード確認で共用。"""
    from debate.admin import admin_password_matches, get_admin_password

    if not get_admin_password():
        return jsonify({"ok": False, "error": "管理パスワードが設定されていません。"}), 503
    ip = client_ip()
    if is_locked(ip):
        return limiter_denied_response()
    if not admin_password_matches(provided):
        record_failure(ip)
        if is_locked(ip):
            return limiter_denied_response()
        return jsonify({"ok": False, "error": "管理パスワードが違います。"}), 403
    clear_failures(ip)
    return None
