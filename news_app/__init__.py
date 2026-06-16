def create_news_blueprints() -> dict:
    from news_app.routes.main import main_bp
    from news_app.routes.admin import admin_bp

    return {"main": main_bp, "admin": admin_bp}
