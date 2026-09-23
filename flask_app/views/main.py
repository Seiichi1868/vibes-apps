from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, send_from_directory, session

from flask_app.config import Config
from flask_app.services.ai_service import AIService
from flask_app.services.tts_service import TTSService

main_bp = Blueprint("main", __name__)


@main_bp.context_processor
def _inject_appearance():
    from flask_app.services.runtime_settings import appearance_context

    return appearance_context()


@main_bp.route("/")
def index():
    if "user_id" not in session:
        session["user_id"] = f"user_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return render_template("index.html")


@main_bp.route("/admin")
def admin_page():
    return render_template("admin.html")


@main_bp.route("/admin/manifest.json")
def admin_web_app_manifest():
    """管理画面用 PWA。start_url を /admin に固定し、学習者画面とは別アイコンで保存する。

    マニフェスト自体も scope（/admin）の内側で配信する。学習者用 manifest の
    start_url は / なので、管理画面がそれを参照するとホーム画面追加時に /admin が消える。
    """
    response = send_from_directory(
        Path(current_app.static_folder) / "admin",
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@main_bp.route("/static/audio/<path:filename>")
def serve_cached_audio(filename: str):
    # TTS cache lives in static/audio/*.mp3; committed SFX use subfolders (e.g. conjugate/).
    return send_from_directory(Config.AUDIO_CACHE_DIR, filename, mimetype="audio/mpeg")


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