"""Vibe Speak Trigger: 完全独立の Flask ブループリントパッケージ。

news_app / flask_app / level_check / conjugate 等、他アプリとのコード上の
依存関係は一切持たない（import しない）。配色は吹き出しアイコン
（ピンク〜パープル〜ブルー〜ティール）に合わせ、CSS はこのパッケージ内に置く。
"""


def create_trigger_blueprints() -> dict:
    from trigger.routes import main_bp
    from trigger.admin.routes import admin_bp

    return {"main": main_bp, "admin": admin_bp}
