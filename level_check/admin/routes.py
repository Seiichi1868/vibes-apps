"""Speaking Level Check Test: 管理画面 Blueprint。

roster 管理・問題バンク編集・結果閲覧・設定切替をすべてここに含む。
"""
import io
import logging
from pathlib import Path

import openpyxl
from flask import Blueprint, jsonify, render_template, request, send_file, send_from_directory

from level_check.config import (
    AI_MODEL_MODES,
    BACKGROUND_IMAGE_STATIC_PATH,
    CATEGORIES,
    CATEGORY_LABELS,
    INFO_LEVEL_LABELS,
    INFO_LEVELS,
    ADMIN_PASSWORD,
    get_openai_api_key,
    resolve_ai_model_id,
)
from level_check.scoring.rubric import (
    DEFAULT_LISTENING_RUBRIC,
    DEFAULT_SPEAKING_RUBRIC,
    LISTENING_AXES,
    SPEAKING_AXES,
)
from level_check.pdf_report import build_submissions_pdf
from level_check.storage import (
    QUESTION_PRIMARY_FIELD,
    add_or_update_student,
    add_questions,
    delete_question,
    delete_student,
    delete_submission,
    get_submission,
    get_submissions,
    import_students_from_excel,
    load_questions,
    load_settings,
    load_students,
    update_question,
    update_settings,
)
from level_check.tasks.definitions import TASK_DEFINITIONS
from level_check.tasks.generator import generate_questions
from level_check.tts import ensure_prompt_audio, synthesize_prompt, tts_text_for_question

logger = logging.getLogger(__name__)

admin_bp = Blueprint(
    "level_check_admin",
    __name__,
    url_prefix="/level_check/admin",
    template_folder="../templates",
)


def _require_model_change_password(payload: dict):
    """AIモデル選択（管理設定）の変更時のみパスワードを要求する。"""
    if str(payload.get("admin_password") or "") != ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "管理設定のパスワードが違います。"}), 403
    return None


def _settings_payload() -> dict:
    settings = load_settings()
    return {
        "ok": True,
        **settings,
        "ai_model_modes": [{"id": k, **v} for k, v in AI_MODEL_MODES.items()],
        "info_levels": [{"id": lvl, "label": INFO_LEVEL_LABELS[lvl]} for lvl in INFO_LEVELS],
        "speaking_rubric_defaults": {axis: DEFAULT_SPEAKING_RUBRIC[axis] for axis in SPEAKING_AXES},
        "listening_rubric_defaults": {axis: DEFAULT_LISTENING_RUBRIC[axis] for axis in LISTENING_AXES},
        "rubric_defaults": {axis: DEFAULT_SPEAKING_RUBRIC[axis] for axis in SPEAKING_AXES},
        "categories": [{"id": c, "label": CATEGORY_LABELS[c]} for c in CATEGORIES],
        "api_key_configured": bool(get_openai_api_key()),
    }


@admin_bp.route("/manifest.json")
def web_app_manifest():
    """管理画面用 PWA manifest（start_url / scope: /level_check/admin/）。"""
    response = send_from_directory(
        Path(admin_bp.root_path).parent / "static" / "admin",
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@admin_bp.route("/")
def admin_page():
    bank = load_questions()
    settings = load_settings()
    return render_template(
        "level_check/admin/index.html",
        settings=settings,
        ai_model_modes=AI_MODEL_MODES,
        info_levels=INFO_LEVELS,
        info_level_labels=INFO_LEVEL_LABELS,
        task_definitions=TASK_DEFINITIONS,
        category_labels=CATEGORY_LABELS,
        categories=CATEGORIES,
        question_bank=bank,
        background_opacity=settings.get("background_opacity"),
        background_image=BACKGROUND_IMAGE_STATIC_PATH,
    )


# ── 設定 ────────────────────────────────────────────────────

@admin_bp.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(_settings_payload())


@admin_bp.route("/api/settings", methods=["POST"])
def save_settings_api():
    payload = request.get_json(silent=True) or {}
    updates = {}
    if "speaking_rubric_weights" in payload:
        updates["speaking_rubric_weights"] = payload.get("speaking_rubric_weights")
    elif "rubric_weights" in payload:
        updates["speaking_rubric_weights"] = payload.get("rubric_weights")
    if "listening_rubric_weights" in payload:
        updates["listening_rubric_weights"] = payload.get("listening_rubric_weights")
    if "overall_weights" in payload:
        updates["overall_weights"] = payload.get("overall_weights")
    if "student_info_level" in payload:
        updates["student_info_level"] = payload.get("student_info_level")
    if "questions_per_category" in payload:
        updates["questions_per_category"] = payload.get("questions_per_category")
    if "background_opacity" in payload:
        updates["background_opacity"] = payload.get("background_opacity")
    if "ai_model_mode" in payload:
        err = _require_model_change_password(payload)
        if err:
            return err
        updates["ai_model_mode"] = payload.get("ai_model_mode")
    update_settings(**updates)
    return jsonify(_settings_payload())


# ── 生徒名簿（roster） ──────────────────────────────────────

@admin_bp.route("/api/students", methods=["GET"])
def list_students():
    return jsonify({"ok": True, "students": load_students()})


@admin_bp.route("/api/students/upload", methods=["POST"])
def upload_students():
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
def upsert_student():
    payload = request.get_json(silent=True) or {}
    student = payload.get("student") or {}
    try:
        students = add_or_update_student(student)
        return jsonify({"ok": True, "students": students})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 400


@admin_bp.route("/api/students/<student_id>", methods=["DELETE"])
def remove_student(student_id):
    students = delete_student(student_id)
    return jsonify({"ok": True, "students": students})


# ── 問題バンク ──────────────────────────────────────────────

@admin_bp.route("/api/questions", methods=["GET"])
def list_questions():
    return jsonify({"ok": True, "questions": load_questions()})


@admin_bp.route("/api/questions/<task_type>", methods=["POST"])
def add_question(task_type):
    cat = str(task_type or "").strip().upper()
    if cat not in QUESTION_PRIMARY_FIELD:
        return jsonify({"ok": False, "error": f"不明なカテゴリ: {task_type}"}), 400
    payload = request.get_json(silent=True) or {}
    item = payload.get("item") or {}
    bank = add_questions(cat, [item])
    return jsonify({"ok": True, "questions": bank})


@admin_bp.route("/api/questions/<task_type>/<question_id>", methods=["POST"])
def edit_question(task_type, question_id):
    cat = str(task_type or "").strip().upper()
    if cat not in QUESTION_PRIMARY_FIELD:
        return jsonify({"ok": False, "error": f"不明なカテゴリ: {task_type}"}), 400
    payload = request.get_json(silent=True) or {}
    updates = payload.get("item") or {}
    try:
        bank = update_question(cat, question_id, updates)
        return jsonify({"ok": True, "questions": bank})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@admin_bp.route("/api/questions/<task_type>/<question_id>", methods=["DELETE"])
def remove_question(task_type, question_id):
    cat = str(task_type or "").strip().upper()
    if cat not in QUESTION_PRIMARY_FIELD:
        return jsonify({"ok": False, "error": f"不明なカテゴリ: {task_type}"}), 400
    bank = delete_question(cat, question_id)
    return jsonify({"ok": True, "questions": bank})


@admin_bp.route("/api/questions/<task_type>/generate", methods=["POST"])
def generate_questions_api(task_type):
    cat = str(task_type or "").strip().upper()
    if cat not in QUESTION_PRIMARY_FIELD:
        return jsonify({"ok": False, "error": f"不明なカテゴリ: {task_type}"}), 400

    payload = request.get_json(silent=True) or {}
    try:
        count = max(1, min(15, int(payload.get("count", 5))))
    except (TypeError, ValueError):
        count = 5

    api_key = get_openai_api_key()
    if not api_key:
        return jsonify({"ok": False, "error": "OpenAI API キーが未設定です。"}), 400

    settings = load_settings()
    model = resolve_ai_model_id(settings.get("ai_model_mode"))
    field = QUESTION_PRIMARY_FIELD[cat]
    existing_texts = [item.get(field, "") for item in load_questions().get(cat, [])]

    try:
        generated = generate_questions(
            task_type=cat, count=count, model=model, api_key=api_key, existing_texts=existing_texts
        )
        # TTS を可能な範囲で事前生成（失敗しても問題登録は続行）
        for item in generated:
            text = tts_text_for_question(cat, item)
            if text:
                url = ensure_prompt_audio(text)
                if url:
                    item["prompt_audio_key"] = url.rsplit("/", 1)[-1].replace(".mp3", "")
        bank = add_questions(cat, generated)
        return jsonify({"ok": True, "questions": bank, "generated_count": len(generated)})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"生成に失敗しました: {exc}"}), 500


@admin_bp.route("/api/questions/<task_type>/<question_id>/tts", methods=["POST"])
def regenerate_question_tts(task_type, question_id):
    cat = str(task_type or "").strip().upper()
    if cat not in QUESTION_PRIMARY_FIELD:
        return jsonify({"ok": False, "error": f"不明なカテゴリ: {task_type}"}), 400
    bank = load_questions()
    item = next((q for q in bank.get(cat, []) if q.get("id") == question_id), None)
    if not item:
        return jsonify({"ok": False, "error": "問題が見つかりません。"}), 404
    text = tts_text_for_question(cat, item)
    if not text:
        return jsonify({"ok": False, "error": "このカテゴリには音声プロンプトがありません。"}), 400
    try:
        key, cached = synthesize_prompt(text, force=True)
        update_question(cat, question_id, {"prompt_audio_key": key})
        return jsonify({"ok": True, "prompt_audio_key": key, "cached": cached})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


# ── 受験結果 ────────────────────────────────────────────────

@admin_bp.route("/api/submissions", methods=["GET"])
def list_submissions():
    return jsonify({"ok": True, "submissions": get_submissions()})


@admin_bp.route("/api/submissions/<submission_id>", methods=["DELETE"])
def remove_submission(submission_id):
    ok = delete_submission(submission_id)
    if not ok:
        return jsonify({"ok": False, "error": "データが見つかりません。"}), 404
    return jsonify({"ok": True})


def _axis_from_overall(overall: dict, track: str, axis: str):
    axes = (overall or {}).get(f"{track}_axes") or {}
    return axes.get(axis, "")


def _latency_average(task_results: list[dict]) -> float | None:
    values = [r.get("response_latency_ms") for r in task_results if r.get("response_latency_ms") is not None]
    if not values:
        return None
    return round(sum(values) / len(values))


@admin_bp.route("/api/submissions/export", methods=["GET"])
def export_submissions():
    submissions = get_submissions()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "受験結果"
    headers = [
        "提出日時",
        "情報レベル",
        "クラス",
        "番号",
        "氏名",
        "Speaking Level Score",
        "総合CEFR帯",
        "スピーキングサブスコア",
        "リスニングサブスコア",
        "A.質問応答",
        "B.復唱",
        "C.会話理解",
        "D.文章理解",
        "E.要約リテリング",
        "F.自由回答",
        "流暢さ",
        "発音・明瞭性",
        "文法的正確性",
        "語彙運用",
        "応答速度スコア",
        "内容理解",
        "応答の的確さ",
        "平均応答速度(ms)",
        "使用AIモデル",
    ]
    ws.append(headers)

    for s in submissions:
        task_results = s.get("task_results") or []
        student_info = s.get("student_info") or {}
        overall = s.get("overall") or {}
        category_scores = overall.get("category_scores") or {}
        ws.append(
            [
                s.get("submitted_at", ""),
                s.get("info_level", ""),
                student_info.get("class_name", ""),
                student_info.get("number", ""),
                student_info.get("name", ""),
                overall.get("speaking_level_score", overall.get("score_100", "")),
                overall.get("cefr_band", ""),
                overall.get("speaking_subscore", ""),
                overall.get("listening_subscore", ""),
                category_scores.get("A", ""),
                category_scores.get("B", ""),
                category_scores.get("C", ""),
                category_scores.get("D", ""),
                category_scores.get("E", ""),
                category_scores.get("F", ""),
                _axis_from_overall(overall, "speaking", "fluency"),
                _axis_from_overall(overall, "speaking", "pronunciation"),
                _axis_from_overall(overall, "speaking", "accuracy"),
                _axis_from_overall(overall, "speaking", "vocabulary"),
                _axis_from_overall(overall, "speaking", "response_latency"),
                _axis_from_overall(overall, "listening", "comprehension_accuracy"),
                _axis_from_overall(overall, "listening", "response_relevance"),
                _latency_average(task_results),
                s.get("ai_model_mode", ""),
            ]
        )

    for i in range(1, len(headers) + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 12

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name="level_check_submissions.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _ascii_safe_filename(value: str, fallback: str = "report") -> str:
    """Content-Disposition に安全に載せられる ASCII のみのファイル名断片を作る。"""
    ascii_only = "".join(ch for ch in str(value or "") if ch.isascii() and (ch.isalnum() or ch in ("-", "_")))
    ascii_only = ascii_only[:40]
    return ascii_only or fallback


def _pdf_response(submissions: list[dict], *, download_name: str, inline: bool = False):
    pdf_bytes = build_submissions_pdf(submissions)
    buf = io.BytesIO(pdf_bytes)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=not inline,
        download_name=download_name,
        mimetype="application/pdf",
    )


@admin_bp.route("/api/submissions/<submission_id>/pdf", methods=["GET"])
def export_submission_pdf(submission_id):
    """個別受験の評価個票 PDF。"""
    try:
        submission = get_submission(submission_id)
        if not submission:
            return jsonify({"ok": False, "error": "データが見つかりません。"}), 404
        student = submission.get("student_info") or {}
        safe_name = _ascii_safe_filename(student.get("name"), fallback="")
        if not safe_name:
            safe_name = _ascii_safe_filename(
                f"{student.get('class_name')}_{student.get('number')}",
                fallback=submission.get("id") or "student",
            )
        return _pdf_response(
            [submission],
            download_name=f"level_check_{safe_name}.pdf",
            inline=True,
        )
    except Exception:
        logger.exception("個別PDFの生成に失敗しました: submission_id=%s", submission_id)
        return jsonify({"ok": False, "error": "PDFの生成に失敗しました。"}), 500


@admin_bp.route("/api/submissions/pdf", methods=["POST"])
def export_submissions_pdf_bulk():
    """選択した受験結果の評価個票を1つの PDF にまとめてダウンロード。"""
    try:
        payload = request.get_json(silent=True) or {}
        ids = payload.get("ids") or []
        if not isinstance(ids, list) or not ids:
            return jsonify({"ok": False, "error": "受験結果が選択されていません。"}), 400

        wanted = {str(i) for i in ids if i}
        by_id = {}
        for submission in get_submissions():
            sid = str(submission.get("id") or "")
            if sid in wanted:
                by_id[sid] = submission

        ordered = [by_id[str(i)] for i in ids if str(i) in by_id]
        if not ordered:
            return jsonify({"ok": False, "error": "対象の受験結果が見つかりません。"}), 404

        return _pdf_response(
            ordered,
            download_name=f"level_check_reports_{len(ordered)}.pdf",
            inline=False,
        )
    except Exception:
        logger.exception("一括PDFの生成に失敗しました")
        return jsonify({"ok": False, "error": "PDFの生成に失敗しました。"}), 500
