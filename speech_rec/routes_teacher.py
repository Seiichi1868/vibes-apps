"""教員の出題作成。管理 Cookie 必須。"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, render_template, request

from speech_rec.assignments import (
    close_assignment,
    create_assignment,
    get_assignment,
    list_assignments,
    live_counts,
)
from speech_rec.auth import require_admin, require_admin_header
from speech_rec.qr import qr_data_uri, student_url
from speech_rec.settings import get_settings, save_settings


def register_teacher_routes(bp: Blueprint) -> None:
    @bp.get("/teacher")
    def teacher_page():
        if not g.speech_rec_admin:
            return render_template("speech_rec/teacher.html", authed=False)
        return render_template("speech_rec/teacher.html", authed=True, settings=get_settings())

    @bp.post("/api/t/assignments")
    @require_admin_header
    @require_admin
    def create():
        body = request.get_json(silent=True) or {}
        try:
            row = create_assignment(body)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        url = student_url(row["token"])
        return jsonify({
            "ok": True,
            "id": row["id"],
            "url": url,
            "qr": qr_data_uri(url),
            "expires_at": row["expires_at"],
            "label": row["label"],
        })

    @bp.get("/api/t/assignments")
    @require_admin_header
    @require_admin
    def index():
        rows = []
        for row in list_assignments():
            rows.append({
                "id": row["id"],
                "label": row.get("label") or "",
                "topic": (row.get("topic") or {}).get("text") or "",
                "status": row.get("status"),
                "expires_at": row.get("expires_at"),
                "url": student_url(row["token"]),
                "live": live_counts(row["id"]),
            })
        return jsonify({"ok": True, "assignments": rows})

    @bp.get("/api/t/assignments/<assignment_id>/live")
    @require_admin_header
    @require_admin
    def live(assignment_id):
        if not get_assignment(assignment_id):
            return jsonify({"ok": False, "error": "not_found"}), 404
        return jsonify({"ok": True, **live_counts(assignment_id)})

    @bp.post("/api/t/assignments/<assignment_id>/close")
    @require_admin_header
    @require_admin
    def close(assignment_id):
        row = close_assignment(assignment_id)
        if not row:
            return jsonify({"ok": False, "error": "not_found"}), 404
        return jsonify({"ok": True, "status": row["status"]})

    @bp.post("/api/t/settings")
    @require_admin_header
    @require_admin
    def update_flags():
        body = request.get_json(silent=True) or {}
        updates = {}
        if "student_enabled" in body:
            updates["student_enabled"] = bool(body["student_enabled"])
        if "id_fields" in body and isinstance(body["id_fields"], dict):
            allowed = {}
            if "enabled" in body["id_fields"]:
                allowed["enabled"] = bool(body["id_fields"]["enabled"])
            updates["id_fields"] = allowed
        saved = save_settings(updates)
        return jsonify({"ok": True, "student_enabled": saved["student_enabled"], "id_fields": saved["id_fields"]})
