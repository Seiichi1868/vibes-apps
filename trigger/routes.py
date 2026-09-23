"""Vibe Speak Trigger: 生徒向け Blueprint。

フロー: ログイン/テーマ選択 → 台本作成 → 台本確定 → 模範音声再生 → 音読録音
       → フォローアップQ&A → 即興スピーチ → 総合評価レポート

すべて単一ページ（templates/trigger/index.html）+ フロントJSで進行し、
各ステップはサーバーAPIを同期的に呼び出す（バックグラウンドジョブは使わない）。
"""
import logging
import mimetypes
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from trigger.audio_convert import normalize_audio_file
from trigger.config import (
    ALLOWED_AUDIO_EXTENSIONS,
    AUDIO_DIR,
    MAX_AUDIO_BYTES,
    PROMPT_AUDIO_DIR,
    ensure_dirs,
    get_openai_api_key,
)
from trigger.model_catalog import resolve_ai_model_id
from trigger.models import new_qa_item, new_session, new_speech_item, touch
from trigger.scoring.pronunciation_ai import evaluate_pronunciation
from trigger.scoring.qa_ai import evaluate_answer, generate_questions
from trigger.scoring.report_ai import generate_final_report
from trigger.scoring.script_ai import correct_script, translate_script
from trigger.scoring.speech_ai import evaluate_speech, generate_topics
from trigger.storage import (
    get_session_lock,
    get_theme,
    load_session,
    load_settings,
    load_students,
    save_session,
    save_submission,
)
from trigger.transcription import transcribe_audio
from trigger.tts import ensure_prompt_audio

logger = logging.getLogger(__name__)

main_bp = Blueprint(
    "trigger",
    __name__,
    url_prefix="/trigger",
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


def _model_for(settings: dict, task_key: str) -> str:
    return resolve_ai_model_id((settings.get("task_model_modes") or {}).get(task_key))


def _resolve_extension(filename: str, mimetype: str | None) -> str:
    safe_name = secure_filename(filename or "")
    if "." in safe_name:
        return safe_name.rsplit(".", 1)[-1].lower()
    guessed = mimetypes.guess_extension(mimetype or "") or ""
    return guessed.lstrip(".").lower() or "webm"


def _save_uploaded_audio(session_id: str, prefix: str):
    """アップロードされた音声を保存し、(Pathオブジェクト, エラーレスポンス) を返す。"""
    if "audio" not in request.files:
        return None, (jsonify({"ok": False, "error": "音声ファイルがありません。マイクの許可をご確認ください。"}), 400)
    audio_file = request.files["audio"]
    if not audio_file.filename:
        return None, (jsonify({"ok": False, "error": "音声ファイルが空です。もう一度録音してください。"}), 400)

    ext = _resolve_extension(audio_file.filename, audio_file.mimetype)
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        return None, (jsonify({"ok": False, "error": f"対応していない音声形式です: {ext}"}), 400)

    ensure_dirs()
    session_dir = AUDIO_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}.{ext}"
    file_path = session_dir / filename
    audio_file.save(file_path)

    if file_path.stat().st_size > MAX_AUDIO_BYTES:
        file_path.unlink(missing_ok=True)
        return None, (jsonify({"ok": False, "error": "音声ファイルが大きすぎます。もう一度、短く録音してください。"}), 400)

    return file_path, None


def _transcribe_or_error(file_path: Path, whisper_model: str):
    try:
        normalized = normalize_audio_file(file_path)
        transcript = transcribe_audio(normalized, model=whisper_model, language="en")
        return transcript, None
    except Exception as exc:  # noqa: BLE001
        logger.error("trigger transcription failed: %s", exc)
        return None, (jsonify({"ok": False, "error": f"音声認識に失敗しました: {exc}"}), 502)


@main_bp.route("/manifest.json")
def web_app_manifest():
    """生徒画面用 PWA manifest（scope: /trigger/）。"""
    response = send_from_directory(
        Path(current_app.static_folder) / "trigger",
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@main_bp.route("/")
def index():
    return render_template("trigger/index.html")


@main_bp.route("/session/<session_id>")
def index_with_session(session_id):
    session = load_session(session_id)
    if not session:
        return render_template("trigger/not_found.html"), 404
    return render_template("trigger/index.html", initial_session_id=session_id)


# ── テーマ・名簿 ────────────────────────────────────────────

@main_bp.route("/api/themes", methods=["GET"])
def list_themes_api():
    from trigger.storage import active_themes

    return jsonify({"ok": True, "themes": active_themes()})


@main_bp.route("/api/config", methods=["GET"])
def public_config_api():
    settings = load_settings()
    return jsonify({"ok": True, "student_info_required": bool(settings.get("student_info_required", True))})


@main_bp.route("/api/roster", methods=["GET"])
def roster_api():
    students = load_students()
    classes = sorted({s["class_name"] for s in students if s.get("class_name")})
    return jsonify({"ok": True, "students": students, "classes": classes})


# ── セッション作成 ──────────────────────────────────────────

@main_bp.route("/api/sessions", methods=["POST"])
def create_session_api():
    payload = request.get_json(silent=True) or {}
    student_info = payload.get("student_info") or {}
    theme_id = str(payload.get("theme_id") or "").strip()

    theme = get_theme(theme_id)
    if not theme:
        return jsonify({"ok": False, "error": "テーマが見つかりません。"}), 400

    settings = load_settings()
    if settings.get("student_info_required", True):
        name = str(student_info.get("name") or "").strip()
        number = str(student_info.get("number") or "").strip()
        if not (name or number):
            return jsonify({"ok": False, "error": "生徒情報を入力してください。"}), 400

    session = new_session(student_info=student_info, theme_id=theme_id, theme_title=theme["title"])
    save_session(session)
    return jsonify({"ok": True, "session_id": session["session_id"], "session": session}), 201


@main_bp.route("/api/sessions/<session_id>", methods=["GET"])
def get_session_api(session_id):
    session = load_session(session_id)
    if not session:
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404
    return jsonify({"ok": True, "session": session})


# ── ステップ1: 台本作成 ─────────────────────────────────────

def _run_script_step(mode: str):
    payload = request.get_json(silent=True) or {}
    session_id = str(payload.get("session_id") or "")
    input_text = str(payload.get("input_text") or "").strip()

    session = load_session(session_id)
    if not session:
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404

    theme = get_theme(session.get("theme_id")) or {}
    settings = load_settings()
    model = _model_for(settings, "script_translate")
    api_key = get_openai_api_key()

    try:
        if mode == "translate":
            result = translate_script(
                input_text=input_text,
                theme_title=theme.get("title", session.get("theme_title", "")),
                description_hint=theme.get("description_hint", ""),
                model=model,
                api_key=api_key,
            )
        else:
            result = correct_script(
                input_text=input_text,
                theme_title=theme.get("title", session.get("theme_title", "")),
                description_hint=theme.get("description_hint", ""),
                model=model,
                api_key=api_key,
            )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 502

    session["script"] = {
        "mode": mode,
        "input_text": input_text,
        "output_text": result["output_text"],
        "notes": result.get("notes", ""),
        "corrections": result.get("corrections", []),
        "confirmed": False,
    }
    session["model_snapshot"]["script_translate"] = model
    touch(session)
    save_session(session)
    return jsonify({"ok": True, "script": session["script"]})


@main_bp.route("/api/script/translate", methods=["POST"])
def script_translate_api():
    return _run_script_step("translate")


@main_bp.route("/api/script/correct", methods=["POST"])
def script_correct_api():
    return _run_script_step("correct")


@main_bp.route("/api/script/confirm", methods=["POST"])
def script_confirm_api():
    payload = request.get_json(silent=True) or {}
    session_id = str(payload.get("session_id") or "")
    output_text = str(payload.get("output_text") or "").strip()

    session = load_session(session_id)
    if not session:
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404
    if not output_text:
        return jsonify({"ok": False, "error": "確定する英文がありません。"}), 400

    session["script"]["output_text"] = output_text
    session["script"]["confirmed"] = True
    session["status"] = "sample"
    touch(session)
    save_session(session)
    return jsonify({"ok": True, "session": session})


# ── ステップ2: 模範音声 ─────────────────────────────────────

@main_bp.route("/api/tts/generate", methods=["POST"])
def tts_generate_api():
    payload = request.get_json(silent=True) or {}
    session_id = str(payload.get("session_id") or "")

    session = load_session(session_id)
    if not session:
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404

    text = session.get("script", {}).get("output_text", "")
    if not text:
        return jsonify({"ok": False, "error": "台本が確定されていません。"}), 400

    url = ensure_prompt_audio(text)
    if not url:
        return jsonify({"ok": False, "error": "音声生成に失敗しました。"}), 502

    session["status"] = "readaloud"
    session["sample_audio_url"] = url
    touch(session)
    save_session(session)
    return jsonify({"ok": True, "audio_url": url, "session": session})


# ── ステップ3: 音読→発音評価 ────────────────────────────────

@main_bp.route("/api/pronunciation/evaluate", methods=["POST"])
def pronunciation_evaluate_api():
    session_id = str(request.form.get("session_id") or "")
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404

        file_path, error = _save_uploaded_audio(session_id, "readaloud")
        if error:
            return error

        settings = load_settings()
        transcript, error = _transcribe_or_error(file_path, settings.get("whisper_model"))
        if error:
            return error

        model = _model_for(settings, "pronunciation_eval")
        try:
            result = evaluate_pronunciation(
                reference_text=session["script"]["output_text"],
                transcript=transcript,
                model=model,
                api_key=get_openai_api_key(),
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 502

        result["audio_url"] = f"/trigger/audio/{session_id}/{file_path.name}"
        session["pronunciation_result"] = result
        session["status"] = "qa"
        session["model_snapshot"]["pronunciation_eval"] = model
        touch(session)
        save_session(session)
        return jsonify({"ok": True, "pronunciation_result": result, "session": session})


# ── ステップ4: フォローアップQ&A ─────────────────────────────

@main_bp.route("/api/qa/generate", methods=["POST"])
def qa_generate_api():
    payload = request.get_json(silent=True) or {}
    session_id = str(payload.get("session_id") or "")

    session = load_session(session_id)
    if not session:
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404

    if session.get("qa_items"):
        return jsonify({"ok": True, "qa_items": session["qa_items"], "session": session})

    settings = load_settings()
    model = _model_for(settings, "qa_generate")
    try:
        questions = generate_questions(
            script_text=session["script"]["output_text"],
            count=settings.get("qa_question_count", 3),
            model=model,
            api_key=get_openai_api_key(),
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 502

    qa_items = []
    for question_text in questions:
        audio_url = ensure_prompt_audio(question_text) or ""
        qa_items.append(new_qa_item(question_text=question_text, question_audio_url=audio_url))

    session["qa_items"] = qa_items
    session["model_snapshot"]["qa_generate"] = model
    touch(session)
    save_session(session)
    return jsonify({"ok": True, "qa_items": qa_items, "session": session})


@main_bp.route("/api/qa/evaluate", methods=["POST"])
def qa_evaluate_api():
    session_id = str(request.form.get("session_id") or "")
    qa_id = str(request.form.get("qa_id") or "")

    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404

        qa_item = next((q for q in session.get("qa_items", []) if q["id"] == qa_id), None)
        if not qa_item:
            return jsonify({"ok": False, "error": "質問が見つかりません。"}), 404

        file_path, error = _save_uploaded_audio(session_id, f"qa_{qa_id}")
        if error:
            return error

        settings = load_settings()
        transcript, error = _transcribe_or_error(file_path, settings.get("whisper_model"))
        if error:
            return error

        model = _model_for(settings, "qa_evaluate")
        try:
            evaluation = evaluate_answer(
                script_text=session["script"]["output_text"],
                question_text=qa_item["question_text"],
                transcript=transcript,
                model=model,
                api_key=get_openai_api_key(),
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 502

        qa_item["student_answer_audio_url"] = f"/trigger/audio/{session_id}/{file_path.name}"
        qa_item["student_answer_transcript"] = transcript
        qa_item["evaluation"] = evaluation
        session["model_snapshot"]["qa_evaluate"] = model

        all_answered = all(q.get("evaluation") for q in session["qa_items"])
        if all_answered:
            session["status"] = "speech"
        touch(session)
        save_session(session)
        return jsonify({"ok": True, "qa_item": qa_item, "all_answered": all_answered, "session": session})


# ── ステップ5: 即興スピーチ ─────────────────────────────────

@main_bp.route("/api/speech/topic", methods=["POST"])
def speech_topic_api():
    payload = request.get_json(silent=True) or {}
    session_id = str(payload.get("session_id") or "")

    session = load_session(session_id)
    if not session:
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404

    if session.get("speech_items"):
        return jsonify({"ok": True, "speech_items": session["speech_items"], "session": session})

    settings = load_settings()
    model = _model_for(settings, "speech_topic")
    try:
        topics = generate_topics(
            script_text=session["script"]["output_text"],
            theme_title=session.get("theme_title", ""),
            count=settings.get("speech_topic_count", 1),
            model=model,
            api_key=get_openai_api_key(),
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 502

    speech_items = []
    for topic in topics:
        topic_text = topic["topic_text"]
        audio_url = ""
        if settings.get("speech_topic_tts_enabled"):
            audio_url = ensure_prompt_audio(topic_text) or ""
        item = new_speech_item(topic_text=topic_text, topic_audio_url=audio_url)
        item["topic_text_ja"] = topic.get("topic_text_ja", "")
        speech_items.append(item)

    session["speech_items"] = speech_items
    session["model_snapshot"]["speech_topic"] = model
    touch(session)
    save_session(session)
    return jsonify({"ok": True, "speech_items": speech_items, "session": session})


@main_bp.route("/api/speech/evaluate", methods=["POST"])
def speech_evaluate_api():
    session_id = str(request.form.get("session_id") or "")
    item_id = str(request.form.get("item_id") or "")

    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404

        speech_item = next((s for s in session.get("speech_items", []) if s["id"] == item_id), None)
        if not speech_item:
            return jsonify({"ok": False, "error": "トピックが見つかりません。"}), 404

        file_path, error = _save_uploaded_audio(session_id, f"speech_{item_id}")
        if error:
            return error

        settings = load_settings()
        transcript, error = _transcribe_or_error(file_path, settings.get("whisper_model"))
        if error:
            return error

        model = _model_for(settings, "speech_evaluate")
        try:
            evaluation = evaluate_speech(
                topic_text=speech_item["topic_text"],
                transcript=transcript,
                model=model,
                api_key=get_openai_api_key(),
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 502

        speech_item["student_audio_url"] = f"/trigger/audio/{session_id}/{file_path.name}"
        speech_item["student_transcript"] = transcript
        speech_item["evaluation"] = evaluation
        session["model_snapshot"]["speech_evaluate"] = model

        all_done = all(s.get("evaluation") for s in session["speech_items"])
        if all_done:
            session["status"] = "report"
        touch(session)
        save_session(session)
        return jsonify({"ok": True, "speech_item": speech_item, "all_answered": all_done, "session": session})


# ── ステップ6: 総合評価 ─────────────────────────────────────

@main_bp.route("/api/report/final", methods=["POST"])
def report_final_api():
    payload = request.get_json(silent=True) or {}
    session_id = str(payload.get("session_id") or "")

    session = load_session(session_id)
    if not session:
        return jsonify({"ok": False, "error": "セッションが見つかりません。"}), 404

    if session.get("final_evaluation"):
        return jsonify({"ok": True, "final_evaluation": session["final_evaluation"], "session": session})

    settings = load_settings()
    model = _model_for(settings, "report_final")
    try:
        final_evaluation = generate_final_report(
            session=session,
            model=model,
            api_key=get_openai_api_key(),
            versant_weights=settings.get("versant_weights"),
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 502

    session["final_evaluation"] = final_evaluation
    session["status"] = "done"
    session["completed_at"] = session["updated_at"]
    session["model_snapshot"]["report_final"] = model
    touch(session)
    save_session(session)

    save_submission(
        {
            "session_id": session_id,
            "student_info": session.get("student_info"),
            "theme_title": session.get("theme_title"),
            "final_evaluation": final_evaluation,
        }
    )
    return jsonify({"ok": True, "final_evaluation": final_evaluation, "session": session})


# ── 音声配信 ────────────────────────────────────────────────

@main_bp.route("/audio/<session_id>/<path:filename>")
def serve_audio(session_id, filename):
    safe_session_id = Path(session_id).name
    safe_filename = Path(filename).name
    directory = AUDIO_DIR / safe_session_id
    return send_from_directory(directory, safe_filename)


@main_bp.route("/prompt-audio/<path:filename>")
def serve_prompt_audio(filename):
    safe_filename = Path(filename).name
    return send_from_directory(PROMPT_AUDIO_DIR, safe_filename)
