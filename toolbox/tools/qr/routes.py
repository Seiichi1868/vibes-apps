from flask import jsonify, render_template, request

from toolbox.auth import login_required
from toolbox.routes import tool_required
from toolbox.tools.qr.make import normalize_url, png_data_uri


def register(bp):
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
        return jsonify({"ok": True, "link": link, "qr": qr_image})
