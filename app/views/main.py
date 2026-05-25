from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, render_template, send_from_directory, session

from app.config import Config
from app.services.ai_service import AIService
from app.services.tts_service import TTSService

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if "user_id" not in session:
        session["user_id"] = f"user_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return render_template("index.html")


@main_bp.route("/admin")
def admin_page():
    return render_template("admin.html")


@main_bp.route("/static/audio/<path:filename>")
def serve_cached_audio(filename: str):
    safe_name = Path(filename).name
    return send_from_directory(Config.AUDIO_CACHE_DIR, safe_name, mimetype="audio/mpeg")


@main_bp.route("/health", methods=["GET"])
def health_check():
    ai_service = AIService()
    tts_service = TTSService()

    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "openai": ai_service.client is not None,
                "text_to_speech": tts_service.client is not None,
            },
        }
    )


@main_bp.route("/api/evaluate", methods=["POST"])
def legacy_evaluate_endpoint():
    return (
        jsonify(
            {
                "error": "This app now runs fully in-browser with Web Speech API.",
                "message": "Please reload the page and use the browser-side recognition flow.",
            }
        ),
        410,
    )