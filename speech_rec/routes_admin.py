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
from speech_rec.settings import get_settings
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

    @bp.get("/api/t/usage")
    @require_admin_header
    @require_admin
    def usage_api():
        data = summarize()
        data["today_jpy"] = round(data["today_usd"] * JPY_PER_USD, 2)
        data["month_jpy"] = round(data["month_usd"] * JPY_PER_USD, 2)
        return jsonify({"ok": True, **data})
