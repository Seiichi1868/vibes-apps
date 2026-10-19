import hmac
import os

from flask import Blueprint, jsonify, request

from flask_app.admin_auth import (
    check_admin_password_attempt,
    clear_admin_session,
    configure_session_cookie,
    establish_admin_session,
    is_admin_session,
)
from flask_app.config import Config
from flask_app.services.gate_service import set_gate_lock_enabled
from flask_app.services.runtime_settings import appearance_response, update_runtime_settings
from flask_app.services.status_service import get_public_status, set_public_status
from flask_app.utils.language_utils import (
    ai_mode_response,
    get_default_ui_language,
    get_enabled_study_languages,
    is_tts_enabled,
    languages_response,
    normalize_ai_mode,
    set_ai_mode,
    set_default_ui_language,
    set_enabled_study_languages,
    set_tts_enabled,
)
from flask_app.utils.section_utils import sections_response, set_visible_sections

admin_bp = Blueprint("admin", __name__)


@admin_bp.record_once
def _configure_admin_session(state):
    configure_session_cookie(state.app)


@admin_bp.route("/admin/login", methods=["POST"])
def admin_login():
    payload = request.get_json(silent=True) or {}
    provided = payload.get("password")
    if provided is None:
        provided = payload.get("admin_password")
    denied = check_admin_password_attempt(
        provided,
        matches=lambda value: _admin_password_ok({"admin_password": value}),
        configured=_get_admin_password,
    )
    if denied:
        return denied
    establish_admin_session()
    return jsonify({"ok": True, "logged_in": True})


@admin_bp.route("/admin/logout", methods=["POST"])
def admin_logout():
    clear_admin_session()
    return jsonify({"ok": True, "logged_in": False})


@admin_bp.route("/admin/status", methods=["GET"])
def admin_status():
    if not _get_admin_password():
        return jsonify({"ok": False, "logged_in": False, "error": _PASSWORD_UNSET}), 503
    return jsonify({"ok": True, "logged_in": is_admin_session()})

_PASSWORD_UNSET = "管理パスワードが設定されていません。"
_PASSWORD_WRONG = "管理設定のパスワードが違います。"


def _get_admin_password() -> str:
    return (os.environ.get("ADMIN_PASSWORD") or "").strip()


def _admin_password_ok(payload: dict) -> bool:
    expected = _get_admin_password()
    if not expected:
        return False
    return hmac.compare_digest(str(payload.get("admin_password") or ""), expected)


def _admin_password_denied():
    if not _get_admin_password():
        return jsonify({"error": _PASSWORD_UNSET}), 503
    return jsonify({"error": _PASSWORD_WRONG}), 403


_OPEN_ADMIN_ENDPOINTS = frozenset(
    {
        "admin.admin_login",
        "admin.admin_logout",
        "admin.admin_status",
    }
)


@admin_bp.before_request
def require_admin_session():
    if request.method == "OPTIONS":
        return None
    if request.endpoint in _OPEN_ADMIN_ENDPOINTS:
        return None
    if is_admin_session() and _get_admin_password():
        return None
    if not _get_admin_password():
        return jsonify({"ok": False, "error": _PASSWORD_UNSET}), 503
    return jsonify({"ok": False, "error": "ログインが必要です。"}), 401


@admin_bp.route("/admin/gate-lock", methods=["GET", "POST"])
def admin_gate_lock():
    from flask_app.services.gate_service import is_gate_lock_enabled

    if request.method == "GET":
        return jsonify({"lock_enabled": is_gate_lock_enabled(), "ok": True})

    payload = request.get_json(silent=True) or {}
    raw = payload.get("lock_enabled")
    if isinstance(raw, bool):
        enabled = raw
    else:
        value = str(raw or "").strip().lower()
        if value in {"1", "true", "on", "yes"}:
            enabled = True
        elif value in {"0", "false", "off", "no"}:
            enabled = False
        else:
            return jsonify({"error": "lock_enabled is required"}), 400

    return jsonify({"ok": True, "lock_enabled": set_gate_lock_enabled(enabled)})


@admin_bp.route("/admin/ai-mode", methods=["GET", "POST"])
def admin_ai_mode():
    if request.method == "GET":
        return jsonify(ai_mode_response())

    payload = request.get_json(silent=True) or {}

    raw_mode = payload.get("ai_mode")
    if raw_mode is None and payload.get("use_gpt5_mode") is not None:
        raw = payload.get("use_gpt5_mode")
        if isinstance(raw, bool):
            raw_mode = "5.6-luna" if raw else Config.DEFAULT_AI_MODE
        else:
            value = str(raw or "").strip().lower()
            raw_mode = "5.6-luna" if value in {"1", "true", "on", "yes"} else Config.DEFAULT_AI_MODE

    if raw_mode is None:
        return jsonify({"error": "ai_mode is required"}), 400

    try:
        set_ai_mode(str(raw_mode))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(ai_mode_response())


@admin_bp.route("/admin/ui-language", methods=["GET", "POST"])
def admin_ui_language():
    if request.method == "GET":
        return jsonify({"ok": True, "default_ui_language": get_default_ui_language()})

    payload = request.get_json(silent=True) or {}
    raw = payload.get("default_ui_language")
    if raw is None:
        raw = payload.get("ui_language")
    if raw is None:
        return jsonify({"error": "default_ui_language is required"}), 400

    lang = set_default_ui_language(raw)
    return jsonify({"ok": True, "default_ui_language": lang})


@admin_bp.route("/admin/tts", methods=["GET", "POST"])
def admin_tts():
    if request.method == "GET":
        return jsonify({"ok": True, "tts_enabled": is_tts_enabled()})

    payload = request.get_json(silent=True) or {}

    raw = payload.get("tts_enabled")
    if raw is None:
        raw = payload.get("enabled")
    if isinstance(raw, bool):
        enabled = raw
    else:
        value = str(raw or "").strip().lower()
        if value in {"1", "true", "on", "yes"}:
            enabled = True
        elif value in {"0", "false", "off", "no"}:
            enabled = False
        else:
            return jsonify({"error": "tts_enabled is required"}), 400

    return jsonify({"ok": True, "tts_enabled": set_tts_enabled(enabled)})


@admin_bp.route("/admin/languages", methods=["GET", "POST"])
def admin_languages():
    if request.method == "GET":
        return jsonify(languages_response())

    payload = request.get_json(silent=True) or {}

    raw = payload.get("enabled_languages")
    if raw is None:
        raw = payload.get("languages")
    try:
        enabled = set_enabled_study_languages(
            raw if raw is not None else get_enabled_study_languages()
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(languages_response() | {"enabled_languages": enabled})


@admin_bp.route("/admin/public-status", methods=["GET"])
def admin_public_status():
    return jsonify({"ok": True, **get_public_status()})


@admin_bp.route("/admin/toggle-public", methods=["POST"])
def admin_toggle_public():
    payload = request.get_json(silent=True) or {}

    raw = payload.get("public_enabled")
    if isinstance(raw, bool):
        enabled = raw
    else:
        value = str(raw or "").strip().lower()
        if value in {"1", "true", "on", "yes"}:
            enabled = True
        elif value in {"0", "false", "off", "no"}:
            enabled = False
        else:
            return jsonify({"error": "public_enabled is required"}), 400

    status = set_public_status(enabled, admin_user="admin")
    return jsonify({"ok": True, **status})


@admin_bp.route("/admin/password-check", methods=["POST"])
def admin_password_check():
    payload = request.get_json(silent=True) or {}
    denied = check_admin_password_attempt(
        payload.get("admin_password"),
        matches=lambda value: _admin_password_ok({"admin_password": value}),
        configured=_get_admin_password,
    )
    if denied:
        return denied
    return jsonify({"ok": True})


@admin_bp.route("/admin/sections", methods=["GET", "POST"])
def admin_sections():
    if request.method == "GET":
        return jsonify(sections_response())

    payload = request.get_json(silent=True) or {}
    raw = payload.get("visible_sections")
    if raw is None:
        raw = payload.get("sections")
    try:
        visible = set_visible_sections(raw if raw is not None else {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(sections_response() | {"visible_sections": visible})


@admin_bp.route("/admin/appearance", methods=["GET", "POST"])
def admin_appearance():
    if request.method == "GET":
        return jsonify(appearance_response())

    payload = request.get_json(silent=True) or {}
    updates = {}
    if "background_id" in payload:
        updates["background_id"] = payload.get("background_id")
    if "background_opacity" in payload:
        updates["background_opacity"] = payload.get("background_opacity")
    if updates:
        update_runtime_settings(**updates)
    return jsonify(appearance_response())
