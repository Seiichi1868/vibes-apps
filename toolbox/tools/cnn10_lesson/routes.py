"""CNN10 授業ページと、News とは別の字幕 API。"""
from __future__ import annotations

import logging

from flask import jsonify, render_template, request

from toolbox.auth import login_required
from toolbox.config import DEFAULT_GENERATE_MODEL, get_openai_api_key
from toolbox.routes import tool_required
from toolbox.services.cnn10 import fetch_cnn10_episodes
from toolbox.services.cnn10_highlight import find_title_segment_in_transcript
from toolbox.storage import get_setting
from toolbox.services.youtube_transcript import (
    TranscriptNotFound,
    TranscriptRateLimited,
    fetch_timedtext_from_url,
    fetch_via_worker_relay,
    fetch_youtube_transcript,
)
from toolbox.tools.cnn10_lesson.assist import (
    extract_questions,
    extract_vocabulary,
    extract_writing,
    translate_script,
)
from toolbox.tools.cnn10_lesson.store import (
    archive_current,
    delete_archive,
    get_archive,
    list_archives,
    load_lesson,
    restore_archive,
    save_lesson,
)

logger = logging.getLogger(__name__)


def register(bp):
    @bp.route("/cnn10")
    @login_required
    @tool_required("cnn10")
    def cnn10_lesson_page():
        return render_template(
            "toolbox/tools/cnn10_lesson.html",
            lesson=load_lesson(),
            archives=list_archives(),
        )

    @bp.route("/cnn10/screen")
    @login_required
    @tool_required("cnn10")
    def cnn10_screen_page():
        return render_template(
            "toolbox/tools/cnn10_screen.html",
            archive_id=(request.args.get("archive") or "").strip(),
        )

    @bp.route("/api/cnn10/episodes")
    @login_required
    @tool_required("cnn10")
    def cnn10_episodes():
        try:
            offset = int(request.args.get("offset") or 0)
            limit = int(request.args.get("limit") or 10)
        except ValueError:
            return jsonify({"ok": False, "error": "offset と limit は数値です。"}), 400
        try:
            data = fetch_cnn10_episodes(offset=offset, limit=limit)
        except Exception as exc:
            logger.exception("toolbox cnn10 episodes failed")
            return jsonify({"ok": False, "error": str(exc)}), 502
        return jsonify({"ok": True, **data})

    @bp.route("/api/cnn10/highlight", methods=["POST"])
    @login_required
    @tool_required("cnn10")
    def cnn10_highlight():
        payload = request.get_json(silent=True) or {}
        title = str(payload.get("title") or "").strip()
        snippets = payload.get("snippets") or []
        if not title:
            return jsonify({"ok": False, "error": "タイトルが必要です。"}), 400
        if not isinstance(snippets, list) or not snippets:
            return jsonify({"ok": False, "error": "文字起こしデータが必要です。"}), 400
        if not get_openai_api_key():
            return jsonify({"ok": True, "highlight": {"ok": False, "error": "OpenAI API キーが未設定です。"}})
        model = str(get_setting("generate_model") or DEFAULT_GENERATE_MODEL)
        try:
            highlight = find_title_segment_in_transcript(
                title, snippets, model=model, api_key=get_openai_api_key()
            )
        except ValueError as exc:
            return jsonify({"ok": True, "highlight": {"ok": False, "error": str(exc)}})
        except Exception as exc:
            logger.exception("toolbox cnn10 highlight failed")
            return jsonify({"ok": False, "error": str(exc)}), 502
        return jsonify({"ok": True, "highlight": highlight})

    @bp.route("/api/cnn10/lesson", methods=["GET", "POST"])
    @login_required
    @tool_required("cnn10")
    def cnn10_lesson_api():
        if request.method == "GET":
            archive_id = (request.args.get("archive") or "").strip()
            if archive_id:
                lesson = get_archive(archive_id)
                if not lesson:
                    return jsonify({"ok": False, "error": "アーカイブが見つかりません。"}), 404
                return jsonify({"ok": True, "lesson": lesson})
            return jsonify({"ok": True, "lesson": load_lesson(), "archives": list_archives()})
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "JSON が必要です。"}), 400
        return jsonify({"ok": True, "lesson": save_lesson(payload)})

    @bp.route("/api/cnn10/archive", methods=["GET", "POST"])
    @login_required
    @tool_required("cnn10")
    def cnn10_archive():
        if request.method == "GET":
            return jsonify({"ok": True, "archives": list_archives()})
        payload = request.get_json(silent=True) or {}
        if payload.get("lesson"):
            save_lesson(payload["lesson"])
        try:
            item = archive_current(
                str(payload.get("title") or ""),
                str(payload.get("lesson_name") or ""),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "archive": item, "archives": list_archives()})

    @bp.route("/api/cnn10/archive/restore", methods=["POST"])
    @login_required
    @tool_required("cnn10")
    def cnn10_archive_restore():
        payload = request.get_json(silent=True) or {}
        try:
            lesson = restore_archive(str(payload.get("archive_id") or ""))
        except LookupError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        return jsonify({"ok": True, "lesson": lesson})

    @bp.route("/api/cnn10/archive/delete", methods=["POST"])
    @login_required
    @tool_required("cnn10")
    def cnn10_archive_delete():
        payload = request.get_json(silent=True) or {}
        try:
            delete_archive(str(payload.get("archive_id") or ""))
        except LookupError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        return jsonify({"ok": True, "archives": list_archives()})

    @bp.route("/api/cnn10/assist", methods=["POST"])
    @login_required
    @tool_required("cnn10")
    def cnn10_assist():
        payload = request.get_json(silent=True) or {}
        script = str(payload.get("script") or "").strip()
        kind = str(payload.get("kind") or "")
        if not script:
            return jsonify({"ok": False, "error": "文字起こしを先に入れてください。"}), 400
        try:
            if kind == "vocab":
                result = {"vocabulary": extract_vocabulary(script, str(payload.get("min_cefr") or "B1"))}
            elif kind in {"warmup", "discussion"}:
                result = {kind: extract_questions(script, kind)}
            elif kind == "translation":
                result = {"translation": translate_script(script)}
            elif kind == "writing":
                result = {"writing": extract_writing(script)}
            else:
                return jsonify({"ok": False, "error": "kind が不正です。"}), 400
        except Exception as exc:
            logger.exception("toolbox cnn10 assist failed")
            return jsonify({"ok": False, "error": str(exc)}), 502
        lesson = save_lesson({**load_lesson(), "script": script, **result})
        return jsonify({"ok": True, "lesson": lesson})

    def _transcript_response(loader):
        raw_id = (request.args.get("id") or "").strip()
        if not raw_id and request.args.get("url"):
            raw_id = request.args.get("url")
        if not raw_id:
            return jsonify({"ok": False, "error": "動画 ID を指定してください (?id=VIDEO_ID)。"}), 400
        try:
            payload = loader(raw_id)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except TranscriptRateLimited as exc:
            return jsonify({"ok": False, "error": str(exc)}), 429
        except TranscriptNotFound as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        except Exception:
            logger.exception("toolbox youtube transcript failed")
            return jsonify({"ok": False, "error": "字幕の取得に失敗しました。"}), 502
        return jsonify(payload)

    @bp.route("/api/youtube-transcript")
    @login_required
    @tool_required("cnn10")
    def toolbox_youtube_transcript():
        return _transcript_response(fetch_youtube_transcript)

    @bp.route("/api/youtube-transcript-worker")
    @login_required
    @tool_required("cnn10")
    def toolbox_youtube_transcript_worker():
        return _transcript_response(fetch_via_worker_relay)

    @bp.route("/api/youtube-timedtext")
    @login_required
    @tool_required("cnn10")
    def toolbox_youtube_timedtext():
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
            logger.exception("toolbox timedtext failed")
            return jsonify({"ok": False, "error": "字幕の取得に失敗しました。"}), 502
        return jsonify(payload)
