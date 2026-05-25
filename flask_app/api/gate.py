from flask import Blueprint, jsonify, request

from flask_app.services.gate_service import (
    daily_class_code,
    gate_access_allowed,
    gate_status_payload,
    gate_token_for_today,
    is_gate_lock_enabled,
)

gate_bp = Blueprint("gate", __name__)


@gate_bp.route("/gate/status", methods=["GET"])
def gate_status():
    return jsonify(gate_status_payload())


@gate_bp.route("/gate/verify", methods=["POST"])
def gate_verify():
    if not is_gate_lock_enabled():
        return jsonify(
            {
                "ok": True,
                "token": gate_token_for_today(),
                "lock_enabled": False,
                "bypass": True,
            }
        )

    payload = request.get_json(silent=True) or {}
    code = str(payload.get("code", "")).strip()
    if code == daily_class_code():
        return jsonify({"ok": True, "token": gate_token_for_today(), "lock_enabled": True})
    return jsonify({"ok": False, "error": "invalid code"}), 403


@gate_bp.route("/gate/today", methods=["GET"])
def gate_today():
    return jsonify({"code": daily_class_code(), "lock_enabled": is_gate_lock_enabled()})
