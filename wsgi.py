"""Gunicorn / Render 用 WSGI エントリポイント。"""
# gthread ワーカーでは gevent.monkey.patch_all() は不要（かつ有害）なので行わない。

from flask_app import create_app

application = create_app()

# debate の文字起こし用 OS スレッドプールをワーカー起動時に初期化。
# gthread では ThreadPoolExecutor、gevent+monkey.patch 時は gevent.threadpool。
try:
    from debate.transcription_jobs import _get_pool

    _get_pool()
except Exception:
    pass
