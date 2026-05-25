import logging

from flask import Blueprint, jsonify, request

from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

practice_bp = Blueprint("practice", __name__)
ai_service = AIService()


@practice_bp.route("/generate-practice-text", methods=["POST"])
def generate_practice_text():
    """練習用テキストを生成"""
    try:
        data = request.get_json(silent=True) or {}
        language_code = data.get("language", "ja-JP")
        difficulty = data.get("difficulty", "medium")
        topic = data.get("topic", "general")

        text = ai_service.generate_practice_text(language_code, difficulty, topic)

        return jsonify(
            {
                "text": text,
                "language": language_code,
                "difficulty": difficulty,
                "topic": topic,
            }
        )

    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        logger.error("Error in generate-practice-text endpoint: %s", exc)
        return jsonify({"error": str(exc)}), 500
