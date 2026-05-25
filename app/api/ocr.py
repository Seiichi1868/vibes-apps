import logging

from flask import Blueprint, jsonify, request

from app.config import Config
from app.services.ai_service import AIService
from app.services.gate_service import gate_access_allowed, gate_auth_error
from app.utils.language_utils import normalize_study_lang
from app.utils.validators import resolve_image_mime

logger = logging.getLogger(__name__)

ocr_bp = Blueprint("ocr", __name__)
ai_service = AIService()


@ocr_bp.route("/ocr", methods=["POST"])
def ocr():
    if not gate_access_allowed():
        return gate_auth_error()

    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "image is required"}), 400

    image_bytes = file.read()
    if not image_bytes:
        return jsonify({"error": "image is empty"}), 400
    if len(image_bytes) > Config.OCR_MAX_BYTES:
        return jsonify({"error": "image is too large (max 10MB)"}), 400

    mime = resolve_image_mime(file)
    if mime not in Config.OCR_ALLOWED_MIME:
        return jsonify({"error": "unsupported image type"}), 400

    lang = normalize_study_lang(request.form.get("lang") or request.args.get("lang") or "")

    try:
        return jsonify(ai_service.extract_text_from_image(image_bytes, mime, lang))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        logger.error("OCR failed: %s", exc)
        return jsonify({"error": f"OCR failed: {exc}"}), 502
