from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from flask import jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from toolbox.auth import current_user, login_required
from toolbox.config import ALLOWED_AUDIO_EXTENSIONS, MAX_AUDIO_BYTES, TALK_AUDIO_DIR, ensure_dirs
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
from toolbox.storage import JST
from toolbox.tools.talk_check.generate import LEVELS, generate_questions, generate_replacement_question, make_title
from toolbox.usage import UsageError, UsageLimitError, _is_reasoning_model, record_event, selected_model, transcribe_file

logger = logging.getLogger(__name__)

ARCHIVE_INTERVAL_DAYS = 30
ARCHIVE_FOLDER_NAME = "ToolboxTalkAudio"


def _error(exc, fallback: str):
    if isinstance(exc, UsageLimitError):
        return jsonify({"ok": False, "error": exc.message, "code": "limit"}), 429
    if isinstance(exc, UsageError):
        return jsonify({"ok": False, "error": exc.message}), 400
    logger.exception(fallback)
    return jsonify({"ok": False, "error": fallback}), 500


def _public_session(session: dict, *, include_questions: bool = False) -> dict:
    questions = session.get("questions_json") or []
    row = {
        "id": session.get("id"),
        "title": session.get("title"),
        "level": session.get("level"),
        "question_count": session.get("question_count") if session.get("question_count") is not None else len(questions),
        "source": session.get("source"),
        "created_at": session.get("created_at"),
        "keywords": session.get("keywords") or "",
        "duration_sec": session.get("duration_sec") or 0,
        "has_audio": bool(session.get("audio_file")),
        "local_audio": session.get("local_audio") or "",
        "status": session.get("status") or ("ready" if questions else "transcribed"),
        "has_transcript": bool((session.get("transcript") or "").strip()),
        "last_error": session.get("last_error") or "",
    }
    if include_questions:
        row["transcript"] = session.get("transcript") or ""
        row["browser_transcript"] = session.get("browser_transcript") or ""
        row["questions"] = questions
        row["wait_prompt"] = session.get("wait_prompt") or "Talk with your partner. What did you hear?"
        row["notes"] = session.get("notes") or ""
        row["include_inference"] = bool(session.get("include_inference"))
        row["count_requested"] = session.get("count_requested") or len(questions)
    return row


def _title_for(session: dict) -> str:
    if (session.get("transcript") or "").strip():
        return make_title(session["transcript"])
    stamp = (session.get("created_at") or now_iso()).replace("T", " ")[5:16]
    return f"録音 {stamp}"


def _clean_edit_questions(raw) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        q_type = "inference" if item.get("type") == "inference" else "fact"
        out.append(
            {
                "id": str(item.get("id") or new_id())[:20],
                "order": index + 1,
                "question": question[:400],
                "model_answer": str(item.get("model_answer") or "").strip()[:400],
                "short_answer": str(item.get("short_answer") or "").strip()[:200],
                "type": q_type,
                "evidence": str(item.get("evidence") or "").strip()[:500],
                "section": str(item.get("section") or "").strip()[:60],
                "included": item.get("included") is not False,
            }
        )
    return out


def register(bp):
    @bp.route("/talk-check")
    @login_required
    @tool_required("talk_check")
    def talk_check_page():
        user = current_user()
        model_id = selected_model("generate")
        return render_template(
            "toolbox/tools/talk_check.html",
            sessions=[_public_session(row) for row in list_talk_sessions(user["id"])],
            parallel_browser_stt=bool(get_setting("parallel_browser_stt", True)),
            levels=LEVELS,
            generate_reasoning=_is_reasoning_model(model_id),
        )

    @bp.route("/api/talk/audio", methods=["POST"])
    @login_required
    @tool_required("talk_check")
    def api_save_audio():
        """録音／音声ファイルを先に保存し、文字起こしや生成が失敗しても残るようにする。"""
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
        source = str(request.form.get("source") or "record")
        if source not in ("record", "file"):
            source = "record"
        ensure_dirs()
        session_id = new_id()
        audio_name = f"{session_id}.{ext}"
        upload.save(TALK_AUDIO_DIR / audio_name)
        session = {
            "id": session_id,
            "user_id": user["id"],
            "created_at": now_iso(),
            "level": str(request.form.get("level") or "A2"),
            "source": source,
            "keywords": (request.form.get("keywords") or "").strip()[:200],
            "duration_sec": max(0, round(duration_sec)),
            "audio_file": audio_name,
            "browser_transcript": (request.form.get("browser_transcript") or "").strip()[:60000],
            "transcript": "",
            "questions_json": [],
            "question_count": 0,
            "status": "recorded",
            "wait_prompt": "Talk with your partner. What did you hear?",
        }
        session["title"] = _title_for(session)
        save_talk_session(session)
        return jsonify({"ok": True, "session_id": session_id, "session": _public_session(session)})

    @bp.route("/api/talk/transcribe", methods=["POST"])
    @login_required
    @tool_required("talk_check")
    def api_transcribe():
        user = current_user()
        payload = request.get_json(silent=True) or {}
        session = load_talk_session(str(payload.get("session_id") or ""), user["id"])
        if not session or not session.get("audio_file"):
            return jsonify({"ok": False, "error": "保存された音声が見つかりません。"}), 404
        audio_path = TALK_AUDIO_DIR / Path(str(session["audio_file"])).name
        if not audio_path.is_file():
            return jsonify({"ok": False, "error": "音声ファイルが見つかりません。"}), 404
        keywords = str(payload.get("keywords") or session.get("keywords") or "").strip()[:200]
        try:
            text = transcribe_file(
                file_path=audio_path,
                duration_sec=float(session.get("duration_sec") or 0),
                keywords=keywords,
                user_id=user["id"],
                tool_id="talk_check",
            )
        except (UsageError, UsageLimitError) as exc:
            session["last_error"] = getattr(exc, "message", str(exc))
            save_talk_session(session)
            return _error(exc, "文字起こしに失敗しました。")
        except Exception as exc:
            session["last_error"] = "文字起こしに失敗しました。"
            save_talk_session(session)
            return _error(exc, "文字起こしに失敗しました。保存済みの音声から再試行できます。")
        if not text:
            session["last_error"] = "文字が起こせませんでした。"
            save_talk_session(session)
            return jsonify({"ok": False, "error": "文字が起こせませんでした。保存済みの音声から再試行するか、テキスト貼り付けを使ってください。"}), 400
        session["transcript"] = text
        session["keywords"] = keywords
        session["last_error"] = ""
        if session.get("status") == "recorded":
            session["status"] = "transcribed"
        if not session.get("questions_json"):
            session["title"] = _title_for(session)
        save_talk_session(session)
        return jsonify({"ok": True, "transcript": text, "session_id": session["id"]})

    @bp.route("/api/talk/sessions", methods=["POST"])
    @login_required
    @tool_required("talk_check")
    def api_create_text_session():
        """貼り付けテキストを先に保存する（生成に失敗しても残る）。"""
        user = current_user()
        payload = request.get_json(silent=True) or {}
        transcript = str(payload.get("transcript") or "").strip()[:60000]
        if not transcript:
            return jsonify({"ok": False, "error": "英文を貼り付けてください。"}), 400
        session = {
            "id": new_id(),
            "user_id": user["id"],
            "created_at": now_iso(),
            "level": str(payload.get("level") or "A2"),
            "source": "paste",
            "keywords": "",
            "duration_sec": 0,
            "transcript": transcript,
            "questions_json": [],
            "question_count": 0,
            "status": "transcribed",
            "wait_prompt": "Talk with your partner. What did you hear?",
        }
        session["title"] = _title_for(session)
        save_talk_session(session)
        return jsonify({"ok": True, "session_id": session["id"], "session": _public_session(session)})

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

        session = None
        session_id = str(payload.get("session_id") or "")
        if session_id:
            session = load_talk_session(session_id, user["id"])
        if session is not None and transcript:
            # 確認・修正された文字起こしも先に保存しておく
            session["transcript"] = transcript
            save_talk_session(session)

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
            if session is not None:
                session["last_error"] = getattr(exc, "message", str(exc))
                save_talk_session(session)
            return _error(exc, "問題を作れませんでした。")
        except Exception as exc:
            if session is not None:
                session["last_error"] = "問題を作れませんでした。"
                save_talk_session(session)
            return _error(exc, "問題を作れませんでした。保存済みの文字起こしから再試行できます。")

        if session is None:
            session = {
                "id": new_id(),
                "user_id": user["id"],
                "created_at": now_iso(),
                "duration_sec": 0,
            }
        session.update(
            {
                "level": level,
                "source": source if (payload.get("source") or not session.get("source")) else session["source"],
                "keywords": keywords,
                "transcript": transcript,
                "questions_json": questions,
                "question_count": len(questions),
                "count_requested": count,
                "notes": notes,
                "include_inference": include_inference,
                "wait_prompt": wait_prompt,
                "status": "ready",
                "last_error": "",
            }
        )
        session["title"] = make_title(transcript)
        save_talk_session(session)
        return jsonify({"ok": True, "session_id": session["id"], "questions": questions, "session": _public_session(session)})

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
                replace_section=str((questions[index] or {}).get("section") or ""),
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

    @bp.route("/api/talk/sessions/<session_id>/audio")
    @login_required
    def api_session_audio(session_id):
        session = load_talk_session(session_id, current_user()["id"])
        if not session or not session.get("audio_file"):
            return jsonify({"ok": False, "error": "音声がありません。"}), 404
        path = TALK_AUDIO_DIR / Path(str(session["audio_file"])).name
        if not path.is_file():
            return jsonify({"ok": False, "error": "音声がありません。"}), 404
        mime = mimetypes.guess_type(path.name)[0] or "audio/webm"
        return send_file(path, mimetype=mime, conditional=True)

    def _drop_server_audio(session: dict) -> None:
        name = session.get("audio_file")
        if name:
            try:
                (TALK_AUDIO_DIR / Path(str(name)).name).unlink(missing_ok=True)
            except OSError:
                logger.warning("failed to delete talk audio %s", name)
        session["audio_file"] = ""

    @bp.route("/api/talk/sessions/<session_id>/audio-local", methods=["POST"])
    @login_required
    def api_audio_local(session_id):
        """音声をこのパソコンのフォルダへ保存したことを記録し、必要ならサーバー上の音声を消す。"""
        session = load_talk_session(session_id, current_user()["id"])
        if not session:
            return jsonify({"ok": False, "error": "履歴が見つかりません。"}), 404
        payload = request.get_json(silent=True) or {}
        filename = Path(str(payload.get("filename") or "")).name[:120]
        if filename:
            session["local_audio"] = filename
        if payload.get("release") and session.get("local_audio"):
            _drop_server_audio(session)
        save_talk_session(session)
        return jsonify({"ok": True, "session": _public_session(session)})

    # ── Safari など、フォルダへ直接書き込めないブラウザ向け：まとめてダウンロード ──

    def _server_audio_sessions(user_id: str) -> list[dict]:
        rows = []
        for row in list_talk_sessions(user_id):
            name = row.get("audio_file")
            if name and (TALK_AUDIO_DIR / Path(str(name)).name).is_file():
                rows.append(row)
        return rows

    def _archive_name(session: dict) -> str:
        digits = "".join(ch for ch in str(session.get("created_at") or "") if ch.isdigit())
        stamp = f"{digits[:8]}-{digits[8:12]}" if len(digits) >= 12 else "unknown"
        ext = Path(str(session.get("audio_file") or "")).suffix or ".webm"
        return f"{stamp}_{session['id']}{ext}"

    @bp.route("/api/talk/audio-archive")
    @login_required
    def api_audio_archive_status():
        rows = _server_audio_sessions(current_user()["id"])
        awaiting = [r for r in rows if r.get("audio_downloaded_at")]
        oldest = min((str(r.get("created_at") or "") for r in rows), default="")
        total = 0
        for r in rows:
            try:
                total += (TALK_AUDIO_DIR / Path(str(r["audio_file"])).name).stat().st_size
            except OSError:
                pass
        due = bool(awaiting)
        if oldest and not due:
            try:
                created = datetime.fromisoformat(oldest)
                if created.tzinfo is None:
                    created = created.replace(tzinfo=JST)
                age = datetime.now(JST) - created
                due = age >= timedelta(days=ARCHIVE_INTERVAL_DAYS)
            except ValueError:
                pass
        return jsonify(
            {
                "ok": True,
                "count": len(rows),
                "awaiting": len(awaiting),
                "bytes": total,
                "oldest_at": oldest,
                "due": due,
                "folder": ARCHIVE_FOLDER_NAME,
            }
        )

    @bp.route("/api/talk/audio-archive.zip")
    @login_required
    def api_audio_archive_zip():
        """サーバー上の音声をまとめた zip を返す。ダウンロード済みの印を付け、確認後に削除する。"""
        rows = _server_audio_sessions(current_user()["id"])
        if not rows:
            return jsonify({"ok": False, "error": "ダウンロードする音声はありません。"}), 404
        tmp = tempfile.TemporaryFile()
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
            for row in rows:
                zf.write(TALK_AUDIO_DIR / Path(str(row["audio_file"])).name, _archive_name(row))
        stamp = now_iso()
        for row in rows:
            row["audio_downloaded_at"] = stamp
            row["audio_download_name"] = _archive_name(row)
            save_talk_session(row)
        tmp.seek(0)
        return send_file(
            tmp,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{ARCHIVE_FOLDER_NAME}-{stamp[:10].replace('-', '')}.zip",
        )

    @bp.route("/api/talk/audio-archive/confirm", methods=["POST"])
    @login_required
    def api_audio_archive_confirm():
        """指定フォルダへ移したことの確認。ダウンロード済みの音声をサーバーから消す。"""
        released = 0
        for row in list_talk_sessions(current_user()["id"]):
            if not row.get("audio_downloaded_at") or not row.get("audio_file"):
                continue
            row["local_audio"] = row.get("audio_download_name") or row.get("local_audio") or ""
            _drop_server_audio(row)
            row.pop("audio_downloaded_at", None)
            row.pop("audio_download_name", None)
            save_talk_session(row)
            released += 1
        return jsonify({"ok": True, "released": released})

    @bp.route("/api/talk/sessions/<session_id>/audio-upload", methods=["POST"])
    @login_required
    @tool_required("talk_check")
    def api_audio_upload(session_id):
        """ローカル保存済みの音声を、文字起こし用に一時的にサーバーへ戻す。"""
        session = load_talk_session(session_id, current_user()["id"])
        if not session:
            return jsonify({"ok": False, "error": "履歴が見つかりません。"}), 404
        upload = request.files.get("audio")
        if not upload or not upload.filename:
            return jsonify({"ok": False, "error": "音声ファイルがありません。"}), 400
        ext = Path(secure_filename(upload.filename)).suffix.lower().lstrip(".")
        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            return jsonify({"ok": False, "error": "対応していない音声形式です。"}), 400
        upload.seek(0, os.SEEK_END)
        size = upload.tell()
        upload.seek(0)
        if size > MAX_AUDIO_BYTES:
            return jsonify({"ok": False, "error": "ファイルが大きすぎます。25MB以内にしてください。"}), 400
        ensure_dirs()
        _drop_server_audio(session)
        audio_name = f"{session_id}.{ext}"
        upload.save(TALK_AUDIO_DIR / audio_name)
        session["audio_file"] = audio_name
        save_talk_session(session)
        return jsonify({"ok": True, "session": _public_session(session)})

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
        if "transcript" in payload:
            session["transcript"] = str(payload.get("transcript") or "").strip()[:60000]
            if session["transcript"] and session.get("status") == "recorded":
                session["status"] = "transcribed"
        if "browser_transcript" in payload:
            session["browser_transcript"] = str(payload.get("browser_transcript") or "").strip()[:60000]
        if "questions" in payload:
            questions = _clean_edit_questions(payload.get("questions"))
            session["questions_json"] = questions
            session["question_count"] = len(questions)
            session["status"] = "ready" if questions else ("transcribed" if session.get("transcript") else "recorded")
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
