from urllib.parse import quote

from flask import Response, jsonify, render_template, request, send_file

from toolbox.auth import current_user, login_required
from toolbox.config import QR_FILE_MAX_BYTES, QR_FILE_TTL_DAYS_DEFAULT
from toolbox.routes import tool_required
from toolbox.tools.qr.files import (
    QrFileError,
    body_path_for,
    delete_file,
    extend_file,
    get_by_token,
    list_files,
    purge_expired,
    save_upload,
)
from toolbox.tools.qr.store import delete_link, extend_link, list_links, save_link
from toolbox.tools.qr.make import normalize_url, png_data_uri

_UPLOAD_MARGIN = 1024 * 1024


def _device_id() -> str:
    raw = str(request.headers.get("X-Toolbox-Device") or "")
    return "".join(ch for ch in raw if ch.isalnum() or ch in "-_")[:64]


def _file_url(token: str) -> str:
    root = request.url_root
    if not root.endswith("/"):
        root += "/"
    return root + "toolbox/f/" + token


def _public_file(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row.get("original_name") or "",
        "title": row.get("title") or row.get("original_name") or "",
        "size": int(row.get("size") or 0),
        "created_at": row.get("created_at") or "",
        "expires_at": row.get("expires_at") or "",
        "url": _file_url(row["token"]),
    }


def _with_qr(row: dict) -> dict:
    item = _public_file(row)
    item["qr"] = png_data_uri(item["url"])
    return item


def _disposition(name: str) -> str:
    ascii_name = "".join(ch if 32 <= ord(ch) < 127 and ch not in '"\\' else "_" for ch in name) or "download"
    encoded = quote(name or "download", safe="")
    return f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def _missing_html() -> Response:
    body = (
        "<!doctype html><html lang=\"ja\"><meta charset=\"utf-8\">"
        "<title>ファイルが見つかりません</title>"
        "<body><p>ファイルが見つからないか、期限が切れています。</p></body></html>"
    )
    return Response(body, status=404, mimetype="text/html; charset=utf-8")


def register(bp):
    @bp.before_request
    def _qr_upload_size_limit():
        if request.endpoint != "toolbox.api_qr_files" or request.method != "POST":
            return None
        limit = QR_FILE_MAX_BYTES + _UPLOAD_MARGIN
        if request.content_length is not None and request.content_length > limit:
            return jsonify({"ok": False, "error": "ファイルは20MBまでです。"}), 413
        return None

    @bp.route("/qr")
    @login_required
    @tool_required("qr")
    def qr_page():
        return render_template("toolbox/tools/qr.html")

    @bp.route("/api/qr", methods=["GET", "POST"])
    @login_required
    @tool_required("qr")
    def api_qr():
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            raw = payload.get("url") or request.form.get("url") or ""
        else:
            raw = request.args.get("url") or ""
        link, error = normalize_url(raw)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        try:
            qr_image = png_data_uri(link)
        except Exception as exc:
            return jsonify({"ok": False, "error": f"QRの生成に失敗しました: {exc}"}), 500
        if request.method == "POST" and (request.get_json(silent=True) or {}).get("save"):
            user = current_user()
            payload = request.get_json(silent=True) or {}
            try:
                save_link(
                    user_id=user["id"],
                    device_id=_device_id(),
                    title=payload.get("title") or "",
                    url=link,
                    ttl_days=payload.get("days") or QR_FILE_TTL_DAYS_DEFAULT,
                )
            except QrFileError as exc:
                return jsonify({"ok": False, "error": exc.message}), exc.status
        return jsonify({"ok": True, "link": link, "qr": qr_image})

    def _archive_rows():
        user = current_user()
        device = _device_id()
        purge_expired()
        items = []
        for row in list_links(user["id"], device):
            url = row.get("url") or ""
            items.append({
                "kind": "link",
                "id": row.get("id") or "",
                "title": row.get("title") or "",
                "text": url,
                "created_at": row.get("created_at") or "",
                "expires_at": row.get("expires_at") or "",
                "qr": png_data_uri(url),
            })
        for row in list_files(user["id"], device):
            item = _with_qr(row)
            items.append({
                "kind": "file",
                "id": item["id"],
                "title": item.get("title") or item.get("name") or "",
                "text": item["url"],
                "created_at": item.get("created_at") or "",
                "expires_at": item.get("expires_at") or "",
                "qr": item["qr"],
            })
        items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return items

    @bp.route("/api/qr/archive", methods=["GET"])
    @login_required
    @tool_required("qr")
    def api_qr_archive():
        try:
            items = _archive_rows()
        except Exception as exc:
            return jsonify({"ok": False, "error": f"一覧の取得に失敗しました: {exc}"}), 500
        return jsonify({"ok": True, "items": items})

    @bp.route("/api/qr/links/<item_id>/extend", methods=["POST"])
    @login_required
    @tool_required("qr")
    def api_qr_link_extend(item_id):
        user = current_user()
        payload = request.get_json(silent=True) or {}
        try:
            extend_link(item_id, user["id"], _device_id(), payload.get("days") or QR_FILE_TTL_DAYS_DEFAULT)
        except QrFileError as exc:
            return jsonify({"ok": False, "error": exc.message}), exc.status
        return jsonify({"ok": True})

    @bp.route("/api/qr/links/<item_id>/delete", methods=["POST"])
    @login_required
    @tool_required("qr")
    def api_qr_link_delete(item_id):
        user = current_user()
        if not delete_link(item_id, user["id"], _device_id()):
            return jsonify({"ok": False, "error": "このQRは見つかりません。"}), 404
        return jsonify({"ok": True})

    @bp.route("/api/qr/files/<file_id>/extend", methods=["POST"])
    @login_required
    @tool_required("qr")
    def api_qr_file_extend(file_id):
        user = current_user()
        payload = request.get_json(silent=True) or {}
        try:
            extend_file(file_id, user["id"], _device_id(), payload.get("days") or QR_FILE_TTL_DAYS_DEFAULT)
        except QrFileError as exc:
            return jsonify({"ok": False, "error": exc.message}), exc.status
        return jsonify({"ok": True})

    @bp.route("/api/qr/files", methods=["GET", "POST"])
    @login_required
    @tool_required("qr")
    def api_qr_files():
        user = current_user()
        if request.method == "GET":
            purge_expired()
            rows = list_files(user["id"], _device_id())
            try:
                files = [_with_qr(row) for row in rows]
            except Exception as exc:
                return jsonify({"ok": False, "error": f"QRの生成に失敗しました: {exc}"}), 500
            return jsonify({"ok": True, "files": files})

        purge_expired()
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify({"ok": False, "error": "ファイルを選んでください。"}), 400
        data = upload.read(QR_FILE_MAX_BYTES + 1)
        ttl = request.form.get("ttl_days") or QR_FILE_TTL_DAYS_DEFAULT
        try:
            row = save_upload(
                user_id=user["id"],
                device_id=_device_id(),
                original_name=upload.filename,
                data=data,
                ttl_days=ttl,
                title=request.form.get("title") or "",
            )
            item = _public_file(row)
            qr_image = png_data_uri(item["url"])
        except QrFileError as exc:
            return jsonify({"ok": False, "error": exc.message}), exc.status
        except Exception as exc:
            return jsonify({"ok": False, "error": f"アップロードに失敗しました: {exc}"}), 500
        return jsonify({"ok": True, "file": item, "qr": qr_image})

    @bp.route("/api/qr/files/<file_id>", methods=["DELETE"])
    @login_required
    @tool_required("qr")
    def api_qr_file_delete(file_id):
        user = current_user()
        if not delete_file(file_id, user["id"], _device_id()):
            return jsonify({"ok": False, "error": "ファイルが見つかりません。"}), 404
        return jsonify({"ok": True})

    @bp.route("/f/<token>")
    def qr_public_file(token):
        row = get_by_token(token)
        path = body_path_for(row) if row else None
        if not row or path is None:
            return _missing_html()
        response = send_file(
            path,
            conditional=True,
            mimetype=row.get("mime") or "application/octet-stream",
            as_attachment=False,
            download_name=row.get("original_name") or "download",
            max_age=300,
        )
        response.headers["Content-Disposition"] = _disposition(row.get("original_name") or "download")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "private, max-age=300"
        return response
