"""Vibe Speak Conjugate: 管理画面Blueprint。

出題カテゴリ・文型、ASRエンジン（Whisper/Web Speech API）・Whisperモデル、
判定の厳しさ、1問あたりの出題数・対象文型数、gustar特殊構文モードの
頻度、弱点動詞優先出題の有無を切り替えられる。
"""
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_from_directory

from conjugate.appearance import appearance_context
from conjugate.config import (
    ADMIN_PASSWORD,
    ASR_ENGINES,
    STRICTNESS_MODES,
    WHISPER_MODELS,
    get_openai_api_key,
)
from conjugate.data.conjugations import TENSE_LABELS, TENSE_ORDER, derived_person_rows, gustar_derived_rows
from conjugate.data.gustar import GUSTAR_EXAMPLES
from conjugate.data.persons import PERSON_MODE_LABELS, PERSON_MODES
from conjugate.data.verbs import CATEGORY_LABELS, CATEGORY_ORDER, drillable_verbs
from conjugate.storage import get_submissions, load_settings, save_settings, weak_verbs_report

admin_bp = Blueprint(
    "conjugate_admin",
    __name__,
    url_prefix="/conjugate/admin",
    template_folder="../templates",
)


@admin_bp.context_processor
def _inject_appearance():
    return appearance_context()


@admin_bp.route("/manifest.json")
def web_app_manifest():
    """管理画面用 PWA。start_url を /conjugate/admin/ に固定する。"""
    response = send_from_directory(
        Path(admin_bp.root_path).parent / "static" / "admin",
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


def _require_admin_password(payload: dict):
    if str(payload.get("admin_password") or "") != ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "管理パスワードが違います。"}), 403
    return None


def _settings_payload() -> dict:
    settings = load_settings()
    verb_counts = {cat: 0 for cat in CATEGORY_ORDER}
    for v in drillable_verbs():
        verb_counts[v["category"]] = verb_counts.get(v["category"], 0) + 1

    return {
        "ok": True,
        **settings,
        "categories": [{"id": c, "label": CATEGORY_LABELS[c], "verb_count": verb_counts.get(c, 0)} for c in CATEGORY_ORDER],
        "tenses": [{"id": t, "label": TENSE_LABELS[t]} for t in TENSE_ORDER],
        "person_modes": [{"id": p, "label": PERSON_MODE_LABELS[p]} for p in PERSON_MODES],
        "asr_engines": [
            {"id": "whisper", "label": "Whisper API（既定・Chrome/Safari両対応）"},
            {"id": "web_speech", "label": "Web Speech API（Chrome限定・低遅延モード）"},
        ],
        "whisper_models": [{"id": k, **v} for k, v in WHISPER_MODELS.items()],
        "strictness_modes": [
            {"id": "lenient", "label": "寛容モード（アクセント・表記ゆれを許容）"},
            {"id": "strict", "label": "厳密モード（アクセントの違いも指摘）"},
        ],
        "gustar_example_count": len(GUSTAR_EXAMPLES),
        "total_drillable_verbs": len(drillable_verbs()),
        "api_key_configured": bool(get_openai_api_key()),
    }


@admin_bp.route("/")
def admin_page():
    settings = load_settings()
    return render_template(
        "conjugate/admin/index.html",
        settings=settings,
        category_labels=CATEGORY_LABELS,
        category_order=CATEGORY_ORDER,
        tense_labels=TENSE_LABELS,
        tense_order=TENSE_ORDER,
        person_modes=PERSON_MODES,
        person_mode_labels=PERSON_MODE_LABELS,
        asr_engines=ASR_ENGINES,
        strictness_modes=STRICTNESS_MODES,
        whisper_models=WHISPER_MODELS,
        gustar_example_count=len(GUSTAR_EXAMPLES),
        api_key_configured=bool(get_openai_api_key()),
        recent_submissions=get_submissions(limit=15),
        weak_verbs=weak_verbs_report(limit=15),
    )


@admin_bp.route("/api/settings", methods=["GET"])
def get_settings_api():
    return jsonify(_settings_payload())


@admin_bp.route("/api/settings", methods=["POST"])
def save_settings_api():
    payload = request.get_json(silent=True) or {}
    guard = _require_admin_password(payload)
    if guard:
        return guard

    current = load_settings()
    updates = dict(current)
    for key in (
        "enabled_categories",
        "enabled_tenses",
        "asr_engine",
        "whisper_model",
        "strictness",
        "questions_per_session",
        "targets_per_question",
        "gustar_enabled",
        "gustar_per_session",
        "prioritize_weak_verbs",
        "person_mode",
        "background_id",
        "background_opacity",
        "opening_enabled",
        "opening_ms",
        "conjugation_mastery_threshold",
        "vocab_mastery_threshold",
        "guardian_price_coins",
    ):
        if key in payload:
            updates[key] = payload[key]

    saved = save_settings(updates)
    return jsonify({"ok": True, **saved})


@admin_bp.route("/api/submissions", methods=["GET"])
def submissions_api():
    return jsonify({"ok": True, "submissions": get_submissions(limit=50)})


@admin_bp.route("/api/weak-verbs", methods=["GET"])
def weak_verbs_api():
    return jsonify({"ok": True, "weak_verbs": weak_verbs_report(limit=30)})


@admin_bp.route("/persons")
def persons_debug_page():
    """tú形から自動導出した él/ella/usted形の全件一覧（目視確認用）。"""
    return render_template(
        "conjugate/admin/persons.html",
        rows=derived_person_rows(),
        gustar_rows=gustar_derived_rows(),
        tense_labels=TENSE_LABELS,
        tense_order=TENSE_ORDER,
    )
