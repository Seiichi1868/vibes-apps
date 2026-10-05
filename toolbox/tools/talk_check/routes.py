from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from flask import jsonify, render_template, request
from werkzeug.utils import secure_filename

from toolbox.auth import current_user, login_required
from toolbox.config import ALLOWED_AUDIO_EXTENSIONS, AUDIO_TMP_DIR, MAX_AUDIO_BYTES, ensure_dirs
from toolbox.routes import tool_required
from toolbox.storage import (
    delete_talk_session,
    get_setting,
    list_talk_sessions,
    load_talk_session,
    new_id,
    now_iso,
    save_talk_session,
)
from toolbox.tools.talk_check.generate import LEVELS, generate_questions, generate_replacement_question, make_title
from toolbox.usage import UsageError, UsageLimitError, record_event, transcribe_file

logger = logging.getLogger(__name__)


def _error(exc, fallback: str):
    if isinstance(exc, UsageLimitError):
        return jsonify({"ok": False, "error": exc.message, "code": "limit"}), 429
    if isinstance(exc, UsageError):
        return jsonify({"ok": False, "error": exc.message}), 400
    logger.exception(fallback)
    return jsonify({"ok": False, "error": fallback}), 500


def _public_session(session: dict, *, include_questions: bool = False) -> dict:
    row = {
        "id": session.get("id"),
        "title": session.get("title"),
        "level": session.get("level"),
        "question_count": session.get("question_count"),
        "source": session.get("source"),
        "created_at": session.get("created_at"),
        "keywords": session.get("keywords") or "",
    }
    if include_questions:
        row["transcript"] = session.get("transcript") or ""
        row["questions"] = session.get("questions_json") or []
        row["wait_prompt"] = session.get("wait_prompt") or "Talk with your partner. What did you hear?"
    return row


def register(bp):
    @bp.route("/talk-check")
    @login_required
    @tool_required("talk_check")
    def talk_check_page():
        user = current_user()
        return render_template(
            "toolbox/tools/talk_check.html",
            sessions=[_public_session(row) for row in list_talk_sessions(user["id"])],
            parallel_browser_stt=bool(get_setting("parallel_browser_stt", True)),
            levels=LEVELS,
        )

    @bp.route("/api/talk/transcribe", methods=["POST"])
    @login_required
    @tool_required("talk_check")
    def api_transcribe():
        user = current_user()
        upload = request.files.get("audio")
        if not upload or not upload.filename:
            return jsonify({"ok": False, "error": "音声ファイルを選んでください。"}), 400
        filename = secure_filename(upload.filename)
        ext = Path(filename).suffix.lower().lstrip(".")
        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            return jsonify({"ok": False, "error": "対応していない音声形式です。webm / mp3 / wav / m4a などを使ってください。"}), 400
        upload.seek(0, os.SEEK_END)
        size = upload.tell()
        upload.seek(0)
        if size > MAX_AUDIO_BYTES:
            return jsonify({"ok": False, "error": "ファイルが大きすぎます。25MB以内にしてください。"}), 400
        try:
            duration_sec = float(request.form.get("duration_sec") or 0)
        except (TypeError, ValueError):
            duration_sec = 0
        keywords = (request.form.get("keywords") or "").strip()[:200]
        ensure_dirs()
        handle = tempfile.NamedTemporaryFile(delete=False, dir=AUDIO_TMP_DIR, suffix=f".{ext}")
        tmp_path = Path(handle.name)
        try:
            upload.save(handle)
            handle.close()
            text = transcribe_file(
                file_path=tmp_path,
                duration_sec=duration_sec,
                keywords=keywords,
                user_id=user["id"],
                tool_id="talk_check",
            )
        except (UsageError, UsageLimitError) as exc:
            return _error(exc, "文字起こしに失敗しました。")
        except Exception as exc:
            return _error(exc, "文字起こしに失敗しました。テキスト貼り付けを試してください。")
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("failed to delete temp audio %s", tmp_path)
        if not text:
            return jsonify({"ok": False, "error": "文字が起こせませんでした。テキスト貼り付けを試してください。"}), 400
        return jsonify({"ok": True, "transcript": text})

    @bp.route("/api/talk/generate", methods=["POST"])
    @login_required
    @tool_required("talk_check")
    def api_generate():
        user = current_user()
        payload = request.get_json(silent=True) or {}
        transcript = str(payload.get("transcript") or "").strip()
        level = str(payload.get("level") or "A2").upper()
        try:
            count = int(payload.get("count") or 5)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "問題数は数字で指定してください。"}), 400
        include_inference = bool(payload.get("include_inference"))
        notes = str(payload.get("notes") or "")[:400]
        source = str(payload.get("source") or "paste")
        if source not in ("record", "file", "paste"):
            source = "paste"
        wait_prompt = str(payload.get("wait_prompt") or "").strip() or "Talk with your partner. What did you hear?"
        keywords = str(payload.get("keywords") or "").strip()[:200]
        try:
            questions = generate_questions(
                transcript=transcript,
                level=level,
                count=count,
                include_inference=include_inference,
                notes=notes,
                user_id=user["id"],
            )
        except (UsageError, UsageLimitError) as exc:
            return _error(exc, "問題を作れませんでした。")
        session = {
            "id": new_id(),
            "user_id": user["id"],
            "created_at": now_iso(),
            "title": make_title(transcript),
            "level": level,
            "question_count": len(questions),
            "source": source,
            "keywords": keywords,
            "transcript": transcript,
            "questions_json": questions,
            "wait_prompt": wait_prompt,
        }
        save_talk_session(session)
        return jsonify({"ok": True, "session_id": session["id"], "questions": questions})

    @bp.route("/api/talk/regenerate-one", methods=["POST"])
    @login_required
    @tool_required("talk_check")
    def api_regenerate_one():
        user = current_user()
        payload = request.get_json(silent=True) or {}
        session = load_talk_session(str(payload.get("session_id") or ""), user["id"])
        if not session:
            return jsonify({"ok": False, "error": "履歴が見つかりません。"}), 404
        try:
            index = int(payload.get("index"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "問題番号が不正です。"}), 400
        questions = list(session.get("questions_json") or [])
        if index < 0 or index >= len(questions):
            return jsonify({"ok": False, "error": "その問題はありません。"}), 404
        try:
            replacement = generate_replacement_question(
                transcript=session.get("transcript") or "",
                level=session.get("level") or "A2",
                existing_questions=questions,
                replace_type=str((questions[index] or {}).get("type") or "fact"),
                notes="Make a clearly different question from the one being replaced.",
                user_id=user["id"],
            )
        except (UsageError, UsageLimitError) as exc:
            return _error(exc, "作り直しに失敗しました。")
        replacement["order"] = index + 1
        questions[index] = replacement
        session["questions_json"] = questions
        save_talk_session(session)
        return jsonify({"ok": True, "question": replacement})

    @bp.route("/api/talk/sessions")
    @login_required
    def api_list_sessions():
        rows = [_public_session(row) for row in list_talk_sessions(current_user()["id"])]
        return jsonify({"ok": True, "sessions": rows})

    @bp.route("/api/talk/sessions/<session_id>")
    @login_required
    def api_get_session(session_id):
        session = load_talk_session(session_id, current_user()["id"])
        if not session:
            return jsonify({"ok": False, "error": "履歴が見つかりません。"}), 404
        return jsonify({"ok": True, "session": _public_session(session, include_questions=True)})

    @bp.route("/api/talk/sessions/<session_id>", methods=["DELETE"])
    @login_required
    def api_delete_session(session_id):
        if not delete_talk_session(session_id, current_user()["id"]):
            return jsonify({"ok": False, "error": "履歴が見つかりません。"}), 404
        return jsonify({"ok": True})

    @bp.route("/api/talk/sessions/<session_id>", methods=["PUT"])
    @login_required
    def api_update_session(session_id):
        session = load_talk_session(session_id, current_user()["id"])
        if not session:
            return jsonify({"ok": False, "error": "履歴が見つかりません。"}), 404
        payload = request.get_json(silent=True) or {}
        if "title" in payload:
            title = str(payload.get("title") or "").strip()
            if title:
                session["title"] = title[:80]
        if "wait_prompt" in payload:
            session["wait_prompt"] = str(payload.get("wait_prompt") or "").strip()[:160]
        save_talk_session(session)
        return jsonify({"ok": True, "session": _public_session(session, include_questions=True)})

    @bp.route("/api/talk/events", methods=["POST"])
    @login_required
    def api_talk_event():
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name") or "").strip()
        if name not in ("browser_stt_parallel_on", "browser_stt_parallel_off", "browser_stt_auto_stop"):
            return jsonify({"ok": False, "error": "不明なイベントです。"}), 400
        record_event(current_user()["id"], "talk_check", name)
        return jsonify({"ok": True})
