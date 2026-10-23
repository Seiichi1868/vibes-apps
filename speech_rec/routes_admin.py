"""PR1: 管理画面のログインと費用の表示だけ。生徒向けの入口はまだ無い。"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, render_template, request

from speech_rec.auth import (
    attach_admin_cookie,
    clear_admin_cookie,
    password_ok,
    read_admin,
    require_admin,
    require_admin_header,
)
from speech_rec.config import admin_password
from speech_rec.pricing import EVAL_MODELS, JPY_PER_USD
from speech_rec.results import assignment_choices, csv_text, delete_assignment_records, delete_record, list_results, recalc
from speech_rec.settings import get_settings, save_settings
from speech_rec.usage import summarize


def register_admin_routes(bp: Blueprint) -> None:
    @bp.before_request
    def _load_admin():
        g.speech_rec_admin = read_admin()

    @bp.get("/admin")
    def admin_page():
        if not admin_password():
            return render_template("speech_rec/admin.html", ready=False, authed=False, summary=None, settings=None), 503
        if not g.speech_rec_admin:
            return render_template("speech_rec/admin.html", ready=True, authed=False, summary=None, settings=None)
        summary = summarize()
        return render_template(
            "speech_rec/admin.html",
            ready=True,
            authed=True,
            summary=summary,
            settings=get_settings(),
            models=sorted(EVAL_MODELS),
            jpy_per_usd=JPY_PER_USD,
        )

    @bp.get("/admin/results")
    def results_page():
        if not g.speech_rec_admin:
            return render_template("speech_rec/admin.html", ready=True, authed=False, summary=None, settings=None)
        return render_template("speech_rec/results.html", assignments=assignment_choices())

    @bp.get("/api/t/results")
    @require_admin_header
    @require_admin
    def results_api():
        assignment_id = str(request.args.get("assignment_id") or "")
        return jsonify({"ok": True, **list_results(assignment_id)})

    @bp.get("/api/t/results.csv")
    @require_admin
    def results_csv():
        assignment_id = str(request.args.get("assignment_id") or "")
        body = csv_text(assignment_id)
        return ( "\ufeff" + body, 200, {"Content-Type": "text/csv; charset=utf-8", "Content-Disposition": "attachment; filename=results.csv"} )

    @bp.post("/api/t/results/recalc")
    @require_admin_header
    @require_admin
    def results_recalc():
        body = request.get_json(silent=True) or {}
        return jsonify({"ok": True, "updated": recalc(str(body.get("assignment_id") or ""))})

    @bp.post("/api/t/results/delete")
    @require_admin_header
    @require_admin
    def results_delete():
        body = request.get_json(silent=True) or {}
        assignment_id = str(body.get("assignment_id") or "")
        if body.get("all"):
            return jsonify({"ok": True, "deleted": delete_assignment_records(assignment_id)})
        if not delete_record(assignment_id, str(body.get("record_id") or "")):
            return jsonify({"ok": False, "error": "not_found"}), 404
        return jsonify({"ok": True})

    @bp.post("/admin/unlock")
    @require_admin_header
    def unlock():
        if not admin_password():
            return jsonify({"ok": False, "error": "unconfigured"}), 503
        body = request.get_json(silent=True) or {}
        if not password_ok(str(body.get("password") or "")):
            return jsonify({"ok": False, "error": "password"}), 401
        response = jsonify({"ok": True})
        return attach_admin_cookie(response)

    @bp.post("/admin/lock")
    @require_admin_header
    def lock():
        response = jsonify({"ok": True})
        return clear_admin_cookie(response)

    @bp.post("/admin/gaps")
    @require_admin_header
    @require_admin
    def save_gaps():
        body = request.get_json(silent=True) or {}
        updates = {}
        for key in ("sentence_gap_min", "clause_gap_min", "mid_gap_min", "unknown_gap_min"):
            try:
                updates[key] = round(float(body.get(key)), 2)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": key}), 400
        saved = save_settings(updates)
        return jsonify({"ok": True, **{key: saved[key] for key in updates}})

    @bp.get("/api/t/usage")
    @require_admin_header
    @require_admin
    def usage_api():
        data = summarize()
        data["today_jpy"] = round(data["today_usd"] * JPY_PER_USD, 2)
        data["month_jpy"] = round(data["month_usd"] * JPY_PER_USD, 2)
        return jsonify({"ok": True, **data})
