import logging
import mimetypes
import tempfile
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from news_app.config import (
    ALLOWED_MEDIA_EXTENSIONS,
    CEFR_LEVELS,
    TRANSCRIBE_MAX_BYTES,
    TRANSCRIBE_MAX_SECONDS,
    get_openai_api_key,
    resolve_ai_model,
    resolve_cefr_level,
    resolve_display_language,
    resolve_eval_ai_model,
)
from news_app.services.audio_convert import prepare_for_whisper
from news_app.services.openai_eval import evaluate_summary
from news_app.services.transcription import transcribe_audio
from news_app.services.storage import (
    current_lesson_identity,
    get_active_class_id,
    get_class,
    get_evaluation_rubric,
    list_classes,
    load_state,
    save_submission,
    vocabulary_for_student,
    script_translation_for_lang,
    appearance_context,
    selected_display_questions,
)
from news_app.services.youtube import build_youtube_embed_url
from news_app.services.youtube_transcript import (
    TranscriptNotFound,
    TranscriptRateLimited,
    fetch_timedtext_from_url,
    fetch_via_worker_relay,
    fetch_youtube_transcript,
)

logger = logging.getLogger(__name__)

main_bp = Blueprint("news_main", __name__)

_MIME_EXTENSIONS = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/m4a": "m4a",
    "audio/aac": "aac",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/x-caf": "caf",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "video/3gpp": "3gp",
}


def _media_extension(filename: str, mimetype: str | None) -> str:
    safe_name = secure_filename(filename or "")
    if "." in safe_name:
        ext = safe_name.rsplit(".", 1)[-1].lower()
        if ext in ALLOWED_MEDIA_EXTENSIONS:
            return ext
    mime = (mimetype or "").split(";")[0].strip().lower()
    if mime in _MIME_EXTENSIONS:
        return _MIME_EXTENSIONS[mime]
    guessed = (mimetypes.guess_extension(mime) or "").lstrip(".").lower()
    if guessed == "qt":
        guessed = "mov"
    return guessed if guessed in ALLOWED_MEDIA_EXTENSIONS else ""


@main_bp.route("/health")
def health():
    return jsonify({"ok": True})


@main_bp.route("/api/youtube-transcript")
def youtube_transcript():
    """Cloudflare Worker が 429 のとき、Render 側 IP から InnerTube で字幕を取る。"""
    raw_id = (request.args.get("id") or "").strip()
    if not raw_id:
        return jsonify({"ok": False, "error": "動画 ID を指定してください (?id=VIDEO_ID)。"}), 400
    try:
        payload = fetch_youtube_transcript(raw_id)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except TranscriptRateLimited as exc:
        return jsonify({"ok": False, "error": str(exc)}), 429
    except TranscriptNotFound as exc:
        return jsonify({"ok": False, "error": str(exc), "source": "render-session"}), 404
    except Exception:
        logger.exception("youtube transcript fallback failed")
        return jsonify({"ok": False, "error": "字幕の取得に失敗しました。"}), 502
    return jsonify(payload)


@main_bp.route("/api/youtube-transcript-worker")
def youtube_transcript_worker_relay():
    """学校ネットワークが *.workers.dev を直接ブロックしている場合向けに、
    Render から Cloudflare Worker を代理で呼び出す同一オリジンの中継route。
    """
    raw_id = (request.args.get("id") or "").strip()
    if not raw_id:
        return jsonify({"ok": False, "error": "動画 ID を指定してください (?id=VIDEO_ID)。"}), 400
    try:
        payload = fetch_via_worker_relay(raw_id)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except TranscriptRateLimited as exc:
        return jsonify({"ok": False, "error": str(exc)}), 429
    except TranscriptNotFound as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        logger.info("worker relay failed: %s", exc)
        return jsonify({"ok": False, "error": "字幕プロキシの中継に失敗しました。"}), 502
    return jsonify(payload)


@main_bp.route("/api/youtube-timedtext")
def youtube_timedtext():
    """署名付き timedtext URL の本文を取得する（ブラウザ CORS 回避用）。"""
    raw_url = (request.args.get("url") or "").strip()
    if not raw_url:
        return jsonify({"ok": False, "error": "timedtext URL を指定してください。"}), 400
    try:
        payload = fetch_timedtext_from_url(raw_url)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except TranscriptRateLimited as exc:
        return jsonify({"ok": False, "error": str(exc)}), 429
    except TranscriptNotFound as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception:
        logger.exception("youtube timedtext proxy failed")
        return jsonify({"ok": False, "error": "字幕の取得に失敗しました。"}), 502
    return jsonify(payload)


@main_bp.route("/manifest.json")
def web_app_manifest():
    """PWA manifest は /news/ 配下に置き、scope が News 画面全体を覆うようにする。"""
    response = send_from_directory(
        Path(current_app.static_folder) / "news",
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


def _class_public_payload(class_id: str, origin: str, display_language: str = "ja") -> dict | None:
    cls = get_class(class_id)
    if not cls:
        return None
    current = cls.get("current") or {}
    lang = resolve_display_language(display_language)
    show_assistive = lang != "en"
    video_id = (current.get("video_id") or "").strip()
    start_sec = int(current.get("start_seconds") or 0)
    end_sec = int(current.get("end_seconds") or 0)
    subtitles_enabled = bool(current.get("subtitles_enabled", False))
    vocabulary_scaffolding_enabled = bool(current.get("vocabulary_scaffolding_enabled", False)) and show_assistive
    vocabulary_data = current.get("vocabulary_data") if isinstance(current.get("vocabulary_data"), list) else []
    if vocabulary_scaffolding_enabled:
        vocabulary_data = vocabulary_for_student(vocabulary_data, lang)
    else:
        vocabulary_data = []
    translation = script_translation_for_lang(current, lang) if show_assistive else {"enabled": False, "text": "", "pairs": []}
    embed_url = (
        build_youtube_embed_url(
            video_id,
            start_sec,
            end_sec,
            origin=origin,
            subtitles_enabled=subtitles_enabled,
        )
        if video_id
        else ""
    )

    warmup_scaffolding_enabled = bool(current.get("warmup_scaffolding_enabled", False))
    warmup_image_url = str(current.get("warmup_image_url") or "").strip()
    if warmup_scaffolding_enabled:
        warmup_questions = selected_display_questions(current.get("warmup_questions"))
    else:
        warmup_questions = []
        warmup_image_url = ""

    postview_scaffolding_enabled = bool(current.get("postview_scaffolding_enabled", False))
    if postview_scaffolding_enabled:
        postview_questions = selected_display_questions(current.get("postview_questions"))
    else:
        postview_questions = []

    return {
        "id": cls["id"],
        "name": cls["name"],
        "require_student_info": bool(cls.get("require_student_info", False)),
        "video": {
            "video_id": video_id,
            "start_seconds": start_sec,
            "end_seconds": end_sec,
            "embed_url": embed_url,
            "watch_url": f"https://www.youtube.com/watch?v={video_id}&t={start_sec}s" if video_id else "",
            "has_script": bool((current.get("script") or "").strip()),
            "subtitles_enabled": subtitles_enabled,
        },
        "timers": {
            "prep_seconds": int(current.get("prep_timer_seconds") or 0),
            "record_seconds": int(current.get("record_timer_seconds") or 60),
            "visible": bool(current.get("timers_visible", True)),
        },
        "vocabulary_scaffolding_enabled": vocabulary_scaffolding_enabled,
        "vocabulary_data": vocabulary_data,
        "translation_enabled": bool(translation.get("enabled")),
        "translation_pairs": translation.get("pairs") or [],
        "translation_text": translation.get("text") or "",
        "warmup_scaffolding_enabled": warmup_scaffolding_enabled,
        "warmup_image_url": warmup_image_url,
        "warmup_questions": warmup_questions,
        "postview_scaffolding_enabled": postview_scaffolding_enabled,
        "postview_questions": postview_questions,
    }


def _class_screen_payload(class_id: str, origin: str, display_language: str = "ja") -> dict | None:
    """教室スクリーン投影向け。管理画面で選択した語彙・導入質問をそのまま返す。"""
    cls = get_class(class_id)
    if not cls:
        return None
    current = cls.get("current") or {}
    lang = resolve_display_language(display_language)
    show_assistive = lang != "en"
    video_id = (current.get("video_id") or "").strip()
    start_sec = int(current.get("start_seconds") or 0)
    end_sec = int(current.get("end_seconds") or 0)
    subtitles_enabled = bool(current.get("subtitles_enabled", False))
    vocabulary_data = (
        vocabulary_for_student(
            current.get("vocabulary_data") if isinstance(current.get("vocabulary_data"), list) else [],
            lang,
        )
        if show_assistive
        else []
    )
    warmup_image_url = str(current.get("warmup_image_url") or "").strip()
    warmup_questions = selected_display_questions(current.get("warmup_questions"))
    postview_questions = selected_display_questions(current.get("postview_questions"))
    embed_url = (
        build_youtube_embed_url(
            video_id,
            start_sec,
            end_sec,
            origin=origin,
            subtitles_enabled=subtitles_enabled,
        )
        if video_id
        else ""
    )
    return {
        "id": cls["id"],
        "name": cls["name"],
        "video": {
            "video_id": video_id,
            "start_seconds": start_sec,
            "end_seconds": end_sec,
            "embed_url": embed_url,
            "subtitles_enabled": subtitles_enabled,
        },
        "vocabulary_data": vocabulary_data,
        "warmup_image_url": warmup_image_url,
        "warmup_questions": warmup_questions,
        "postview_questions": postview_questions,
        "has_video": bool(video_id),
        "has_vocab": bool(vocabulary_data),
        "has_warmup": bool(warmup_image_url or warmup_questions),
        "has_postview": bool(postview_questions),
    }


@main_bp.route("/")
def index():
    state = load_state()
    default_level = resolve_cefr_level(state.get("default_cefr_level"))
    level = resolve_cefr_level(request.args.get("level"), fallback=default_level)
    class_id = (request.args.get("class") or get_active_class_id()).strip()
    classes = list_classes()
    cls = get_class(class_id) if class_id else None
    current = (cls or {}).get("current") or {}
    lang = resolve_display_language(state.get("display_language"))
    show_assistive = lang != "en"
    vocabulary_scaffolding_enabled = bool(current.get("vocabulary_scaffolding_enabled", False)) and show_assistive
    vocabulary_data = current.get("vocabulary_data") if isinstance(current.get("vocabulary_data"), list) else []
    if not vocabulary_scaffolding_enabled:
        vocabulary_data = []
    else:
        vocabulary_data = vocabulary_for_student(vocabulary_data, lang)
    translation = script_translation_for_lang(current, lang) if show_assistive else {"enabled": False, "text": "", "pairs": []}

    return render_template(
        "news/index.html",
        state=state,
        cefr_levels=CEFR_LEVELS,
        initial_level=level,
        initial_class_id=class_id,
        classes=classes,
        page_origin=request.host_url.rstrip("/"),
        vocabulary_scaffolding_enabled=vocabulary_scaffolding_enabled,
        vocabulary_data=vocabulary_data,
        translation_enabled=bool(translation.get("enabled")),
        translation_pairs=translation.get("pairs") or [],
        **appearance_context(state),
    )


@main_bp.route("/api/classes", methods=["GET"])
def api_classes():
    return jsonify({"ok": True, "classes": list_classes()})


@main_bp.route("/screen/")
def screen():
    class_id = (request.args.get("class") or get_active_class_id()).strip()
    classes = list_classes()
    return render_template(
        "news/screen.html",
        initial_class_id=class_id,
        classes=classes,
        page_origin=request.host_url.rstrip("/"),
        **appearance_context(),
    )


@main_bp.route("/api/screen")
def screen_config():
    class_id = (request.args.get("class_id") or request.args.get("class") or "").strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラス ID が必要です。"}), 400

    origin = request.host_url.rstrip("/")
    state = load_state()
    display_language = resolve_display_language(state.get("display_language"))
    payload = _class_screen_payload(class_id, origin, display_language)
    if not payload:
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    return jsonify(
        {
            "ok": True,
            "display_language": display_language,
            "page_origin": origin,
            "class": payload,
        }
    )


@main_bp.route("/api/config")
def public_config():
    class_id = (request.args.get("class_id") or "").strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラス ID が必要です。"}), 400

    origin = request.host_url.rstrip("/")
    state = load_state()
    display_language = resolve_display_language(state.get("display_language"))
    payload = _class_public_payload(class_id, origin, display_language)
    if not payload:
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    return jsonify(
        {
            "ok": True,
            "display_language": display_language,
            "page_origin": origin,
            "class": payload,
        }
    )


@main_bp.route("/api/evaluate", methods=["POST"])
def evaluate():
    data = request.get_json(silent=True) or {}
    state = load_state()
    default_level = resolve_cefr_level(state.get("default_cefr_level"))
    raw_level = (data.get("level") or "").strip()
    if raw_level and raw_level.upper() not in CEFR_LEVELS:
        return jsonify({"ok": False, "error": f"CEFR レベルは {', '.join(CEFR_LEVELS)} のいずれかです。"}), 400
    level = resolve_cefr_level(raw_level, fallback=default_level)
    summary = (data.get("summary") or "").strip()
    class_id = (data.get("class_id") or "").strip()
    student_hr_class = str(data.get("student_hr_class") or "").strip()
    student_number = str(data.get("student_number") or "").strip()
    student_name = str(data.get("student_name") or "").strip()

    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択してください。"}), 400

    cls = get_class(class_id)
    if not cls:
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    reference_script = (cls.get("current") or {}).get("script") or ""
    if not reference_script.strip():
        return jsonify(
            {"ok": False, "error": "このクラスには参照スクリプトが未設定です。管理画面で設定してください。"},
        ), 400

    model = resolve_eval_ai_model(
        state.get("ai_eval_model"),
        fallback=resolve_ai_model(state.get("ai_model")),
    )
    api_key = get_openai_api_key()
    rubric = get_evaluation_rubric(class_id, level)

    try:
        evaluation = evaluate_summary(
            level, reference_script, summary, model, api_key, rubric_override=rubric
        )
        feedback = evaluation["feedback"]
        score_feedback = evaluation["score_feedback"]
        if student_number or student_name:
            lesson = current_lesson_identity(cls)
            save_submission(
                class_id=class_id,
                class_name=cls.get("name") or class_id,
                student_hr_class=student_hr_class,
                student_number=student_number,
                student_name=student_name,
                transcript=summary,
                feedback=score_feedback,
                level=level,
                lesson_title=lesson["lesson_title"],
                lesson_key_value=lesson["lesson_key"],
                lesson_video_id=lesson["lesson_video_id"],
                lesson_start_seconds=lesson["lesson_start_seconds"],
                lesson_end_seconds=lesson["lesson_end_seconds"],
            )
        return jsonify({"ok": True, "feedback": feedback, "level": level, "class_id": class_id})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"評価に失敗しました: {exc}"}), 500


@main_bp.route("/api/transcribe", methods=["POST"])
def transcribe_media():
    class_id = (request.form.get("class_id") or "").strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択してください。"}), 400
    if not get_class(class_id):
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    uploaded = request.files.get("audio") or request.files.get("media")
    if uploaded is None:
        return jsonify({"ok": False, "error": "動画またはボイスメモを選択してください。"}), 400

    uploaded.stream.seek(0, 2)
    size = uploaded.stream.tell()
    uploaded.stream.seek(0)
    if size <= 0:
        return jsonify({"ok": False, "error": "ファイルが空です。別のファイルを選んでください。"}), 400
    if size > TRANSCRIBE_MAX_BYTES:
        return jsonify(
            {"ok": False, "error": "ファイルが大きすぎます。ボイスメモか、より短い動画にしてください。"},
        ), 413

    ext = _media_extension(uploaded.filename, uploaded.mimetype)
    if not ext:
        return jsonify(
            {"ok": False, "error": "対応していない形式です。動画（mp4 / mov）か音声（m4a / mp3 / wav）を選んでください。"},
        ), 400

    try:
        with tempfile.TemporaryDirectory(prefix="news-stt-") as tmp:
            src_path = Path(tmp) / f"upload.{ext}"
            uploaded.save(src_path)
            prepared = prepare_for_whisper(src_path, TRANSCRIBE_MAX_SECONDS)
            transcript = transcribe_audio(prepared)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("news transcription failed")
        return jsonify({"ok": False, "error": f"文字起こしに失敗しました: {exc}"}), 500

    if not transcript:
        return jsonify(
            {"ok": False, "error": "音声を認識できませんでした。もう一度録音するか、別のファイルを選んでください。"},
        ), 400

    return jsonify({"ok": True, "transcript": transcript})
