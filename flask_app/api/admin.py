from flask import Blueprint, jsonify, request

from flask_app.config import Config
from flask_app.services.gate_service import set_gate_lock_enabled
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

admin_bp = Blueprint("admin", __name__)

ADMIN_SETTINGS_PASSWORD = "2479"


def _admin_password_ok(payload: dict) -> bool:
    return str(payload.get("admin_password") or "") == ADMIN_SETTINGS_PASSWORD


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
    if not _admin_password_ok(payload):
        return jsonify({"error": "管理設定のパスワードが違います。"}), 403

    raw_mode = payload.get("ai_mode")
    if raw_mode is None and payload.get("use_gpt5_mode") is not None:
        raw = payload.get("use_gpt5_mode")
        if isinstance(raw, bool):
            raw_mode = "5-mini" if raw else Config.DEFAULT_AI_MODE
        else:
            value = str(raw or "").strip().lower()
            raw_mode = "5-mini" if value in {"1", "true", "on", "yes"} else Config.DEFAULT_AI_MODE

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
    if not _admin_password_ok(payload):
        return jsonify({"error": "管理設定のパスワードが違います。"}), 403

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
    if not _admin_password_ok(payload):
        return jsonify({"error": "管理設定のパスワードが違います。"}), 403

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
