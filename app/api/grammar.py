import json
import logging

from flask import Blueprint, jsonify, request

from app.services.ai_service import AIService
from app.services.gate_service import gate_access_allowed, gate_auth_error

logger = logging.getLogger(__name__)

grammar_bp = Blueprint("grammar", __name__)
ai_service = AIService()


@grammar_bp.route("/check-grammar", methods=["POST"])
def check_grammar():
    if not gate_access_allowed():
        return gate_auth_error()

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    lang_raw = payload.get("lang") or payload.get("lang_id") or payload.get("language") or ""
    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        return jsonify(ai_service.check_grammar(text, lang_raw))
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON from grammar model"}), 502
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        logger.error("Grammar check failed: %s", exc)
        return jsonify({"error": f"Grammar check failed: {exc}"}), 502
