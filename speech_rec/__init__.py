"""1分スピーチ採点。他アプリは import しない。"""
from __future__ import annotations

from flask import Blueprint

from speech_rec.routes_admin import register_admin_routes
from speech_rec.routes_public import register_public_routes
from speech_rec.routes_teacher import register_teacher_routes


def create_blueprint() -> Blueprint:
    bp = Blueprint("speech_rec", __name__, url_prefix="/rec")
    register_admin_routes(bp)
    register_teacher_routes(bp)
    register_public_routes(bp)

    @bp.before_request
    def _start_jobs():
        from speech_rec.jobs import start

        start()

    return bp
