"""GTEC 管理画面 Blueprint。"""

import hmac
import os
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory

from gtec_app.admin_auth import (
    check_admin_password_attempt,
    clear_admin_session,
    configure_session_cookie,
    establish_admin_session,
    is_admin_session,
)
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


@gtec_admin_bp.record_once
def _configure_admin_session(state):
    configure_session_cookie(state.app)


@gtec_admin_bp.route("/gtec/admin/api/login", methods=["POST"])
def admin_login():
    payload = request.get_json(silent=True) or {}
    provided = payload.get("password")
    if provided is None:
        provided = payload.get("admin_password")
    denied = check_admin_password_attempt(
        provided,
        matches=lambda value: _password_ok({"admin_password": value}),
        configured=get_admin_password,
    )
    if denied:
        return denied
    establish_admin_session()
    return jsonify({"ok": True, "logged_in": True})


@gtec_admin_bp.route("/gtec/admin/api/logout", methods=["POST"])
def admin_logout():
    clear_admin_session()
    return jsonify({"ok": True, "logged_in": False})


@gtec_admin_bp.route("/gtec/admin/api/status", methods=["GET"])
def admin_status():
    if not get_admin_password():
        return jsonify({"ok": False, "logged_in": False, "error": _PASSWORD_UNSET}), 503
    return jsonify({"ok": True, "logged_in": is_admin_session()})

_PASSWORD_UNSET = "管理パスワードが設定されていません。"
_PASSWORD_WRONG = "管理パスワードが違います。"


def get_admin_password() -> str:
    per_app = (os.environ.get("GTEC_ADMIN_PASSWORD") or "").strip()
    if per_app:
        return per_app
    return (os.environ.get("ADMIN_PASSWORD") or "").strip()


PART_LABELS = {
    "a": "Part A：音読 (Reading Aloud)",
    "b": "Part B：やり取り (Interacting with Others)",
    "c": "Part C：ストーリー (Telling a Story)",
    "d": "Part D：意見表明 (Expressing Your Opinion)",
}


def _password_ok(payload: dict) -> bool:
    expected = get_admin_password()
    if not expected:
        return False
    return hmac.compare_digest(str(payload.get("admin_password") or ""), expected)


def _require_admin_password(payload: dict):
    return check_admin_password_attempt(
        payload.get("admin_password"),
        matches=lambda value: _password_ok({"admin_password": value}),
        configured=get_admin_password,
    )


@gtec_admin_bp.route("/gtec/admin/manifest.json")
def web_app_manifest():
    """管理画面用 PWA manifest（start_url / scope: /gtec/admin/）。"""
    response = send_from_directory(
        Path(current_app.static_folder) / "gtec" / "admin",
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@gtec_admin_bp.route("/gtec/admin", strict_slashes=False)
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
    denied = _require_admin_password(payload)
    if denied:
        return denied

    updates = {}
    for part in PART_DEFAULTS:
        enabled_key = f"part_{part}_prep_enabled"
        seconds_key = f"part_{part}_prep_seconds"
        problem_count_key = f"part_{part}_problem_count"
        selectable_key = f"part_{part}_selectable_problems"
        if enabled_key in payload:
            updates[enabled_key] = bool(payload.get(enabled_key))
        if seconds_key in payload:
            updates[seconds_key] = payload.get(seconds_key)
        if problem_count_key in payload:
            updates[problem_count_key] = payload.get(problem_count_key)
        if selectable_key in payload:
            updates[selectable_key] = payload.get(selectable_key)

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
    denied = _require_admin_password(payload)
    if denied:
        return denied

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
