"""HTML / JSON は毎回再検証し、JS / CSS は内容ハッシュで版を付ける。

アプリごとの static も、テンプレートの url_for 経由なら同じ規則になる。
音声・動画の Cache-Control はここでは上書きしない。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from flask import Flask, current_app, request, url_for as flask_url_for

VERSIONED_SUFFIXES = {".js", ".css", ".mjs"}
_HASH_CACHE: dict[tuple[str, int, int], str] = {}


def content_hash(path: Path) -> str:
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _HASH_CACHE.get(key)
    if cached:
        return cached
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:10]
    _HASH_CACHE[key] = digest
    return digest


def static_file_path(app: Flask, endpoint: str, filename: str) -> Path | None:
    if not filename or filename.startswith(("/", "\\")) or ".." in Path(filename).parts:
        return None
    if endpoint == "static":
        if not app.static_folder:
            return None
        root = Path(app.static_folder)
    elif endpoint.endswith(".static"):
        blueprint = app.blueprints.get(endpoint[: -len(".static")])
        if blueprint is None or not blueprint.static_folder:
            return None
        root = Path(blueprint.static_folder)
        if not root.is_absolute():
            root = Path(blueprint.root_path) / root
    else:
        return None
    try:
        full = (root / filename).resolve()
        full.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    if full.is_file():
        return full
    return None


def versioned_url_for(endpoint: str, **values):
    """JS/CSS の url_for に、ファイル内容のハッシュを v= として付ける。

    テンプレート側の手書き v= は上書きする。画像・音声はそのまま。
    """
    filename = values.get("filename")
    if isinstance(filename, str) and Path(filename).suffix.lower() in VERSIONED_SUFFIXES:
        path = static_file_path(current_app, endpoint, filename)
        if path is not None:
            values["v"] = content_hash(path)
    return flask_url_for(endpoint, **values)


def asset_version(filename: str) -> str:
    """メイン static フォルダのファイル内容ハッシュ。SW 登録 URL 用。"""
    path = static_file_path(current_app, "static", filename)
    if path is None:
        return "0"
    return content_hash(path)


def _is_content_hash(value: str) -> bool:
    return len(value) == 10 and all(char in "0123456789abcdef" for char in value)


def apply_cache_headers(response):
    if request.method not in {"GET", "HEAD"}:
        return response
    mimetype = (response.mimetype or "").lower()
    path = request.path.lower()
    if mimetype.startswith("audio/") or mimetype.startswith("video/"):
        return response
    if path.endswith((".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac", ".caf")):
        return response

    version = (request.args.get("v") or "").lower()
    is_code = path.endswith((".js", ".css", ".mjs")) or mimetype in {
        "text/javascript",
        "application/javascript",
        "application/x-javascript",
        "text/css",
    }
    if is_code and _is_content_hash(version):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
    if is_code or path.endswith("/sw.js"):
        response.headers["Cache-Control"] = "no-cache"
        return response
    if mimetype in {"text/html", "application/json", "application/manifest+json"}:
        response.headers["Cache-Control"] = "no-cache"
        return response
    return response


def install(app: Flask) -> None:
    @app.context_processor
    def _override_url_for():
        return {"url_for": versioned_url_for, "asset_version": asset_version}

    app.after_request(apply_cache_headers)
