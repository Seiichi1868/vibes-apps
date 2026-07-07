"""GTEC 管理画面 Blueprint。"""

import os

from flask import Blueprint, jsonify, render_template, request

from gtec_app.settings import load_settings, update_settings

gtec_admin_bp = Blueprint("gtec_admin", __name__)

ADMIN_PASSWORD = os.environ.get("GTEC_ADMIN_PASSWORD", "2479")


def _password_ok(payload: dict) -> bool:
    return str(payload.get("admin_password") or "") == ADMIN_PASSWORD


@gtec_admin_bp.route("/gtec/admin")
def admin_page():
    return render_template("gtec/admin.html")


@gtec_admin_bp.route("/gtec/admin/api/settings", methods=["GET", "POST"])
def admin_settings():
    if request.method == "GET":
        return jsonify({"ok": True, **load_settings()})

    payload = request.get_json(silent=True) or {}
    if not _password_ok(payload):
        return jsonify({"ok": False, "error": "管理パスワードが違います。"}), 403

    updates = {}
    if "part_a_prep_enabled" in payload:
        updates["part_a_prep_enabled"] = bool(payload["part_a_prep_enabled"])

    if not updates:
        return jsonify({"ok": True, **load_settings()})

    saved = update_settings(**updates)
    return jsonify({"ok": True, **saved})
