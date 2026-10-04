"""Toolbox 本体 Blueprint。ログイン・ランチャー・共通 API。"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, redirect, render_template, request, url_for

from toolbox.auth import (
    admin_reauth_ok,
    authenticate,
    check_csrf,
    current_csrf,
    current_user,
    inject_auth_cookie,
    load_request_user,
    login_required,
    password_ok,
    public_current_user,
    set_admin_reauth,
    verify_password,
    write_session_cookie,
)
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

PUBLIC_ENDPOINTS = {"toolbox.login"}


@main_bp.before_request
def _before():
    load_request_user()
    if request.endpoint in PUBLIC_ENDPOINTS:
        csrf_error = check_csrf()
        return csrf_error
    if request.endpoint == "toolbox.static":
        return None
    if not current_user():
        csrf_error = check_csrf()
        if csrf_error:
            return csrf_error
        if request.path.startswith("/toolbox/api/") or request.path.startswith("/toolbox/admin/api/"):
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
        "is_admin": bool(user and user.get("role") == "admin"),
        "admin_reauth_ok": admin_reauth_ok(),
        "toolbox_cache": "20261004b",
    }


def tool_required(tool_id: str):
    def deco(view):
        from functools import wraps

        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
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


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user() and request.method == "GET":
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

    error = None
    ok_message = None
    if request.method == "POST":
        user = current_user()
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
