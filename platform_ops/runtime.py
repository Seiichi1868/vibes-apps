"""稼働状態の永続化とリクエスト判定。"""
from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from pathlib import Path

from platform_ops.registry import PLATFORM_APPS, PlatformApp, get_app

MAINTENANCE_MESSAGE = (
    "ただいま、メンテナンス中のためサイトにはアクセスできません。しばらくお待ちください。"
)

_GLOBAL_EXEMPT_PREFIXES = ("/static", "/health")
_lock = threading.Lock()


def _data_file() -> Path:
    root = Path(__file__).resolve().parent.parent
    data_root = Path(
        os.environ.get("PLATFORM_OPS_DATA_DIR", str(root / "data"))
    ).expanduser()
    data_root.mkdir(parents=True, exist_ok=True)
    return data_root / "platform_apps.json"


def _read_state() -> dict:
    path = _data_file()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    operational = raw.get("operational")
    return operational if isinstance(operational, dict) else {}


def _write_state(operational: dict) -> dict:
    path = _data_file()
    payload = {"operational": operational}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def is_app_operational(app_id: str) -> bool:
    state = _read_state()
    value = state.get(app_id)
    if value is None:
        return True
    return bool(value)


def set_app_operational(app_id: str, operational: bool) -> dict:
    if not get_app(app_id):
        raise KeyError(app_id)
    with _lock:
        state = _read_state()
        state[app_id] = bool(operational)
        _write_state(state)
        return {"id": app_id, "operational": bool(operational)}


def list_apps_with_status() -> list[dict]:
    state = _read_state()
    rows = []
    for app in PLATFORM_APPS:
        rows.append(
            {
                "id": app.id,
                "name": app.name,
                "description": app.description,
                "operational": bool(state.get(app.id, True)),
            }
        )
    return rows


def _path_matches_prefix(path: str, prefix: str) -> bool:
    if prefix.endswith("/"):
        return path.startswith(prefix)
    return path == prefix or path.startswith(prefix + "/")


def _app_for_path(path: str) -> PlatformApp | None:
    best: PlatformApp | None = None
    best_score = -1
    for app in PLATFORM_APPS:
        for exact in app.exact_paths:
            if path == exact:
                score = len(exact) + 1000
                if score > best_score:
                    best = app
                    best_score = score
        for prefix in app.prefixes:
            if _path_matches_prefix(path, prefix):
                score = len(prefix)
                if score > best_score:
                    best = app
                    best_score = score
    return best


def _is_bypass(path: str, app: PlatformApp) -> bool:
    for prefix in app.admin_bypass_prefixes:
        if _path_matches_prefix(path, prefix):
            return True
    return False


def is_path_operational(path: str) -> bool:
    for prefix in _GLOBAL_EXEMPT_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    app = _app_for_path(path)
    if not app:
        return True
    if not is_app_operational(app.id):
        if _is_bypass(path, app):
            return True
        return False
    return True


def maintenance_response(path: str, accept_mimetypes) -> tuple[object, int] | None:
    """Flask の before_request 用。ブロック時は (response, status)、通過時は None。"""
    if is_path_operational(path):
        return None
    wants_json = "/api/" in path or path.endswith("/api") or (
        accept_mimetypes["application/json"] >= accept_mimetypes["text/html"]
        and accept_mimetypes["application/json"] > 0
    )
    if wants_json:
        from flask import jsonify

        return (
            jsonify(
                {
                    "ok": False,
                    "error": "maintenance",
                    "message": MAINTENANCE_MESSAGE,
                }
            ),
            503,
        )
    from flask import render_template

    return render_template("platform_maintenance.html", message=MAINTENANCE_MESSAGE), 503
