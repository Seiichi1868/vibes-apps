"""Toolbox 専用のログイン・CSRF・管理再認証。Flask 全体のセッション設定は変えない。"""
from __future__ import annotations

import hmac
import logging
import secrets
from functools import wraps

from flask import g, jsonify, redirect, request, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from toolbox.config import (
    ADMIN_REAUTH_SEC,
    COOKIE_MAX_AGE,
    COOKIE_NAME,
    MIN_PASSWORD_LEN,
    SESSION_SALT,
)
from toolbox.storage import (
    add_login_attempt,
    get_user,
    login_lock_remaining,
    now_iso,
    public_user,
    save_user,
)

logger = logging.getLogger(__name__)


def _serializer() -> URLSafeTimedSerializer:
    from flask import current_app

    secret = current_app.config.get("SECRET_KEY") or "toolbox-dev-secret"
    return URLSafeTimedSerializer(str(secret), salt=SESSION_SALT)


def cookie_secure() -> bool:
    proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    return request.is_secure or proto == "https"


def read_session() -> dict:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return {}
    try:
        data = _serializer().loads(raw, max_age=COOKIE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return {}
    return data if isinstance(data, dict) else {}


def write_session_cookie(response, data: dict):
    token = _serializer().dumps(data)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=cookie_secure(),
        samesite="Lax",
        path="/toolbox",
    )
    return response


def clear_session_cookie(response):
    response.delete_cookie(COOKIE_NAME, path="/toolbox")
    return response


def ensure_csrf(data: dict) -> dict:
    next_data = dict(data)
    if not next_data.get("csrf"):
        next_data["csrf"] = secrets.token_urlsafe(32)
    return next_data


def current_csrf() -> str:
    return str(getattr(g, "toolbox_session", {}).get("csrf") or "")


def current_user() -> dict | None:
    return getattr(g, "toolbox_user", None)


def wants_json() -> bool:
    if request.path.startswith("/toolbox/api/") or request.path.startswith("/toolbox/admin/api/"):
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes["application/json"] > 0


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def password_ok(password: str) -> str | None:
    if len(password or "") < MIN_PASSWORD_LEN:
        return f"パスワードは{MIN_PASSWORD_LEN}文字以上にしてください。"
    return None


def client_ip() -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or (request.remote_addr or "unknown")


def authenticate(username: str, password: str) -> tuple[dict | None, str | None]:
    name = (username or "").strip()
    ip = client_ip()
    remaining = login_lock_remaining(name, ip)
    if remaining > 0:
        minutes = max(1, (remaining + 59) // 60)
        return None, f"ログイン試行が多すぎます。約{minutes}分後にやり直してください。"
    user = get_user(username=name)
    if not user or not check_password_hash(user.get("password_hash") or "", password or ""):
        add_login_attempt(name, ip, False)
        return None, "ユーザー名またはパスワードが違います。"
    if not user.get("is_active"):
        add_login_attempt(name, ip, False)
        return None, "このアカウントは停止されています。管理者に連絡してください。"
    add_login_attempt(name, ip, True)
    user["last_login_at"] = now_iso()
    save_user(user)
    return user, None


def verify_password(user: dict, password: str) -> bool:
    return check_password_hash(user.get("password_hash") or "", password or "")


def admin_reauth_ok() -> bool:
    until = getattr(g, "toolbox_session", {}).get("admin_ok_until")
    try:
        return float(until or 0) > __import__("time").time()
    except (TypeError, ValueError):
        return False


def set_admin_reauth(data: dict) -> dict:
    import time

    next_data = dict(data)
    next_data["admin_ok_until"] = time.time() + ADMIN_REAUTH_SEC
    return next_data


def load_request_user() -> None:
    session = ensure_csrf(read_session())
    g.toolbox_session = session
    g.toolbox_user = None
    user_id = session.get("uid")
    if not user_id:
        return
    user = get_user(user_id=user_id)
    if user and user.get("is_active"):
        g.toolbox_user = user


def csrf_error():
    message = "操作をやり直してください。ページを再読み込みしてからもう一度試してください。"
    if wants_json():
        return jsonify({"ok": False, "error": message}), 403
    return message, 403


def check_csrf() -> object | None:
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    expected = current_csrf()
    token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        token = token or payload.get("csrf_token")
    if not expected or not token or not hmac.compare_digest(str(token), expected):
        return csrf_error()
    return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            if wants_json():
                return jsonify({"ok": False, "error": "ログインしてください。"}), 401
            return redirect(url_for("toolbox.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            if wants_json():
                return jsonify({"ok": False, "error": "ログインしてください。"}), 401
            return redirect(url_for("toolbox.login", next=request.path))
        if user.get("role") != "admin":
            if wants_json():
                return jsonify({"ok": False, "error": "管理画面は管理者だけが使えます。"}), 403
            return "管理画面は管理者だけが使えます。", 403
        return view(*args, **kwargs)

    return wrapped


def require_admin_reauth():
    if admin_reauth_ok():
        return None
    return jsonify(
        {
            "ok": False,
            "error": "confirm_required",
            "message": "重要な操作です。パスワードを再入力してください。",
        }
    ), 403


def inject_auth_cookie(response):
    session = ensure_csrf(getattr(g, "toolbox_session", {}) or {})
    g.toolbox_session = session
    return write_session_cookie(response, session)


def public_current_user() -> dict | None:
    user = current_user()
    return public_user(user) if user else None
