"""1分スピーチ採点。他アプリは import しない。"""
from __future__ import annotations

from flask import Blueprint

from speech_rec.routes_admin import register_admin_routes


def create_blueprint() -> Blueprint:
    bp = Blueprint("speech_rec", __name__, url_prefix="/rec")
    register_admin_routes(bp)
    return bp
