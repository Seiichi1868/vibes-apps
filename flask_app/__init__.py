import logging

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory

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

    @app.route("/static/manifest.json")
    def web_app_manifest():
        """PWA manifest を application/manifest+json で配信する。

        Flask の static ハンドラは .json を application/json にするため、
        専用ルートで MIME を明示する。start_url / scope は / （学習者画面）。
        管理画面は /admin/manifest.json（start_url: /admin）を別にリンクする。
        Conjugate 等の他アプリも各ページで別 manifest をリンクしている。
        """
        response = send_from_directory(
            app.static_folder,
            "manifest.json",
            mimetype="application/manifest+json",
        )
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    from flask_app.services.runtime_settings import load_and_apply_runtime_settings

    load_and_apply_runtime_settings()

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
    from flask_app.views.public import public_bp
    from news_app import create_news_blueprints
    from gtec_app import gtec_admin_bp, gtec_bp
    from debate import debate_admin_bp, debate_bp
    from level_check import create_level_check_blueprints
    from conjugate import create_conjugate_blueprints
    from trigger import create_trigger_blueprints

    app.register_blueprint(main_bp)
    app.register_blueprint(public_bp, url_prefix="/public")
    app.register_blueprint(gtec_bp)
    app.register_blueprint(gtec_admin_bp)
    app.register_blueprint(debate_bp)
    app.register_blueprint(debate_admin_bp)

    news_bps = create_news_blueprints()
    app.register_blueprint(news_bps["main"], url_prefix="/news")
    app.register_blueprint(news_bps["admin"], url_prefix="/news/admin")

    level_check_bps = create_level_check_blueprints()
    app.register_blueprint(level_check_bps["main"])
    app.register_blueprint(level_check_bps["admin"])

    conjugate_bps = create_conjugate_blueprints()
    app.register_blueprint(conjugate_bps["main"])
    app.register_blueprint(conjugate_bps["admin"])

    trigger_bps = create_trigger_blueprints()
    app.register_blueprint(trigger_bps["main"])
    app.register_blueprint(trigger_bps["admin"])
    app.register_blueprint(gate_bp, url_prefix="/api")
    app.register_blueprint(grammar_bp, url_prefix="/api")
    app.register_blueprint(ocr_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api")
    app.register_blueprint(transcription_bp, url_prefix="/api")
    app.register_blueprint(tts_bp, url_prefix="/api")
    app.register_blueprint(practice_bp, url_prefix="/api")
    app.register_blueprint(statistics_bp, url_prefix="/api")
    app.register_blueprint(languages_bp, url_prefix="/api")

    @app.before_request
    def _public_kill_switch():
        """/public/ 配下のみを対象にした Kill-Switch。

        既存の学校用パス（``/``, ``/admin``, ``/api/...`` など）は
        ``request.path`` が ``/public`` で始まらないため、この判定には
        一切かからない。
        """
        path = request.path
        if path != "/public" and not path.startswith("/public/"):
            return None

        from flask_app.services.status_service import is_public_enabled

        if is_public_enabled():
            return None

        message = "The service is temporarily unavailable due to high traffic. Please try again later."
        wants_json = path.startswith("/public/api/") or (
            request.accept_mimetypes["application/json"]
            >= request.accept_mimetypes["text/html"]
            and request.accept_mimetypes["application/json"] > 0
        )
        if wants_json:
            return jsonify({"ok": False, "error": "public_service_disabled", "message": message}), 503
        return render_template("public_maintenance.html"), 503

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(
            {
                "ok": False,
                "error": "ファイルが大きすぎます。ボイスメモか、より短い動画にしてください。",
            }
        ), 413

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
