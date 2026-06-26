"""Gunicorn / Render 用 WSGI エントリポイント。"""
from gevent import monkey

monkey.patch_all()

from flask_app import create_app

application = create_app()
