"""GTEC 管理画面 Blueprint。"""

import os

from flask import Blueprint, jsonify, render_template, request

from gtec_app.problems import load_problems, public_problems, save_problems
from gtec_app.settings import (
    BACKGROUND_PRESETS,
    DEFAULT_BACKGROUND_OPACITY,
    PART_DEFAULTS,
    _clamp_opacity,
    load_settings,
    resolve_background,
    update_settings,
)

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
    settings = load_settings()
    bg = resolve_background(settings.get("background_id"))
    return render_template(
        "gtec/admin.html",
        parts=PART_LABELS,
        defaults=PART_DEFAULTS,
        backgrounds=BACKGROUND_PRESETS,
        current_background=bg,
        background_opacity=settings.get("background_opacity", DEFAULT_BACKGROUND_OPACITY),
    )


@gtec_admin_bp.route("/gtec/admin/api/settings", methods=["GET", "POST"])
def admin_settings():
    if request.method == "GET":
        settings = load_settings()
        return jsonify({"ok": True, **settings, **resolve_background(settings.get("background_id"))})

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

    if "background_id" in payload:
        bg_id = str(payload.get("background_id") or "")
        if bg_id in BACKGROUND_PRESETS:
            updates["background_id"] = bg_id

    if "background_opacity" in payload:
        updates["background_opacity"] = _clamp_opacity(payload.get("background_opacity"))

    if not updates:
        settings = load_settings()
        return jsonify({"ok": True, **settings, **resolve_background(settings.get("background_id"))})

    saved = update_settings(**updates)
    return jsonify({"ok": True, **saved, **resolve_background(saved.get("background_id"))})


@gtec_admin_bp.route("/gtec/admin/api/problems", methods=["GET", "POST"])
def admin_problems():
    if request.method == "GET":
        return jsonify({"ok": True, **load_problems()})

    payload = request.get_json(silent=True) or {}
    if not _password_ok(payload):
        return jsonify({"ok": False, "error": "管理パスワードが違います。"}), 403

    incoming = {}
    if isinstance(payload.get("active"), dict):
        incoming["active"] = payload["active"]
    if isinstance(payload.get("sets"), dict):
        incoming["sets"] = payload["sets"]

    if not incoming:
        return jsonify({"ok": True, **load_problems()})

    current = load_problems()
    if "active" in incoming:
        current["active"].update(incoming["active"])
    if "sets" in incoming:
        from gtec_app.problems import PROBLEM_NUMS, PARTS, _normalize_part_set

        for part, part_sets in incoming["sets"].items():
            if part not in current["sets"] or not isinstance(part_sets, dict):
                continue
            for num, content in part_sets.items():
                try:
                    num_int = int(num)
                except (TypeError, ValueError):
                    continue
                if part in PARTS and num_int in PROBLEM_NUMS:
                    current["sets"][part][str(num_int)] = _normalize_part_set(
                        part, num_int, content if isinstance(content, dict) else None
                    )

    saved = save_problems(current)
    return jsonify({"ok": True, **saved})
