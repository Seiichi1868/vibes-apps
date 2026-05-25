"""Render 互換エントリポイント。

``python app.py`` や旧デプロイ設定から起動された場合に、
``routes`` パッケージと ``app`` パッケージ（Flask 本体）の両方を解決する。
本番の Gunicorn 推奨コマンドは ``gunicorn wsgi:application``。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from app import create_app

app = create_app()

# 旧 app.py が期待する import（Blueprint は create_app 内で登録済み）
from routes.student import student_bp  # noqa: F401
from routes.admin import admin_bp  # noqa: F401

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(host="0.0.0.0", port=port, debug=debug)
