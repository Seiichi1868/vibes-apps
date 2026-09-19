"""Debate app 管理画面 Blueprint（背景・透過率の設定、保存済みセッションの一覧・削除）。"""
import os

from flask import Blueprint, jsonify, render_template, request

from debate.judge_models import public_judge_model_modes, resolve_judge_model_mode
from debate.settings import (
    BACKGROUND_PRESETS,
    DEFAULT_BACKGROUND_OPACITY,
    TRANSCRIPTION_MODES,
    _clamp_opacity,
    load_settings,
    resolve_background,
    resolve_judge_model,
    resolve_opponent_model,
    update_settings,
)
from debate.storage import copy_session, delete_session, list_sessions, update_session_notes

debate_admin_bp = Blueprint("debate_admin", __name__, url_prefix="/debate/admin")

ADMIN_PASSWORD = os.environ.get("DEBATE_ADMIN_PASSWORD", "2479")

# パスワードが必要な設定キー（AIモデル・文字起こし方式）
_SENSITIVE_SETTING_KEYS = ("transcription_mode", "judge_model_mode", "opponent_model_mode")


def _password_ok(payload: dict) -> bool:
    return str(payload.get("admin_password") or "") == ADMIN_PASSWORD


def _settings_response(settings: dict) -> dict:
    judge_mode = resolve_judge_model_mode(settings.get("judge_model_mode"))
    opponent_mode = resolve_judge_model_mode(settings.get("opponent_model_mode"))
    return {
        "ok": True,
        **settings,
        **resolve_background(settings.get("background_id")),
        "judge_model": resolve_judge_model(judge_mode),
        "judge_model_modes": public_judge_model_modes(),
        "opponent_model": resolve_opponent_model(opponent_mode),
        "opponent_model_mode": opponent_mode,
    }


@debate_admin_bp.route("")
def admin_page():
    settings = load_settings()
    bg = resolve_background(settings.get("background_id"))
    return render_template(
        "debate/admin.html",
        backgrounds=BACKGROUND_PRESETS,
        background=bg,
        background_opacity=settings.get("background_opacity", DEFAULT_BACKGROUND_OPACITY),
    )


@debate_admin_bp.route("/api/settings", methods=["GET", "POST"])
def admin_settings():
    if request.method == "GET":
        return jsonify(_settings_response(load_settings()))

    payload = request.get_json(silent=True) or {}
    has_sensitive = any(key in payload for key in _SENSITIVE_SETTING_KEYS)
    if has_sensitive and not _password_ok(payload):
        return jsonify({"ok": False, "error": "管理パスワードが違います。"}), 403

    updates = {}
    if "background_id" in payload:
        bg_id = str(payload.get("background_id") or "")
        if bg_id in BACKGROUND_PRESETS:
            updates["background_id"] = bg_id
    if "background_opacity" in payload:
        updates["background_opacity"] = _clamp_opacity(payload.get("background_opacity"))
    if "transcription_mode" in payload:
        mode = str(payload.get("transcription_mode") or "")
        if mode in TRANSCRIPTION_MODES:
            updates["transcription_mode"] = mode
    if "judge_model_mode" in payload:
        judge_mode = str(payload.get("judge_model_mode") or "")
        if judge_mode in {mode["id"] for mode in public_judge_model_modes()}:
            updates["judge_model_mode"] = judge_mode
    if "opponent_model_mode" in payload:
        opponent_mode = str(payload.get("opponent_model_mode") or "")
        if opponent_mode in {mode["id"] for mode in public_judge_model_modes()}:
            updates["opponent_model_mode"] = opponent_mode

    if not updates:
        # パスワード確認のみ（管理設定の解除）
        if has_sensitive or _password_ok(payload):
            return jsonify(_settings_response(load_settings()))
        return jsonify({"ok": False, "error": "管理パスワードが違います。"}), 403

    return jsonify(_settings_response(update_settings(**updates)))


# ── 保存済みセッション一覧（途中まで進めたディベートの再開・削除） ──────
@debate_admin_bp.route("/api/sessions", methods=["GET"])
def admin_list_sessions():
    return jsonify({"ok": True, "sessions": list_sessions(limit=500, include_notes=True)})


@debate_admin_bp.route("/api/sessions/<session_id>/copy", methods=["POST"])
def admin_copy_session(session_id):
    payload = request.get_json(silent=True) or {}
    copied = copy_session(session_id, notes=str(payload.get("notes") or ""))
    if not copied:
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404
    return jsonify(
        {
            "ok": True,
            "session_id": copied["session_id"],
            "admin_notes": copied.get("admin_notes", ""),
        }
    )


@debate_admin_bp.route("/api/sessions/<session_id>/notes", methods=["POST"])
def admin_update_session_notes(session_id):
    payload = request.get_json(silent=True) or {}
    updated = update_session_notes(session_id, notes=str(payload.get("notes") or ""))
    if not updated:
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404
    return jsonify({"ok": True, "admin_notes": updated.get("admin_notes", "")})


@debate_admin_bp.route("/api/sessions/<session_id>/delete", methods=["POST"])
def admin_delete_session(session_id):
    deleted = delete_session(session_id)
    if not deleted:
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404
    return jsonify({"ok": True})
