"""Vibe Speak Trigger: 管理画面 Blueprint。

テーマプール管理・AIモデル選択（コスト管理）・問題数/トピック数設定・
生徒名簿・完了セッション（総合評価レポート）閲覧をすべてここに含む。
"""
import io
from pathlib import Path

import openpyxl
from flask import Blueprint, current_app, jsonify, render_template, request, send_file, send_from_directory

from trigger.config import (
    ADMIN_PASSWORD,
    QA_QUESTION_COUNT_RANGE,
    SPEECH_TOPIC_COUNT_RANGE,
    TASK_KEYS,
    TASK_LABELS,
    get_openai_api_key,
)
from trigger.cost_estimate import estimate_session_cost_usd
from trigger.model_catalog import public_ai_model_modes
from trigger.model_pricing import WHISPER_MODEL_PRICING
from trigger.scoring.rubric import VERSANT_CATEGORIES, VERSANT_LABELS
from trigger.storage import (
    add_or_update_student,
    add_or_update_theme,
    delete_student,
    delete_submission,
    delete_theme,
    get_submissions,
    import_students_from_excel,
    load_settings,
    load_students,
    load_themes,
    update_settings,
)

admin_bp = Blueprint(
    "trigger_admin",
    __name__,
    url_prefix="/trigger/admin",
    template_folder="../templates",
)


def _require_password(payload: dict):
    if str(payload.get("admin_password") or "") != ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "管理者パスワードが違います。"}), 403
    return None


def _settings_payload() -> dict:
    settings = load_settings()
    return {
        "ok": True,
        **settings,
        "task_keys": list(TASK_KEYS),
        "task_labels": TASK_LABELS,
        "ai_model_modes": public_ai_model_modes(),
        "whisper_models": [{"id": k, **v} for k, v in WHISPER_MODEL_PRICING.items()],
        "qa_question_count_range": list(QA_QUESTION_COUNT_RANGE),
        "speech_topic_count_range": list(SPEECH_TOPIC_COUNT_RANGE),
        "versant_categories": [{"id": c, "label": VERSANT_LABELS[c]} for c in VERSANT_CATEGORIES],
        "cost_estimate": estimate_session_cost_usd(settings),
        "api_key_configured": bool(get_openai_api_key()),
    }


@admin_bp.route("/manifest.json")
def web_app_manifest():
    """管理画面用 PWA manifest（start_url / scope: /trigger/admin/）。"""
    response = send_from_directory(
        Path(current_app.static_folder) / "trigger" / "admin",
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@admin_bp.route("/")
def admin_page():
    return render_template(
        "trigger/admin/index.html",
        themes=load_themes(),
        students=load_students(),
        submissions=get_submissions(),
    )


# ── 設定（AIモデル選択・問題数/トピック数） ────────────────

@admin_bp.route("/api/settings", methods=["GET"])
def get_settings_api():
    return jsonify(_settings_payload())


@admin_bp.route("/api/settings", methods=["POST"])
def save_settings_api():
    payload = request.get_json(silent=True) or {}
    changes_model = "task_model_modes" in payload
    if changes_model:
        err = _require_password(payload)
        if err:
            return err

    updates = {}
    if "task_model_modes" in payload:
        updates["task_model_modes"] = payload.get("task_model_modes")
    if "whisper_model" in payload:
        updates["whisper_model"] = payload.get("whisper_model")
    if "qa_question_count" in payload:
        updates["qa_question_count"] = payload.get("qa_question_count")
    if "speech_topic_count" in payload:
        updates["speech_topic_count"] = payload.get("speech_topic_count")
    if "speech_topic_tts_enabled" in payload:
        updates["speech_topic_tts_enabled"] = payload.get("speech_topic_tts_enabled")
    if "student_info_required" in payload:
        updates["student_info_required"] = payload.get("student_info_required")
    if "versant_weights" in payload:
        updates["versant_weights"] = payload.get("versant_weights")

    update_settings(**updates)
    return jsonify(_settings_payload())


@admin_bp.route("/api/cost-estimate", methods=["POST"])
def cost_estimate_preview_api():
    """保存前の設定値でコスト概算をプレビューする。"""
    payload = request.get_json(silent=True) or {}
    current = load_settings()
    preview = {**current, **{k: v for k, v in payload.items() if k in current}}
    return jsonify({"ok": True, "cost_estimate": estimate_session_cost_usd(preview)})


# ── テーマプール ────────────────────────────────────────────

@admin_bp.route("/api/themes", methods=["GET"])
def list_themes_api():
    return jsonify({"ok": True, "themes": load_themes()})


@admin_bp.route("/api/themes", methods=["POST"])
def upsert_theme_api():
    payload = request.get_json(silent=True) or {}
    theme = payload.get("theme") or {}
    if not str(theme.get("title") or "").strip():
        return jsonify({"ok": False, "error": "テーマ名を入力してください。"}), 400
    themes = add_or_update_theme(theme)
    return jsonify({"ok": True, "themes": themes})


@admin_bp.route("/api/themes/<theme_id>", methods=["DELETE"])
def delete_theme_api(theme_id):
    themes = delete_theme(theme_id)
    return jsonify({"ok": True, "themes": themes})


# ── 生徒名簿（roster） ──────────────────────────────────────

@admin_bp.route("/api/students", methods=["GET"])
def list_students_api():
    return jsonify({"ok": True, "students": load_students()})


@admin_bp.route("/api/students/upload", methods=["POST"])
def upload_students_api():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "ファイルが選択されていません。"}), 400
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({"ok": False, "error": ".xlsx または .xls ファイルを選択してください。"}), 400
    try:
        students = import_students_from_excel(file.read())
        return jsonify({"ok": True, "students": students, "count": len(students)})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"読み込みエラー: {exc}"}), 500


@admin_bp.route("/api/students", methods=["POST"])
def upsert_student_api():
    payload = request.get_json(silent=True) or {}
    student = payload.get("student") or {}
    try:
        students = add_or_update_student(student)
        return jsonify({"ok": True, "students": students})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 400


@admin_bp.route("/api/students/<student_id>", methods=["DELETE"])
def delete_student_api(student_id):
    students = delete_student(student_id)
    return jsonify({"ok": True, "students": students})


# ── 完了セッション（総合評価レポート） ──────────────────────

@admin_bp.route("/api/submissions", methods=["GET"])
def list_submissions_api():
    return jsonify({"ok": True, "submissions": get_submissions()})


@admin_bp.route("/api/submissions/<submission_id>", methods=["DELETE"])
def delete_submission_api(submission_id):
    ok = delete_submission(submission_id)
    if not ok:
        return jsonify({"ok": False, "error": "データが見つかりません。"}), 404
    return jsonify({"ok": True})


@admin_bp.route("/api/submissions/export", methods=["GET"])
def export_submissions_api():
    submissions = get_submissions()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "総合評価レポート"
    headers = [
        "提出日時",
        "クラス",
        "番号",
        "氏名",
        "テーマ",
        "総合スコア(0-90)",
        "CEFRレベル",
        "Sentence Mastery",
        "Vocabulary",
        "Fluency",
        "Pronunciation",
        "Comprehension",
    ]
    ws.append(headers)
    for s in submissions:
        student_info = s.get("student_info") or {}
        final_eval = s.get("final_evaluation") or {}
        scores90 = final_eval.get("versant_scores_90") or {}
        ws.append(
            [
                s.get("submitted_at", ""),
                student_info.get("class_name", ""),
                student_info.get("number", ""),
                student_info.get("name", ""),
                s.get("theme_title", ""),
                final_eval.get("overall_score_90", ""),
                final_eval.get("cefr_level", ""),
                scores90.get("sentence_mastery", ""),
                scores90.get("vocabulary", ""),
                scores90.get("fluency", ""),
                scores90.get("pronunciation", ""),
                scores90.get("comprehension", ""),
            ]
        )
    for i in range(1, len(headers) + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 14

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name="trigger_submissions.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
