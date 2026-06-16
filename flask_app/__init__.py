import logging

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from flask_app.config import Config
from flask_app.extensions import cors

load_dotenv(Config.BASE_DIR / ".env")


def create_app(config_class=Config):
    """Flaskアプリケーションファクトリ"""
    app = Flask(
        __name__,
        template_folder=str(config_class.TEMPLATE_FOLDER),
        static_folder=str(config_class.STATIC_FOLDER),
    )
    app.config.from_object(config_class)
    config_class.init_app(app)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    cors.init_app(app)

    from flask_app.api import (
        admin_bp,
        gate_bp,
        grammar_bp,
        languages_bp,
        ocr_bp,
        practice_bp,
        statistics_bp,
        transcription_bp,
        tts_bp,
    )
    from flask_app.views import main_bp
    from news_app import create_news_blueprints

    app.register_blueprint(main_bp)

    news_bps = create_news_blueprints()
    app.register_blueprint(news_bps["main"], url_prefix="/news")
    app.register_blueprint(news_bps["admin"], url_prefix="/news/admin")
    app.register_blueprint(gate_bp, url_prefix="/api")
    app.register_blueprint(grammar_bp, url_prefix="/api")
    app.register_blueprint(ocr_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api")
    app.register_blueprint(transcription_bp, url_prefix="/api")
    app.register_blueprint(tts_bp, url_prefix="/api")
    app.register_blueprint(practice_bp, url_prefix="/api")
    app.register_blueprint(statistics_bp, url_prefix="/api")
    app.register_blueprint(languages_bp, url_prefix="/api")

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "API endpoint not found"}), 404
        return ("Not Found", 404)

    @app.errorhandler(500)
    def internal_error(_error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return ("Internal Server Error", 500)

    return app
