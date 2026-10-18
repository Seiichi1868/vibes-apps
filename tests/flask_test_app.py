"""unittest 間で Flask アプリを1つだけ作る。news の blueprint は2回登録できない。"""
from __future__ import annotations

import os

_APP = None


def get_test_app():
    global _APP
    if _APP is None:
        os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
        from flask_app import create_app

        _APP = create_app()
        _APP.testing = True
        _APP.config["SESSION_COOKIE_SECURE"] = False
    return _APP
