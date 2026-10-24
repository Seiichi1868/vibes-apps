"""管理者パスワードと署名 Cookie。POST は同一オリジンのカスタムヘッダ必須。"""
from __future__ import annotations

import hmac
from functools import wraps

from flask import current_app, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from speech_rec.config import ADMIN_HEADER, COOKIE_MAX_AGE, COOKIE_NAME, SESSION_SALT, admin_password


def _runtime_secret() -> str:
    import os

    secret = str(current_app.config.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY") or "").strip()
    render = (os.environ.get("RENDER") or "").strip().lower() in {"1", "true", "yes", "on"}
    env = (os.environ.get("FLASK_ENV") or os.environ.get("ENV") or "").strip().lower()
    production = render or env == "production"
    if production and (not secret or secret in {"local-dev-flask-secret", "speech-rec-dev-secret", "your-secret-key-here"}):
        raise RuntimeError("FLASK_SECRET_KEY が未設定です。本番では起動できません。")
    return secret or "local-dev-flask-secret"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_runtime_secret(), salt=SESSION_SALT)


def cookie_secure() -> bool:
    proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    return request.is_secure or proto == "https"


def read_admin() -> bool:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return False
    try:
        data = _serializer().loads(raw, max_age=COOKIE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(data, dict) and data.get("role") == "admin"


def attach_admin_cookie(response):
    token = _serializer().dumps({"role": "admin"})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=cookie_secure(),
        samesite="Lax",
        path="/rec",
    )
    return response


def clear_admin_cookie(response):
    response.delete_cookie(COOKIE_NAME, path="/rec")
    return response


def password_ok(given: str) -> bool:
    expected = admin_password()
    if not expected or not given:
        return False
    return hmac.compare_digest(expected, given)


def require_admin_header(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        origin = request.headers.get("Origin") or ""
        host = request.host_url.rstrip("/")
        if origin and origin.rstrip("/") != host:
            return jsonify({"ok": False, "error": "origin"}), 403
        if request.headers.get(ADMIN_HEADER) != "1":
            return jsonify({"ok": False, "error": "header"}), 403
        return view(*args, **kwargs)

    return wrapped


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not getattr(g, "speech_rec_admin", False):
            return jsonify({"ok": False, "error": "auth"}), 401
        return view(*args, **kwargs)

    return wrapped
