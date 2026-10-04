"""管理画面: ユーザー・ツール公開・利用状況・モデル選択。"""
from __future__ import annotations

import secrets
from datetime import date

from flask import g, jsonify, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from toolbox.auth import (
    admin_panel_ok,
    admin_panel_required,
    current_user,
    password_ok,
    require_admin_reauth,
    set_admin_panel_unlock,
    set_admin_reauth,
    verify_admin_panel_password,
    wants_json,
)
from toolbox.cli import USERNAME_RE
from toolbox.config import MIN_PASSWORD_LEN
from toolbox.model_catalog import resolved_catalog
from toolbox.pricing import estimate_generate_usd, estimate_transcribe_usd
from toolbox.registry import all_tools, get_tool
from toolbox.routes import main_bp
from toolbox.storage import (
    count_active_admins,
    delete_user,
    get_setting,
    get_user,
    list_users,
    load_app_settings,
    load_tool_settings,
    new_id,
    now_iso,
    public_user,
    save_user,
    set_tool_enabled,
    update_app_settings,
)
from toolbox.usage import measured_stats, usage_summary


def _cost_performance(score, est_cost: float | None):
    if not score or est_cost is None:
        return None
    if est_cost <= 0:
        return 5
    ratio = float(score) / est_cost
    return round(ratio, 2)


def _model_rows(kind: str) -> list[dict]:
    selected = get_setting("transcribe_model" if kind == "transcribe" else "generate_model")
    assume_sec = float(get_setting("assume_transcribe_sec") or 180)
    assume_in = int(get_setting("assume_input_tokens") or 1500)
    assume_out = int(get_setting("assume_output_tokens") or 800)
    rows = []
    for entry in resolved_catalog(kind):
        measured = measured_stats(entry["id"], kind)
        if kind == "transcribe":
            est = estimate_transcribe_usd(entry["id"], assume_sec) if entry["priced"] else None
            unit = f"${entry['price']['per_min']}/分" if entry["priced"] else "未設定"
        else:
            est = (
                estimate_generate_usd(entry["id"], assume_in, assume_out)
                if entry["priced"]
                else None
            )
            if entry["priced"]:
                unit = f"in ${entry['price']['input_per_1m']} / out ${entry['price']['output_per_1m']} /1M"
            else:
                unit = "未設定"
        rows.append(
            {
                **entry,
                "selected": entry["id"] == selected,
                "unit_price_label": unit,
                "est_cost_usd": None if est is None else round(est, 6),
                "measured": measured,
                "cost_performance": _cost_performance(entry.get("quality_score"), est),
            }
        )
    return rows


@main_bp.route("/admin/unlock", methods=["POST"])
def admin_unlock():
    password = request.form.get("password") or ""
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        password = payload.get("password") or password
    if not verify_admin_panel_password(password):
        if wants_json():
            return jsonify({"ok": False, "error": "管理パスワードが違います。"}), 403
        return render_template(
            "toolbox/admin_gate.html",
            error="管理パスワードが違います。",
        ), 403
    g.toolbox_session = set_admin_panel_unlock(g.toolbox_session)
    g.toolbox_session = set_admin_reauth(g.toolbox_session)
    if wants_json():
        return jsonify({"ok": True})
    return redirect(url_for("toolbox.admin_page"))


@main_bp.route("/admin/")
def admin_page():
    if not admin_panel_ok():
        return render_template("toolbox/admin_gate.html", error=None)
    users = [public_user(user) for user in list_users()]
    user_names = {user["id"]: user["username"] for user in users}
    summary = usage_summary()
    return render_template(
        "toolbox/admin.html",
        users=users,
        tools=all_tools(),
        tool_settings=load_tool_settings(),
        settings=load_app_settings(),
        usage=summary,
        user_names=user_names,
        transcribe_models=_model_rows("transcribe"),
        generate_models=_model_rows("generate"),
    )


@main_bp.route("/admin/api/reauth", methods=["POST"])
@admin_panel_required
def admin_reauth():
    payload = request.get_json(silent=True) or {}
    password = payload.get("password") or ""
    if not verify_admin_panel_password(password):
        return jsonify({"ok": False, "error": "管理パスワードが違います。"}), 403
    g.toolbox_session = set_admin_reauth(g.toolbox_session)
    return jsonify({"ok": True})


@main_bp.route("/admin/api/users", methods=["POST"])
@admin_panel_required
def admin_create_user():
    guard = require_admin_reauth()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    role = str(payload.get("role") or "teacher")
    if not USERNAME_RE.match(username):
        return jsonify({"ok": False, "error": "ユーザー名は英数字とアンダースコア、3〜32文字です。"}), 400
    if role not in ("admin", "teacher"):
        return jsonify({"ok": False, "error": "役割は admin または teacher です。"}), 400
    problem = password_ok(password)
    if problem:
        return jsonify({"ok": False, "error": problem}), 400
    if get_user(username=username):
        return jsonify({"ok": False, "error": "同じユーザー名があります。"}), 400
    user = {
        "id": new_id(),
        "username": username,
        "password_hash": generate_password_hash(password),
        "role": role,
        "is_active": True,
        "created_at": now_iso(),
        "last_login_at": None,
    }
    save_user(user)
    return jsonify({"ok": True, "user": public_user(user)})


def _mutate_user(user_id: str):
    user = get_user(user_id=user_id)
    if not user:
        return None, jsonify({"ok": False, "error": "ユーザーが見つかりません。"}), 404
    return user, None, None


@main_bp.route("/admin/api/users/<user_id>/active", methods=["POST"])
@admin_panel_required
def admin_set_active(user_id):
    guard = require_admin_reauth()
    if guard:
        return guard
    user, err, code = _mutate_user(user_id)
    if err:
        return err, code
    payload = request.get_json(silent=True) or {}
    active = bool(payload.get("is_active"))
    if not active and user.get("role") == "admin" and count_active_admins(exclude_id=user_id) < 1:
        return jsonify({"ok": False, "error": "最後の管理者は停止できません。"}), 400
    user["is_active"] = active
    save_user(user)
    return jsonify({"ok": True, "user": public_user(user)})


@main_bp.route("/admin/api/users/<user_id>/reset-password", methods=["POST"])
@admin_panel_required
def admin_reset_password(user_id):
    guard = require_admin_reauth()
    if guard:
        return guard
    user, err, code = _mutate_user(user_id)
    if err:
        return err, code
    password = secrets.token_urlsafe(10)
    if len(password) < MIN_PASSWORD_LEN:
        password = password + "x" * (MIN_PASSWORD_LEN - len(password))
    user["password_hash"] = generate_password_hash(password)
    save_user(user)
    return jsonify({"ok": True, "password": password, "user": public_user(user)})


@main_bp.route("/admin/api/users/<user_id>", methods=["DELETE"])
@admin_panel_required
def admin_delete_user(user_id):
    guard = require_admin_reauth()
    if guard:
        return guard
    user, err, code = _mutate_user(user_id)
    if err:
        return err, code
    me = current_user()
    if me and user.get("id") == me.get("id"):
        return jsonify({"ok": False, "error": "自分自身は削除できません。"}), 400
    if user.get("role") == "admin" and count_active_admins(exclude_id=user_id) < 1:
        return jsonify({"ok": False, "error": "最後の管理者は削除できません。"}), 400
    delete_user(user_id)
    return jsonify({"ok": True})


@main_bp.route("/admin/api/tools/<tool_id>/enabled", methods=["POST"])
@admin_panel_required
def admin_set_tool(tool_id):
    guard = require_admin_reauth()
    if guard:
        return guard
    if not get_tool(tool_id):
        return jsonify({"ok": False, "error": "ツールが見つかりません。"}), 404
    payload = request.get_json(silent=True) or {}
    enabled = bool(payload.get("enabled"))
    row = set_tool_enabled(tool_id, enabled)
    return jsonify({"ok": True, "tool_id": tool_id, **row})


@main_bp.route("/admin/api/settings", methods=["POST"])
@admin_panel_required
def admin_save_settings():
    guard = require_admin_reauth()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    updates = {}
    if "daily_limit_usd" in payload:
        try:
            updates["daily_limit_usd"] = max(0.0, float(payload["daily_limit_usd"]))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "1日の上限は数字で入力してください。"}), 400
    if "parallel_browser_stt" in payload:
        updates["parallel_browser_stt"] = bool(payload["parallel_browser_stt"])
    if "login_required_enabled" in payload:
        updates["login_required_enabled"] = bool(payload["login_required_enabled"])
    if "assume_transcribe_sec" in payload:
        try:
            updates["assume_transcribe_sec"] = max(10, int(payload["assume_transcribe_sec"]))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "想定秒数が不正です。"}), 400
    if "assume_input_tokens" in payload:
        try:
            updates["assume_input_tokens"] = max(1, int(payload["assume_input_tokens"]))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "想定入力トークンが不正です。"}), 400
    if "assume_output_tokens" in payload:
        try:
            updates["assume_output_tokens"] = max(1, int(payload["assume_output_tokens"]))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "想定出力トークンが不正です。"}), 400
    if updates:
        update_app_settings(updates)
    return jsonify({"ok": True, "settings": load_app_settings()})


@main_bp.route("/admin/api/models", methods=["POST"])
@admin_panel_required
def admin_select_model():
    guard = require_admin_reauth()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    kind = payload.get("kind")
    model_id = payload.get("model_id")
    if kind not in ("transcribe", "generate"):
        return jsonify({"ok": False, "error": "種別が不正です。"}), 400
    catalog = {row["id"]: row for row in resolved_catalog(kind)}
    entry = catalog.get(model_id)
    if not entry:
        return jsonify({"ok": False, "error": "モデルが見つかりません。"}), 404
    if not entry.get("priced"):
        return jsonify({"ok": False, "error": "価格未設定のモデルは選べません。"}), 400
    key = "transcribe_model" if kind == "transcribe" else "generate_model"
    update_app_settings({key: model_id})
    return jsonify({"ok": True, "settings": load_app_settings()})


@main_bp.route("/admin/api/models/<model_id>/meta", methods=["POST"])
@admin_panel_required
def admin_edit_model_meta(model_id):
    guard = require_admin_reauth()
    if guard:
        return guard
    catalog = {row["id"]: row for row in resolved_catalog()}
    if model_id not in catalog:
        return jsonify({"ok": False, "error": "モデルが見つかりません。"}), 404
    payload = request.get_json(silent=True) or {}
    overrides = dict(load_app_settings().get("model_overrides") or {})
    current = dict(overrides.get(model_id) or {})
    if "quality_score" in payload:
        try:
            score = int(payload["quality_score"])
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "性能スコアは1〜5の整数です。"}), 400
        if score < 1 or score > 5:
            return jsonify({"ok": False, "error": "性能スコアは1〜5です。"}), 400
        current["quality_score"] = score
    if "quality_note" in payload:
        current["quality_note"] = str(payload.get("quality_note") or "")
    if "speed_note" in payload:
        current["speed_note"] = str(payload.get("speed_note") or "")
    current["last_verified"] = date.today().isoformat()
    overrides[model_id] = current
    update_app_settings({"model_overrides": overrides})
    return jsonify({"ok": True, "overrides": current})
