"""Debate app 管理画面 Blueprint（背景・透過率の設定、保存済みセッションの一覧・削除）。"""
import hmac
import os
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory

from debate.judge_models import public_judge_model_modes, resolve_judge_model_mode
from debate.config import (
    DEFAULT_MOTIONS,
    PART_ORDER,
    POI_PROTECTED_SEC_MAX,
    POI_PROTECTED_SEC_MIN,
    POI_PROTECTED_SEC_STEP,
)
from debate.settings import (
    BACKGROUND_PRESETS,
    DEFAULT_BACKGROUND_OPACITY,
    DEFAULT_SCRIPT_MODEL_MODE,
    TRANSCRIPTION_MODES,
    _clamp_opacity,
    add_affiliation,
    clamp_poi_protected_sec,
    delete_affiliation,
    format_poi_protected_label,
    list_affiliations,
    load_settings,
    rename_affiliation,
    resolve_background,
    resolve_judge_model,
    resolve_opponent_model,
    resolve_script_model,
    resolve_speech_mode,
    update_settings,
)
from debate.storage import copy_session, delete_session, list_sessions, update_session_notes

debate_admin_bp = Blueprint("debate_admin", __name__, url_prefix="/debate/admin")

_PASSWORD_UNSET = "管理パスワードが設定されていません。"
_PASSWORD_WRONG = "管理パスワードが違います。"


def get_admin_password() -> str:
    per_app = (os.environ.get("DEBATE_ADMIN_PASSWORD") or "").strip()
    if per_app:
        return per_app
    return (os.environ.get("ADMIN_PASSWORD") or "").strip()


def admin_password_matches(provided) -> bool:
    expected = get_admin_password()
    if not expected:
        return False
    return hmac.compare_digest(str(provided or ""), expected)

# パスワードが必要な設定キー（AIモデル・文字起こし方式・観戦スクリプト設定）
_SENSITIVE_SETTING_KEYS = (
    "transcription_mode",
    "judge_model_mode",
    "opponent_model_mode",
    "script_model_mode",
    "speech_mode",
)


def _password_ok(payload: dict) -> bool:
    return admin_password_matches((payload or {}).get("admin_password"))


def _admin_denied_response():
    if not get_admin_password():
        return jsonify({"ok": False, "error": _PASSWORD_UNSET}), 503
    return jsonify({"ok": False, "error": _PASSWORD_WRONG}), 403


def _protected_payload():
    payload = request.get_json(silent=True) or {}
    if not _password_ok(payload):
        return None, _admin_denied_response()
    return payload, None


def _settings_response(settings: dict) -> dict:
    judge_mode = resolve_judge_model_mode(settings.get("judge_model_mode"))
    opponent_mode = resolve_judge_model_mode(settings.get("opponent_model_mode"))
    script_mode = resolve_judge_model_mode(
        settings.get("script_model_mode"),
        fallback_mode=DEFAULT_SCRIPT_MODEL_MODE,
    )
    start_sec = clamp_poi_protected_sec(settings.get("poi_protected_start_sec"))
    end_sec = clamp_poi_protected_sec(settings.get("poi_protected_end_sec"))
    return {
        "ok": True,
        **settings,
        **resolve_background(settings.get("background_id")),
        "poi_protected_start_sec": start_sec,
        "poi_protected_end_sec": end_sec,
        "poi_protected_start_label": format_poi_protected_label(start_sec),
        "poi_protected_end_label": format_poi_protected_label(end_sec),
        "poi_protected_min": POI_PROTECTED_SEC_MIN,
        "poi_protected_max": POI_PROTECTED_SEC_MAX,
        "poi_protected_step": POI_PROTECTED_SEC_STEP,
        "judge_model": resolve_judge_model(judge_mode),
        "judge_model_modes": public_judge_model_modes(),
        "opponent_model": resolve_opponent_model(opponent_mode),
        "opponent_model_mode": opponent_mode,
        "script_model": resolve_script_model(script_mode),
        "script_model_mode": script_mode,
        "speech_mode": resolve_speech_mode(settings.get("speech_mode")),
    }


@debate_admin_bp.route("/manifest.json")
def web_app_manifest():
    """管理画面用 PWA manifest（start_url / scope: /debate/admin/）。"""
    response = send_from_directory(
        Path(current_app.static_folder) / "debate" / "admin",
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@debate_admin_bp.route("/", strict_slashes=False)
def admin_page():
    settings = load_settings()
    bg = resolve_background(settings.get("background_id"))
    start_sec = clamp_poi_protected_sec(settings.get("poi_protected_start_sec"))
    end_sec = clamp_poi_protected_sec(settings.get("poi_protected_end_sec"))
    return render_template(
        "debate/admin.html",
        backgrounds=BACKGROUND_PRESETS,
        background=bg,
        background_opacity=settings.get("background_opacity", DEFAULT_BACKGROUND_OPACITY),
        default_motions=DEFAULT_MOTIONS,
        poi_protected_start_sec=start_sec,
        poi_protected_end_sec=end_sec,
        poi_protected_start_label=format_poi_protected_label(start_sec),
        poi_protected_end_label=format_poi_protected_label(end_sec),
        poi_protected_min=POI_PROTECTED_SEC_MIN,
        poi_protected_max=POI_PROTECTED_SEC_MAX,
        poi_protected_step=POI_PROTECTED_SEC_STEP,
    )


@debate_admin_bp.route("/api/settings", methods=["GET", "POST"])
def admin_settings():
    if request.method == "GET":
        return jsonify(_settings_response(load_settings()))

    payload = request.get_json(silent=True) or {}
    has_sensitive = any(key in payload for key in _SENSITIVE_SETTING_KEYS)
    if has_sensitive and not _password_ok(payload):
        return _admin_denied_response()

    updates = {}
    if "background_id" in payload:
        bg_id = str(payload.get("background_id") or "")
        if bg_id in BACKGROUND_PRESETS:
            updates["background_id"] = bg_id
    if "background_opacity" in payload:
        updates["background_opacity"] = _clamp_opacity(payload.get("background_opacity"))
    if "poi_protected_start_sec" in payload:
        updates["poi_protected_start_sec"] = clamp_poi_protected_sec(payload.get("poi_protected_start_sec"))
    if "poi_protected_end_sec" in payload:
        updates["poi_protected_end_sec"] = clamp_poi_protected_sec(payload.get("poi_protected_end_sec"))
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
    if "script_model_mode" in payload:
        script_mode = str(payload.get("script_model_mode") or "")
        if script_mode in {mode["id"] for mode in public_judge_model_modes()}:
            updates["script_model_mode"] = script_mode
    if "speech_mode" in payload:
        speech_mode = str(payload.get("speech_mode") or "")
        if speech_mode in ("openai", "browser"):
            updates["speech_mode"] = speech_mode

    if not updates:
        # パスワード確認のみ（管理設定の解除）
        if has_sensitive or _password_ok(payload):
            return jsonify(_settings_response(load_settings()))
        return _admin_denied_response()

    return jsonify(_settings_response(update_settings(**updates)))


# ── 所属（生徒がディベート開始時に選ぶ選択肢） ────────────────
@debate_admin_bp.route("/api/affiliations", methods=["GET"])
def admin_list_affiliations():
    return jsonify({"ok": True, "affiliations": list_affiliations()})


@debate_admin_bp.route("/api/affiliations", methods=["POST"])
def admin_add_affiliation():
    payload = request.get_json(silent=True) or {}
    items, error = add_affiliation(str(payload.get("name") or ""))
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "affiliations": items})


@debate_admin_bp.route("/api/affiliations/<affiliation_id>", methods=["POST"])
def admin_rename_affiliation(affiliation_id):
    payload, denied = _protected_payload()
    if denied:
        return denied
    items, error = rename_affiliation(affiliation_id, str(payload.get("name") or ""))
    if error:
        status = 404 if error == "所属が見つかりません。" else 400
        return jsonify({"ok": False, "error": error}), status
    return jsonify({"ok": True, "affiliations": items})


@debate_admin_bp.route("/api/affiliations/<affiliation_id>/delete", methods=["POST"])
def admin_delete_affiliation(affiliation_id):
    _payload, denied = _protected_payload()
    if denied:
        return denied
    items, error = delete_affiliation(affiliation_id)
    if error:
        return jsonify({"ok": False, "error": error}), 404
    return jsonify({"ok": True, "affiliations": items})


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
    _payload, denied = _protected_payload()
    if denied:
        return denied
    deleted = delete_session(session_id)
    if not deleted:
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404
    return jsonify({"ok": True})


def _admin_password_from_request(payload: dict | None = None) -> bool:
    body = payload if isinstance(payload, dict) else {}
    header = request.headers.get("X-Debate-Admin-Password") or ""
    return _password_ok(body) or admin_password_matches(header)


# ── 観戦用スクリプト（生成・編集・公開。生徒画面の生成APIにはしない） ──
@debate_admin_bp.route("/api/scripts", methods=["GET"])
def admin_list_scripts():
    if not _admin_password_from_request():
        return _admin_denied_response()
    from debate.script_jobs import recover_stuck_scripts
    from debate.script_storage import list_scripts, script_admin_summary

    from debate.speech_jobs import recover_stuck_speech

    recover_stuck_scripts()
    recover_stuck_speech()
    return jsonify({"ok": True, "scripts": [script_admin_summary(item) for item in list_scripts()]})


@debate_admin_bp.route("/api/scripts", methods=["POST"])
def admin_create_script():
    payload, denied = _protected_payload()
    if denied:
        return denied
    motion = str(payload.get("motion") or "").strip()
    if not motion:
        return jsonify({"ok": False, "error": "論題を入力してください。"}), 400
    if len(motion) > 500:
        return jsonify({"ok": False, "error": "論題は500文字以内にしてください。"}), 400
    level = str(payload.get("level") or "normal").strip()
    winner = str(payload.get("intended_winner") or "auto").strip()
    model_mode = str(payload.get("model_mode") or payload.get("script_model_mode") or "").strip()
    if not model_mode:
        model_mode = load_settings().get("script_model_mode") or DEFAULT_SCRIPT_MODEL_MODE
    from debate.script_jobs import start_script_job

    try:
        script = start_script_job(motion, level, winner, model_mode)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    from debate.script_storage import script_admin_summary

    return jsonify({"ok": True, "script": script_admin_summary(script)})


@debate_admin_bp.route("/api/scripts/<script_id>", methods=["GET"])
def admin_get_script(script_id):
    if not _admin_password_from_request():
        return _admin_denied_response()
    from debate.script_storage import load_script

    script = load_script(script_id)
    if not script:
        return jsonify({"ok": False, "error": "スクリプトが見つかりません。"}), 404
    return jsonify({"ok": True, "script": script})


@debate_admin_bp.route("/api/scripts/<script_id>/parts/<part>", methods=["POST"])
def admin_update_script_part(script_id, part):
    payload, denied = _protected_payload()
    if denied:
        return denied
    if part not in PART_ORDER:
        return jsonify({"ok": False, "error": "パートが不正です。"}), 400
    from debate.ai_script import apply_part_text
    from debate.script_storage import get_script_lock, load_script, save_script

    with get_script_lock(script_id):
        script = load_script(script_id)
        if not script:
            return jsonify({"ok": False, "error": "スクリプトが見つかりません。"}), 404
        parts = script.get("parts") or []
        target = next((item for item in parts if item.get("part") == part), None)
        if not target:
            return jsonify({"ok": False, "error": "このパートはまだありません。"}), 400
        updated, part_warnings = apply_part_text(
            target, str(payload.get("text") or ""), script.get("level") or "normal"
        )
        script["parts"] = [updated if item.get("part") == part else item for item in parts]
        from debate.ai_script import warning_message

        warnings = [
            item
            for item in (script.get("warnings") or [])
            if not warning_message(item).startswith(f"{part}:")
        ]
        warnings.extend(part_warnings)
        script["warnings"] = warnings
        save_script(script)
    return jsonify({"ok": True, "script": script})


@debate_admin_bp.route("/api/scripts/<script_id>/note", methods=["POST"])
def admin_update_script_note(script_id):
    payload, denied = _protected_payload()
    if denied:
        return denied
    from debate.script_storage import get_script_lock, load_script, normalize_teacher_note, save_script

    with get_script_lock(script_id):
        script = load_script(script_id)
        if not script:
            return jsonify({"ok": False, "error": "スクリプトが見つかりません。"}), 404
        script["teacher_note"] = normalize_teacher_note(str(payload.get("teacher_note") or ""))
        save_script(script)
    return jsonify({"ok": True, "teacher_note": script.get("teacher_note") or ""})


@debate_admin_bp.route("/api/scripts/<script_id>/status", methods=["POST"])
def admin_update_script_status(script_id):
    payload, denied = _protected_payload()
    if denied:
        return denied
    status = str(payload.get("status") or "").strip()
    if status not in ("draft", "published"):
        return jsonify({"ok": False, "error": "状態は draft か published です。"}), 400
    from debate.script_storage import get_script_lock, load_script, save_script

    with get_script_lock(script_id):
        script = load_script(script_id)
        if not script:
            return jsonify({"ok": False, "error": "スクリプトが見つかりません。"}), 404
        if script.get("generation_status") != "draft":
            return jsonify({"ok": False, "error": "生成が終わったスクリプトだけ公開できます。"}), 400
        if not script.get("parts"):
            return jsonify({"ok": False, "error": "本文がないため公開できません。"}), 400
        script["status"] = status
        save_script(script)
    if status == "published" and resolve_speech_mode() == "openai":
        from debate.speech_jobs import queue_script_speech

        try:
            queue_script_speech(script_id)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "status": status})


@debate_admin_bp.route("/api/scripts/<script_id>/delete", methods=["POST"])
def admin_delete_script(script_id):
    _payload, denied = _protected_payload()
    if denied:
        return denied
    from debate.script_storage import delete_script

    if not delete_script(script_id):
        return jsonify({"ok": False, "error": "スクリプトが見つかりません。"}), 404
    return jsonify({"ok": True})


@debate_admin_bp.route("/api/scripts/<script_id>/preview-token", methods=["POST"])
def admin_script_preview_token(script_id):
    _payload, denied = _protected_payload()
    if denied:
        return denied
    from debate.script_storage import issue_preview_token, load_script

    script = load_script(script_id)
    if not script:
        return jsonify({"ok": False, "error": "スクリプトが見つかりません。"}), 404
    if script.get("generation_status") == "error":
        return jsonify({"ok": False, "error": "生成に失敗したためプレビューできません。"}), 409
    if script.get("generation_status") != "draft":
        return jsonify({"ok": False, "error": "まだ生成が終わっていません。"}), 409
    try:
        token = issue_preview_token(script_id)
    except RuntimeError:
        return jsonify({"ok": False, "error": "DEBATE_PREVIEW_SECRET が設定されていません。"}), 503
    return jsonify({"ok": True, "token": token})


@debate_admin_bp.route("/api/scripts/<script_id>/audio", methods=["POST"])
def admin_queue_script_audio(script_id):
    payload, denied = _protected_payload()
    if denied:
        return denied
    if resolve_speech_mode() != "openai":
        return jsonify({"ok": False, "error": "読み上げ方式がブラウザのため、サーバー音声は作りません。"}), 400
    part = str(payload.get("part") or "").strip()
    only = [part] if part else None
    from debate.speech_jobs import queue_script_speech
    from debate.script_storage import script_admin_summary

    try:
        script = queue_script_speech(script_id, only, force=bool(part))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "script": script_admin_summary(script)})


@debate_admin_bp.route("/api/scripts/<script_id>/checks/estimate", methods=["POST"])
def admin_estimate_script_check(script_id):
    payload, denied = _protected_payload()
    if denied:
        return denied
    from debate.script_checks import estimate_check_cost, parse_check_request
    from debate.script_storage import load_script

    script = load_script(script_id)
    if not script:
        return jsonify({"ok": False, "error": "スクリプトが見つかりません。"}), 404
    if script.get("generation_status") != "draft" or not script.get("parts"):
        return jsonify({"ok": False, "error": "生成が終わった本文があるスクリプトだけ照合できます。"}), 400
    try:
        modes, runs = parse_check_request(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "estimate": estimate_check_cost(script, modes, runs)})


@debate_admin_bp.route("/api/scripts/<script_id>/checks", methods=["GET"])
def admin_get_script_checks(script_id):
    if not _admin_password_from_request():
        return _admin_denied_response()
    from debate.script_check_jobs import checks_view
    from debate.script_storage import load_script

    if not load_script(script_id):
        return jsonify({"ok": False, "error": "スクリプトが見つかりません。"}), 404
    return jsonify({"ok": True, "checks": checks_view(script_id)})


@debate_admin_bp.route("/api/scripts/<script_id>/checks", methods=["POST"])
def admin_start_script_check(script_id):
    payload, denied = _protected_payload()
    if denied:
        return denied
    from debate.script_check_jobs import start_check_job

    if not payload.get("confirmed"):
        return jsonify({"ok": False, "error": "概算を確認してから実行してください。"}), 400
    try:
        checks = start_check_job(script_id, payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "checks": checks})
