"""Toolbox 本体 Blueprint。ログイン・ランチャー・共通 API。"""
from __future__ import annotations

import time

from flask import Blueprint, g, jsonify, redirect, render_template, request, send_from_directory, url_for

from toolbox.auth import (
    admin_panel_ok,
    admin_reauth_ok,
    authenticate,
    check_csrf,
    current_csrf,
    current_user,
    ensure_guest_user,
    inject_auth_cookie,
    load_request_user,
    login_is_required,
    login_required,
    password_ok,
    public_current_user,
    set_admin_panel_unlock,
    set_admin_reauth,
    verify_admin_panel_password,
    verify_password,
    write_session_cookie,
)
from toolbox.config import PROJECT_ROOT
from toolbox.registry import SCENE_TABS, all_tools, get_tool
from toolbox.storage import (
    get_setting,
    is_tool_enabled,
    list_favorites,
    list_recent,
    load_tool_settings,
    record_recent,
    toggle_favorite,
)

main_bp = Blueprint("toolbox", __name__, url_prefix="/toolbox")

PUBLIC_ENDPOINTS = {
    "toolbox.login",
    "toolbox.admin_page",
    "toolbox.admin_unlock",
    "toolbox.web_app_manifest",
    "toolbox.admin_web_app_manifest",
    "toolbox.service_worker",
    "toolbox.offline",
}

_STATIC_DIR = PROJECT_ROOT / "static" / "toolbox"
_static_version_cache: dict = {"at": 0.0, "value": "0"}


def _static_version() -> str:
    """static/toolbox 配下で最も新しい更新時刻。ファイルを直せば URL の ?v= が自動で変わる。"""
    now = time.monotonic()
    if now - _static_version_cache["at"] < 2.0:
        return _static_version_cache["value"]
    newest = 0
    try:
        for path in _STATIC_DIR.rglob("*"):
            if path.suffix in (".js", ".css"):
                newest = max(newest, int(path.stat().st_mtime))
    except OSError:
        pass
    _static_version_cache["at"] = now
    _static_version_cache["value"] = format(newest, "x") if newest else "0"
    return _static_version_cache["value"]


def _admin_path() -> bool:
    path = request.path
    return path == "/toolbox/admin" or path.startswith("/toolbox/admin/")


def _canonical_host_redirect():
    """onrender.com で開いた Toolbox は正式ドメインへ送る。

    オリジンが違うと、インストール済み PWA と localStorage が別物になる。
    """
    if request.method not in ("GET", "HEAD"):
        return None
    host = (request.host or "").split(":")[0].lower()
    if not host.endswith(".onrender.com"):
        return None
    target = "https://vibes-lab.com" + request.full_path
    if target.endswith("?"):
        target = target[:-1]
    return redirect(target, code=302)


@main_bp.before_request
def _before():
    canonical = _canonical_host_redirect()
    if canonical is not None:
        return canonical
    load_request_user()
    if request.endpoint in PUBLIC_ENDPOINTS:
        return check_csrf()
    if request.endpoint == "toolbox.static":
        return None
    if _admin_path():
        return check_csrf()
    if not login_is_required():
        if not current_user():
            ensure_guest_user()
        return check_csrf()
    user = current_user()
    if not user or user.get("is_guest"):
        csrf_error = check_csrf()
        if csrf_error:
            return csrf_error
        if request.path.startswith("/toolbox/api/"):
            return jsonify({"ok": False, "error": "ログインしてください。"}), 401
        return redirect(url_for("toolbox.login", next=request.path))
    return check_csrf()


@main_bp.after_request
def _after(response):
    return inject_auth_cookie(response)


@main_bp.context_processor
def _inject():
    user = current_user()
    return {
        "csrf_token": current_csrf(),
        "current_user": public_current_user(),
        "is_admin": admin_panel_ok() or bool(user and user.get("role") == "admin"),
        "admin_panel_ok": admin_panel_ok(),
        "admin_reauth_ok": admin_reauth_ok(),
        "login_required_enabled": login_is_required(),
        "is_guest": bool(user and user.get("is_guest")),
        "toolbox_cache": _static_version(),
    }


def tool_required(tool_id: str):
    def deco(view):
        from functools import wraps

        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                if not login_is_required():
                    user = ensure_guest_user()
                else:
                    return redirect(url_for("toolbox.login", next=request.path))
            if not is_tool_enabled(tool_id):
                message = "このツールはいま公開されていません。管理画面でオンにしてください。"
                if request.path.startswith("/toolbox/api/"):
                    return jsonify({"ok": False, "error": message}), 403
                return render_template("toolbox/unavailable.html", message=message), 403
            record_recent(user["id"], tool_id)
            return view(*args, **kwargs)

        return wrapped

    return deco


def any_tool_required(*tool_ids: str):
    def deco(view):
        from functools import wraps

        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                if not login_is_required():
                    user = ensure_guest_user()
                else:
                    return redirect(url_for("toolbox.login", next=request.path))
            enabled_id = next((tid for tid in tool_ids if is_tool_enabled(tid)), None)
            if not enabled_id:
                message = "このツールはいま公開されていません。管理画面でオンにしてください。"
                if request.path.startswith("/toolbox/api/"):
                    return jsonify({"ok": False, "error": message}), 403
                return render_template("toolbox/unavailable.html", message=message), 403
            if not request.path.startswith("/toolbox/api/"):
                record_recent(user["id"], enabled_id)
            return view(*args, **kwargs)

        return wrapped

    return deco


def launcher_tools(user: dict) -> list[dict]:
    settings = load_tool_settings()
    favorites = set(list_favorites(user["id"]))
    is_admin = user.get("role") == "admin"
    rows = []
    for tool in all_tools():
        enabled = bool(settings.get(tool["id"], {}).get("enabled"))
        if not enabled and not is_admin:
            continue
        row = dict(tool)
        row["enabled"] = enabled
        row["favorite"] = tool["id"] in favorites
        rows.append(row)
    return rows


@main_bp.route("/sw.js")
def service_worker():
    """Service Worker。/toolbox/ を制御できるパスで配信する。"""
    response = send_from_directory(_STATIC_DIR, "sw.js", mimetype="application/javascript")
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Service-Worker-Allowed"] = "/toolbox/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@main_bp.route("/offline")
def offline():
    return render_template("toolbox/offline.html")


@main_bp.route("/manifest.json")
def web_app_manifest():
    """PWA manifest（scope: /toolbox/）。application/manifest+json で配信する。"""
    response = send_from_directory(
        _STATIC_DIR,
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@main_bp.route("/admin/manifest.json")
def admin_web_app_manifest():
    """管理画面用 PWA manifest（start_url / scope: /toolbox/admin/）。"""
    response = send_from_directory(
        _STATIC_DIR / "admin",
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if not login_is_required():
        if not current_user():
            ensure_guest_user()
        return redirect(url_for("toolbox.launcher"))
    if current_user() and not current_user().get("is_guest") and request.method == "GET":
        return redirect(url_for("toolbox.launcher"))
    error = None
    if request.method == "POST":
        user, error = authenticate(request.form.get("username") or "", request.form.get("password") or "")
        if user:
            g.toolbox_session = {
                "uid": user["id"],
                "csrf": current_csrf() or __import__("secrets").token_urlsafe(32),
            }
            nxt = request.form.get("next") or request.args.get("next") or url_for("toolbox.launcher")
            if not str(nxt).startswith("/toolbox"):
                nxt = url_for("toolbox.launcher")
            response = redirect(nxt)
            return write_session_cookie(response, g.toolbox_session)
    return render_template("toolbox/login.html", error=error, next=request.args.get("next") or "")


@main_bp.route("/logout", methods=["POST"])
def logout():
    g.toolbox_session = {"csrf": current_csrf()}
    response = redirect(url_for("toolbox.login"))
    return write_session_cookie(response, g.toolbox_session)


@main_bp.route("/")
@login_required
def launcher():
    user = current_user()
    tools = launcher_tools(user)
    recent_ids = [row["tool_id"] for row in list_recent(user["id"])]
    by_id = {tool["id"]: tool for tool in tools}
    recent = [by_id[tool_id] for tool_id in recent_ids if tool_id in by_id]
    favorites = [tool for tool in tools if tool.get("favorite")]
    return render_template(
        "toolbox/launcher.html",
        tools=tools,
        favorites=favorites,
        recent=recent,
        scene_tabs=SCENE_TABS,
    )


@main_bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    from toolbox.auth import hash_password
    from toolbox.storage import save_user

    user = current_user()
    if not user or user.get("is_guest"):
        return redirect(url_for("toolbox.launcher"))
    error = None
    ok_message = None
    if request.method == "POST":
        current = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""
        if not verify_password(user, current):
            error = "いまのパスワードが違います。"
        elif new_password != confirm:
            error = "新しいパスワードが一致しません。"
        else:
            problem = password_ok(new_password)
            if problem:
                error = problem
            else:
                user["password_hash"] = hash_password(new_password)
                save_user(user)
                ok_message = "パスワードを変更しました。"
    return render_template("toolbox/password.html", error=error, ok_message=ok_message)


@main_bp.route("/api/favorites/<tool_id>", methods=["POST"])
@login_required
def api_toggle_favorite(tool_id):
    if not get_tool(tool_id):
        return jsonify({"ok": False, "error": "ツールが見つかりません。"}), 404
    favored = toggle_favorite(current_user()["id"], tool_id)
    return jsonify({"ok": True, "favorite": favored})


@main_bp.route("/api/me")
@login_required
def api_me():
    return jsonify(
        {
            "ok": True,
            "user": public_current_user(),
            "parallel_browser_stt": bool(get_setting("parallel_browser_stt", True)),
        }
    )
