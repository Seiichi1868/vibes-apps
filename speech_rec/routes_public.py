"""生徒向け。ログインは無く、出題トークンが権限。"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from speech_rec.assignments import availability, find_by_token, public_view, records_dir
from speech_rec.config import MAX_UPLOAD_BYTES
from speech_rec.jobs import enqueue_eval, load_view, recover_stalled
from speech_rec.settings import get_settings
from speech_rec.store import write_json
from speech_rec.submissions import accept_audio, load_by_read_token, public_status
from speech_rec.usage import daily_limit_reached

AUDIO_PRESETS = {"default", "ns_on_agc_off", "ns_off"}


def register_public_routes(bp: Blueprint) -> None:
    @bp.errorhandler(RequestEntityTooLarge)
    def too_large(_exc):
        return jsonify({"ok": False, "error": "too_long"}), 413

    @bp.get("/<token>")
    def student_page(token):
        if token in {"admin", "teacher", "api"} or not find_by_token(token):
            return ("見つかりません", 404)
        mode = request.args.get("rec_audio") or "default"
        if mode not in AUDIO_PRESETS:
            mode = "default"
        return render_template("speech_rec/student.html", token=token, rec_audio=mode)

    @bp.get("/api/a/<token>")
    def assignment_info(token):
        row = find_by_token(token)
        if not row:
            return jsonify({"ok": False, "reason": "not_found"}), 404
        settings = get_settings()
        return jsonify(public_view(row, student_enabled=bool(settings.get("student_enabled")), id_fields=settings["id_fields"]))

    @bp.post("/api/a/<token>/submit")
    def submit(token):
        row = find_by_token(token)
        if not row:
            return jsonify({"ok": False, "error": "not_found"}), 404
        settings = get_settings()
        reason = availability(row, student_enabled=bool(settings.get("student_enabled")))
        if reason:
            return jsonify({"ok": False, "error": reason}), 403
        if daily_limit_reached():
            return jsonify({"ok": False, "error": "limit"}), 429
        recover_stalled()
        request.max_content_length = MAX_UPLOAD_BYTES
        upload = request.files.get("audio")
        if upload is None:
            return jsonify({"ok": False, "error": "audio"}), 400
        blob = upload.read(3 * 1024 * 1024 + 1)
        result = accept_audio(
            row,
            file_bytes=blob,
            mime=upload.mimetype or "",
            form=request.form,
            settings=settings,
        )
        if result.get("error"):
            code = 409 if result["error"] in {"full", "attempts"} else 400
            if result["error"] == "busy":
                code = 429
            return jsonify({"ok": False, "error": result["error"]}), code
        return jsonify({"ok": True, "read_token": result["read_token"], "attempt": result["attempt"]}), 202

    @bp.get("/api/r/<read_token>")
    def read_result(read_token):
        recover_stalled()
        record = load_by_read_token(read_token)
        if not record:
            return jsonify({"ok": False, "error": "not_found"}), 404
        detail = request.args.get("detail") == "1"
        return jsonify(public_status(record, detail=detail))

    @bp.post("/api/r/<read_token>/reevaluate")
    def reevaluate(read_token):
        if daily_limit_reached():
            return jsonify({"ok": False, "error": "limit"}), 429
        record = load_by_read_token(read_token)
        if not record:
            return jsonify({"ok": False, "error": "not_found"}), 404
        if record.get("error_code") != "eval_failed":
            return jsonify({"ok": False, "error": "retry"}), 400
        if int(record.get("eval_retries") or 0) >= 3:
            return jsonify({"ok": False, "error": "retry"}), 400
        view = load_view(str(record.get("id") or ""))
        if not view or not str(view.get("transcript") or "").strip():
            return jsonify({"ok": False, "error": "expired"}), 409
        record["eval_retries"] = int(record.get("eval_retries") or 0) + 1
        record["status"] = "processing"
        record["error_code"] = None
        write_json(records_dir(record["assignment_id"]) / f"{record['id']}.json", record)
        enqueue_eval(record["assignment_id"], record["id"])
        return jsonify({"ok": True, "read_token": read_token}), 202
