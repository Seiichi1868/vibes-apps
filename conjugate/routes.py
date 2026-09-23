"""Vibe Speak Conjugate: 生徒（学習者）向けBlueprint。

  1. GET  /conjugate/                                    … トップ（統計・カテゴリ導線）
  2. GET  /conjugate/verbs                               … 動詞一覧（習得バッジ）
  3. GET  /conjugate/profile                             … 記録・履歴
  4. POST /conjugate/api/sessions                         … セッション作成（JS経由）
  4b.POST /conjugate/start                                … セッション作成（フォーム送信フォールバック）
  5. GET  /conjugate/session/<id>                         … 出題・録音画面
  6. POST /conjugate/api/sessions/<id>/questions/<qid>/targets/<t>/answer … 採点
  7. POST /conjugate/api/sessions/<id>/finish              … セッション終了・サマリ保存
  8. GET  /conjugate/session/<id>/summary                  … 結果画面
  9. GET  /conjugate/manifest.json                         … PWA manifest
 10. POST /conjugate/api/vocab                            … 語彙4択セッション作成
 11. GET  /conjugate/vocab/<id>                           … 語彙4択画面
 12. POST /conjugate/api/vocab/<id>/questions/<qid>/answer … 語彙4択の解答
 13. POST /conjugate/api/progress/daily-goal              … 1日の累計目標を保存
 14. GET  /conjugate/shop                                 … コインショップ（Guardián交換）
 15. POST /conjugate/api/progress/guardian/purchase        … Guardián購入（コイン消費）
 16. GET  /conjugate/tenses                               … 時制の解説一覧
 17. GET  /conjugate/tenses/<tense_id>                    … 時制ごとの解説
"""
import logging
import mimetypes
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from conjugate.appearance import appearance_context
from conjugate.audio_convert import audio_duration_sec, normalize_audio_file
from conjugate.config import (
    ALLOWED_AUDIO_EXTENSIONS,
    AUDIO_TMP_DIR,
    MAX_AUDIO_BYTES,
    ensure_dirs,
    whisper_cost_usd,
)
from conjugate.data.conjugations import TENSE_LABELS, TENSE_ORDER, default_selected_tenses, selectable_tenses
from conjugate.data.tense_guides import get_tense_guide, list_tense_guides
from conjugate.data.persons import (
    DEFAULT_PERSON_FILTER,
    EL_ELLA_USTED_HINT,
    PERSON_BADGE_LABELS,
    PERSON_FILTER_LABELS,
    PERSON_IDS,
    PERSON_MODE_LABELS,
)
from conjugate.data.verbs import CATEGORY_LABELS, CATEGORY_ORDER, CATEGORY_SHORT, drillable_verbs
from conjugate.session_logic import build_session_questions, build_summary, grade_target, public_question
from conjugate.storage import (
    get_session_lock,
    get_submissions,
    load_session,
    load_settings,
    new_session_id,
    progress_detail,
    progress_summary,
    progress_verbs,
    purchase_guardian,
    save_daily_goal,
    save_session,
    save_submission,
    weak_verbs_report,
)
from conjugate.transcription import keep_spanish_transcript, transcribe_audio
from conjugate.vocab import (
    DEFAULT_VOCAB_COUNT,
    DIRECTION_LABELS,
    DIRECTIONS,
    build_vocab_questions,
    build_vocab_summary,
    grade_vocab_choice,
    public_vocab_question,
)

logger = logging.getLogger(__name__)

main_bp = Blueprint(
    "conjugate",
    __name__,
    url_prefix="/conjugate",
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


START_ERROR_MESSAGES = {
    "no_questions": "出題できる問題がありません。管理画面でカテゴリと文型の設定を確認してください。",
}


@main_bp.context_processor
def _inject_appearance():
    return appearance_context()


@main_bp.after_request
def _revalidate_html(response):
    """HTMLは常に再検証させ、古いHTML（＝古いJS/CSSのURL）が残らないようにする。"""
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@main_bp.route("/health")
def health():
    return jsonify({"ok": True, "app": "conjugate"})


@main_bp.route("/manifest.json")
def web_app_manifest():
    """PWA manifest は /conjugate/ 配下に置き、scope が練習画面全体を覆うようにする。"""
    return send_from_directory(
        Path(main_bp.root_path) / "static",
        "manifest.json",
        mimetype="application/manifest+json",
    )


@main_bp.route("/")
def index():
    settings = load_settings()
    progress = progress_detail()
    weak = weak_verbs_report(limit=3)
    verb_counts = {cat: 0 for cat in CATEGORY_ORDER}
    category_person = {cat: {"tu": 0, "el": 0, "both": 0} for cat in CATEGORY_ORDER}
    for verb in drillable_verbs():
        verb_counts[verb["category"]] = verb_counts.get(verb["category"], 0) + 1
    for row in progress.get("verbs") or []:
        cat = row.get("category")
        if cat not in category_person:
            continue
        persons = row.get("persons") or {}
        if (persons.get("tu") or {}).get("mastered"):
            category_person[cat]["tu"] += 1
        if (persons.get("el_ella_usted") or {}).get("mastered"):
            category_person[cat]["el"] += 1
        if row.get("mastered"):
            category_person[cat]["both"] += 1
    return render_template(
        "conjugate/index.html",
        settings=settings,
        start_error=START_ERROR_MESSAGES.get(request.args.get("error", "")),
        category_labels=CATEGORY_LABELS,
        category_short=CATEGORY_SHORT,
        category_order=CATEGORY_ORDER,
        category_counts=verb_counts,
        category_person=category_person,
        tense_labels=TENSE_LABELS,
        tense_order=TENSE_ORDER,
        selectable_tenses=selectable_tenses(settings.get("enabled_tenses")),
        default_tenses=default_selected_tenses(settings.get("enabled_tenses")),
        person_mode=settings.get("person_mode", "tu"),
        person_mode_labels=PERSON_MODE_LABELS,
        person_filter_labels=PERSON_FILTER_LABELS,
        person_badge_labels=PERSON_BADGE_LABELS,
        progress=progress,
        weak_verbs=weak,
    )


@main_bp.route("/verbs")
def verbs_page():
    grouped = {cat: [] for cat in CATEGORY_ORDER}
    for row in progress_verbs():
        grouped.setdefault(row["category"], []).append(row)
    progress = progress_summary()
    return render_template(
        "conjugate/verbs.html",
        grouped_verbs=grouped,
        category_labels=CATEGORY_LABELS,
        category_short=CATEGORY_SHORT,
        category_order=CATEGORY_ORDER,
        tense_labels=TENSE_LABELS,
        tense_order=TENSE_ORDER,
        progress=progress,
    )


@main_bp.route("/tenses")
def tenses_page():
    return render_template(
        "conjugate/tenses.html",
        guides=list_tense_guides(),
        tense_labels=TENSE_LABELS,
        tense_order=TENSE_ORDER,
    )


@main_bp.route("/tenses/<tense_id>")
def tense_guide_page(tense_id):
    guide = get_tense_guide(tense_id)
    if not guide:
        return render_template("conjugate/not_found.html"), 404
    return render_template(
        "conjugate/tense_guide.html",
        guide=guide,
        tense_labels=TENSE_LABELS,
        tense_order=TENSE_ORDER,
    )


@main_bp.route("/profile")
def profile_page():
    return render_template(
        "conjugate/profile.html",
        progress=progress_summary(),
        recent_submissions=get_submissions(limit=8),
        weak_verbs=weak_verbs_report(limit=8),
        category_labels=CATEGORY_LABELS,
        tense_labels=TENSE_LABELS,
    )


@main_bp.route("/shop")
def shop_page():
    return render_template(
        "conjugate/shop.html",
        progress=progress_summary(),
    )


def _prepare_session(raw_categories, raw_tenses, raw_count, raw_prioritize_weak, raw_person_filter=None) -> dict:
    """選択内容を検証・正規化して、未保存のセッションを組み立てる。"""
    ensure_dirs()
    settings = load_settings()

    categories = [c for c in (raw_categories or settings["enabled_categories"]) if c in CATEGORY_ORDER]
    categories = [c for c in categories if c in settings["enabled_categories"]] or settings["enabled_categories"]

    tenses = [t for t in (raw_tenses or settings["enabled_tenses"]) if t in TENSE_ORDER]
    allowed = set(selectable_tenses(settings["enabled_tenses"]))
    tenses = [t for t in tenses if t in allowed] or list(default_selected_tenses(settings["enabled_tenses"]))

    try:
        count = int(raw_count or settings["questions_per_session"])
    except (TypeError, ValueError):
        count = settings["questions_per_session"]
    count = max(3, min(50, count))

    prioritize_weak = bool(settings["prioritize_weak_verbs"] if raw_prioritize_weak is None else raw_prioritize_weak)
    gustar_enabled = bool(settings["gustar_enabled"])
    gustar_count = settings["gustar_per_session"] if gustar_enabled else 0
    person_mode = settings.get("person_mode") or "tu"
    person_filter = str(raw_person_filter or DEFAULT_PERSON_FILTER)
    if person_filter not in ("all",) + PERSON_IDS:
        person_filter = DEFAULT_PERSON_FILTER
    if person_mode != "mix":
        person_filter = "all"

    questions = build_session_questions(
        categories=categories,
        tenses=tenses,
        count=count,
        targets_per_question=settings["targets_per_question"],
        gustar_enabled=gustar_enabled,
        gustar_count=gustar_count,
        prioritize_weak=prioritize_weak,
        person_mode=person_mode,
        person_filter=person_filter,
    )

    return {
        "session_id": new_session_id(),
        "categories": categories,
        "tenses": tenses,
        "person_mode": person_mode,
        "person_filter": person_filter,
        "strictness": settings["strictness"],
        "asr_engine": settings["asr_engine"],
        "whisper_model": settings["whisper_model"],
        "questions": questions,
        "current_index": 0,
        "status": "in_progress",
        "usage": {"whisper_seconds": 0.0, "whisper_calls": 0, "cost_usd": 0.0},
    }


@main_bp.route("/api/sessions", methods=["POST"])
def create_session():
    payload = request.get_json(silent=True) or {}
    session = _prepare_session(
        payload.get("categories"),
        payload.get("tenses"),
        payload.get("count"),
        payload.get("prioritize_weak_verbs"),
        payload.get("person_filter"),
    )
    if not session["questions"]:
        return jsonify({"ok": False, "error": START_ERROR_MESSAGES["no_questions"]}), 400

    save_session(session)
    return jsonify({"ok": True, "session_id": session["session_id"]}), 201


@main_bp.route("/start", methods=["POST"])
def start_session():
    """index.jsが読み込めない環境でも練習を開始できるフォーム送信の受け口。"""
    session = _prepare_session(
        request.form.getlist("category"),
        request.form.getlist("tense"),
        request.form.get("count"),
        "prioritize_weak_verbs" in request.form,
        request.form.get("person_filter"),
    )
    if not session["questions"]:
        return redirect(url_for("conjugate.index", error="no_questions"), code=303)

    save_session(session)
    # 303にしてPOST→GETの読み替えをクライアントに依存させない
    return redirect(url_for("conjugate.quiz_screen", session_id=session["session_id"]), code=303)


@main_bp.route("/session/<session_id>")
def quiz_screen(session_id):
    session = load_session(session_id)
    if not session:
        return render_template("conjugate/not_found.html"), 404
    if session.get("kind") == "vocab":
        return redirect(url_for("conjugate.vocab_screen", session_id=session_id))
    return render_template(
        "conjugate/quiz.html",
        session_id=session_id,
        asr_engine=session.get("asr_engine", "whisper"),
        tense_labels=TENSE_LABELS,
        category_labels=CATEGORY_LABELS,
        person_badge_labels=PERSON_BADGE_LABELS,
        el_ella_usted_hint=EL_ELLA_USTED_HINT,
        tense_guides=[get_tense_guide(tid) for tid in TENSE_ORDER],
    )


@main_bp.route("/api/sessions/<session_id>", methods=["GET"])
def get_session_api(session_id):
    session = load_session(session_id)
    if not session:
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404
    if session.get("kind") == "vocab":
        public = dict(session)
        public["questions"] = [public_vocab_question(q) for q in session["questions"]]
        return jsonify({"ok": True, "session": public})
    public = dict(session)
    public["questions"] = [public_question(q) for q in session["questions"]]
    return jsonify({"ok": True, "session": public})


def _resolve_extension(filename: str, mimetype: str | None) -> str:
    safe_name = secure_filename(filename or "")
    if "." in safe_name:
        return safe_name.rsplit(".", 1)[-1].lower()
    guessed = mimetypes.guess_extension(mimetype or "") or ""
    return guessed.lstrip(".").lower() or "webm"


def _add_whisper_usage(session: dict, model: str, duration_sec: float) -> None:
    usage = session.setdefault("usage", {"whisper_seconds": 0.0, "whisper_calls": 0, "cost_usd": 0.0})
    billed_sec = max(1, int(duration_sec + 0.999999))
    usage["whisper_seconds"] = float(usage.get("whisper_seconds") or 0) + billed_sec
    usage["whisper_calls"] = int(usage.get("whisper_calls") or 0) + 1
    usage["cost_usd"] = float(usage.get("cost_usd") or 0) + whisper_cost_usd(model, billed_sec)


def _find_question(session: dict, question_id: str) -> dict | None:
    for q in session["questions"]:
        if q["question_id"] == question_id:
            return q
    return None


@main_bp.route("/api/sessions/<session_id>/questions/<question_id>/targets/<target>/answer", methods=["POST"])
def submit_answer(session_id, question_id, target):
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404
        if session.get("kind") == "vocab":
            return jsonify({"ok": False, "error": "このセッションは語彙クイズです。"}), 400
        question = _find_question(session, question_id)
        if not question:
            return jsonify({"ok": False, "error": "問題が見つかりません。"}), 404
        if target not in question.get("targets", []):
            return jsonify({"ok": False, "error": "指定された文型はこの問題の対象ではありません。"}), 400

        transcript = ""
        transcript_source = "text"
        answer_source = "speech"

        if "audio" in request.files and request.files["audio"].filename:
            audio_file = request.files["audio"]
            ext = _resolve_extension(audio_file.filename, audio_file.mimetype)
            if ext not in ALLOWED_AUDIO_EXTENSIONS:
                return jsonify({"ok": False, "error": f"対応していない音声形式です: {ext}"}), 400

            ensure_dirs()
            tmp_name = f"{session_id}_{question_id}_{target}_{uuid.uuid4().hex[:8]}.{ext}"
            tmp_path = AUDIO_TMP_DIR / tmp_name
            audio_file.save(tmp_path)

            try:
                if tmp_path.stat().st_size > MAX_AUDIO_BYTES:
                    tmp_path.unlink(missing_ok=True)
                    return jsonify({"ok": False, "error": "音声ファイルが大きすぎます。もう一度、短く録音してください。"}), 400

                norm_path = normalize_audio_file(tmp_path)
                whisper_model = session.get("whisper_model", "whisper-1")
                duration_sec = audio_duration_sec(norm_path)
                try:
                    transcript = transcribe_audio(norm_path, model=whisper_model, language="es")
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Whisper transcription failed")
                    return jsonify({"ok": False, "error": f"文字起こしに失敗しました: {exc}"}), 502
                transcript_source = "whisper"
                _add_whisper_usage(session, whisper_model, duration_sec)
            finally:
                tmp_path.unlink(missing_ok=True)
                norm_candidate = tmp_path.with_suffix(".norm.wav")
                norm_candidate.unlink(missing_ok=True)
        else:
            payload = request.form or request.get_json(silent=True) or {}
            transcript = keep_spanish_transcript(str(payload.get("transcript") or ""))
            if str(payload.get("answer_mode") or "") == "typed":
                transcript_source = "typed"
                answer_source = "typed"
                if not transcript:
                    return jsonify({"ok": False, "error": "解答が空です。スペルをタイプしてください。"}), 400
            else:
                transcript_source = "web_speech"
                if not transcript:
                    return jsonify({"ok": False, "error": "音声ファイルまたは認識テキストがありません。"}), 400

        strict = session.get("strictness") == "strict"
        result = grade_target(question, target, transcript, strict, source=answer_source)
        result["transcript_source"] = transcript_source

        question.setdefault("answers", {})[target] = result
        if result.get("newly_mastered") and question.get("kind") == "verb":
            person = question.get("person") if question.get("person") in ("tu", "el_ella_usted") else "tu"
            session.setdefault("newly_mastered", []).append(
                {
                    "infinitive": question.get("infinitive"),
                    "meaning_ja": question.get("meaning_ja", ""),
                    "target": target,
                    "person": person,
                    "person_label": "él" if person == "el_ella_usted" else "tú",
                }
            )
        if all(t in question["answers"] for t in question["targets"]):
            question["status"] = "done"
        save_session(session)

        return jsonify({"ok": True, "result": result})


@main_bp.route("/api/sessions/<session_id>/finish", methods=["POST"])
def finish_session(session_id):
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404
        if session.get("kind") == "vocab":
            summary = build_vocab_summary(session)
        else:
            summary = build_summary(session)
        session["status"] = "done"
        session["summary"] = summary
        save_session(session)

        if session.get("kind") != "vocab":
            save_submission(
                {
                    "session_id": session_id,
                    "categories": session.get("categories", []),
                    "tenses": session.get("tenses", []),
                    "total": summary["total"],
                    "correct": summary["correct"],
                    "accuracy": summary["accuracy"],
                    "level_counts": summary["level_counts"],
                }
            )

    return jsonify({"ok": True, "summary": summary})


@main_bp.route("/session/<session_id>/summary")
def summary_screen(session_id):
    session = load_session(session_id)
    if not session:
        return render_template("conjugate/not_found.html"), 404
    if session.get("kind") == "vocab":
        return redirect(url_for("conjugate.vocab_summary_screen", session_id=session_id))
    summary = session.get("summary") or build_summary(session)
    progress = progress_detail()
    verbs_by_id = {row.get("id"): row for row in progress.get("verbs") or []}
    for item in summary.get("weak_items") or []:
        row = verbs_by_id.get(item.get("verb_id")) or {}
        item["tense_misses"] = row.get("tense_misses") or []
        item["miss_total"] = int(row.get("miss_total") or 0)
    return render_template(
        "conjugate/summary.html",
        session=session,
        summary=summary,
        progress=progress,
        category_labels=CATEGORY_LABELS,
        tense_labels=TENSE_LABELS,
    )


@main_bp.route("/api/weak-verbs")
def weak_verbs_api():
    return jsonify({"ok": True, "weak_verbs": weak_verbs_report()})


@main_bp.route("/api/progress/daily-goal", methods=["POST"])
def set_daily_goal():
    payload = request.get_json(silent=True) or {}
    try:
        goal = int(payload.get("daily_goal") or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "1日の目標は数値で指定してください。"}), 400
    if goal < 1 or goal > 100:
        return jsonify({"ok": False, "error": "1日の目標は1〜100問で設定してください。"}), 400
    view = save_daily_goal(goal)
    return jsonify({"ok": True, "progress": view})


@main_bp.route("/api/progress/guardian/purchase", methods=["POST"])
def purchase_guardian_api():
    view = purchase_guardian()
    ok = bool(view.get("ok"))
    return jsonify({"ok": ok, "error": view.get("error"), "progress": view}), (200 if ok else 400)


def _prepare_vocab_session(raw_direction, raw_count) -> dict:
    direction = str(raw_direction or "ja_to_es")
    if direction not in DIRECTIONS:
        direction = "ja_to_es"
    try:
        count = int(raw_count or DEFAULT_VOCAB_COUNT)
    except (TypeError, ValueError):
        count = DEFAULT_VOCAB_COUNT
    questions = build_vocab_questions(direction, count)
    return {
        "session_id": new_session_id(),
        "kind": "vocab",
        "direction": direction,
        "questions": questions,
        "status": "in_progress",
    }


@main_bp.route("/api/vocab", methods=["POST"])
def create_vocab_session():
    payload = request.get_json(silent=True) or {}
    session = _prepare_vocab_session(payload.get("direction"), payload.get("count"))
    if not session["questions"]:
        return jsonify({"ok": False, "error": "出題できる単語が足りません。"}), 400
    save_session(session)
    return jsonify({"ok": True, "session_id": session["session_id"]}), 201


@main_bp.route("/vocab/start", methods=["POST"])
def start_vocab_session():
    session = _prepare_vocab_session(request.form.get("direction"), request.form.get("count"))
    if not session["questions"]:
        return redirect(url_for("conjugate.index"), code=303)
    save_session(session)
    return redirect(url_for("conjugate.vocab_screen", session_id=session["session_id"]), code=303)


@main_bp.route("/vocab/<session_id>")
def vocab_screen(session_id):
    session = load_session(session_id)
    if not session or session.get("kind") != "vocab":
        return render_template("conjugate/not_found.html"), 404
    return render_template(
        "conjugate/vocab.html",
        session_id=session_id,
        direction=session.get("direction", "ja_to_es"),
        direction_label=DIRECTION_LABELS.get(session.get("direction"), ""),
    )


@main_bp.route("/api/vocab/<session_id>", methods=["GET"])
def get_vocab_session_api(session_id):
    session = load_session(session_id)
    if not session or session.get("kind") != "vocab":
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404
    public = dict(session)
    public["questions"] = [public_vocab_question(q) for q in session["questions"]]
    return jsonify({"ok": True, "session": public})


@main_bp.route("/api/vocab/<session_id>/questions/<question_id>/answer", methods=["POST"])
def submit_vocab_answer(session_id, question_id):
    payload = request.get_json(silent=True) or request.form or {}
    choice_id = str(payload.get("choice_id") or "")
    if not choice_id:
        return jsonify({"ok": False, "error": "選択肢を選んでください。"}), 400

    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session or session.get("kind") != "vocab":
            return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404
        question = _find_question(session, question_id)
        if not question:
            return jsonify({"ok": False, "error": "問題が見つかりません。"}), 404
        valid_ids = {c["id"] for c in question.get("choices", [])}
        if choice_id not in valid_ids:
            return jsonify({"ok": False, "error": "不正な選択肢です。"}), 400
        if question.get("answer"):
            return jsonify({"ok": True, "result": question["answer"], "already_answered": True})

        result = grade_vocab_choice(question, choice_id)
        question["answer"] = result
        question["status"] = "done"
        save_session(session)
        return jsonify({"ok": True, "result": result})


@main_bp.route("/api/vocab/<session_id>/finish", methods=["POST"])
def finish_vocab_session(session_id):
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session or session.get("kind") != "vocab":
            return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404
        summary = build_vocab_summary(session)
        session["status"] = "done"
        session["summary"] = summary
        save_session(session)
    return jsonify({"ok": True, "summary": summary})


@main_bp.route("/vocab/<session_id>/summary")
def vocab_summary_screen(session_id):
    session = load_session(session_id)
    if not session or session.get("kind") != "vocab":
        return render_template("conjugate/not_found.html"), 404
    summary = session.get("summary") or build_vocab_summary(session)
    progress = progress_detail()
    direction = session.get("direction")
    miss_by_id = {
        row.get("id"): int((row.get(direction) or {}).get("miss_count") or 0)
        for row in progress.get("vocab_verbs") or []
    }
    for item in summary.get("weak_items") or []:
        item["miss_count"] = miss_by_id.get(item.get("verb_id"), int(item.get("miss_count") or 0))
    return render_template(
        "conjugate/vocab_summary.html",
        session=session,
        summary=summary,
        progress=progress,
        direction_label=DIRECTION_LABELS.get(session.get("direction"), ""),
    )
