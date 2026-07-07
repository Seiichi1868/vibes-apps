"""GTEC 管理画面 Blueprint。"""

import os

from flask import Blueprint, jsonify, render_template, request

from gtec_app.settings import PART_DEFAULTS, load_settings, update_settings

gtec_admin_bp = Blueprint("gtec_admin", __name__)

ADMIN_PASSWORD = os.environ.get("GTEC_ADMIN_PASSWORD", "2479")

PART_LABELS = {
    "a": "Part A：音読 (Reading Aloud)",
    "b": "Part B：やり取り (Interacting with Others)",
    "c": "Part C：ストーリー (Telling a Story)",
    "d": "Part D：意見表明 (Expressing Your Opinion)",
}


def _password_ok(payload: dict) -> bool:
    return str(payload.get("admin_password") or "") == ADMIN_PASSWORD


@gtec_admin_bp.route("/gtec/admin")
def admin_page():
    return render_template("gtec/admin.html", parts=PART_LABELS, defaults=PART_DEFAULTS)


@gtec_admin_bp.route("/gtec/admin/api/settings", methods=["GET", "POST"])
def admin_settings():
    if request.method == "GET":
        return jsonify({"ok": True, **load_settings()})

    payload = request.get_json(silent=True) or {}
    if not _password_ok(payload):
        return jsonify({"ok": False, "error": "管理パスワードが違います。"}), 403

    updates = {}
    for part in PART_DEFAULTS:
        enabled_key = f"part_{part}_prep_enabled"
        seconds_key = f"part_{part}_prep_seconds"
        if enabled_key in payload:
            updates[enabled_key] = bool(payload.get(enabled_key))
        if seconds_key in payload:
            updates[seconds_key] = payload.get(seconds_key)

    if not updates:
        return jsonify({"ok": True, **load_settings()})

    saved = update_settings(**updates)
    return jsonify({"ok": True, **saved})
