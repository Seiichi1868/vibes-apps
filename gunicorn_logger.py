"""Gunicorn のアクセスログから、成功した Render ヘルスチェックを外す。

Render は環境変数 ``GUNICORN_CMD_ARGS`` で ``--access-logfile -`` を渡す。
そのため ``GET /health``（User-Agent ``Render/1.0``、約5秒間隔）が
サービスログを埋め、デプロイログやエラーが流れ去る。
2xx / 3xx の ``/health`` だけ出さない。失敗は残す。
"""

from gunicorn.glogging import Logger


def status_code(status) -> str:
    if status is None:
        return ""
    if isinstance(status, bytes):
        status = status.decode("latin-1", "replace")
    return str(status).strip().split(None, 1)[0]


def should_skip_health_access(path, status) -> bool:
    normalized = (path or "").rstrip("/") or "/"
    if normalized != "/health":
        return False
    code = status_code(status)
    return len(code) == 3 and code[0] in "23" and code.isdigit()


class QuietHealthLogger(Logger):
    def access(self, resp, req, environ, request_time):
        path = ""
        if environ:
            path = environ.get("PATH_INFO") or ""
        status = getattr(resp, "status", None)
        if should_skip_health_access(path, status):
            return
        super().access(resp, req, environ, request_time)
