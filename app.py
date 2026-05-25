"""Render 互換エントリポイント（``python app.py`` / ``gunicorn app:app``）。

Flask 本体は ``flask_app`` パッケージにあり、このファイル名 ``app`` との衝突を避ける。
本番推奨: ``gunicorn wsgi:application``
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from flask_app import create_app

app = create_app()

from routes.student import student_bp  # noqa: F401
from routes.admin import admin_bp  # noqa: F401

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(host="0.0.0.0", port=port, debug=debug)
