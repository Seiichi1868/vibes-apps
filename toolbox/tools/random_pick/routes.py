from flask import jsonify, render_template, request

from toolbox.auth import current_user, login_required
from toolbox.routes import any_tool_required, tool_required
from toolbox.storage import delete_class, get_class, list_classes, new_id, now_iso, save_class


def _normalize_class(payload: dict, user_id: str, existing: dict | None = None) -> tuple[dict | None, str | None]:
    name = str(payload.get("name") or "").strip()
    if not name:
        return None, "クラス名を入力してください。"
    try:
        count = int(payload.get("student_count"))
    except (TypeError, ValueError):
        return None, "人数は1〜60の数字で入力してください。"
    if count < 1 or count > 60:
        return None, "人数は1〜60人です。"
    row = {
        "id": existing["id"] if existing else new_id(),
        "user_id": user_id,
        "name": name[:40],
        "student_count": count,
        "seat_layout_json": existing.get("seat_layout_json") if existing else None,
        "created_at": existing["created_at"] if existing else now_iso(),
    }
    return row, None


def register(bp):
    @bp.route("/random-pick")
    @login_required
    @tool_required("random_pick")
    def random_pick_page():
        return render_template(
            "toolbox/tools/random_pick.html",
            classes=list_classes(current_user()["id"]),
        )

    @bp.route("/api/classes")
    @login_required
    @any_tool_required("random_pick", "random_seats")
    def api_list_classes():
        return jsonify({"ok": True, "classes": list_classes(current_user()["id"])})

    @bp.route("/api/classes", methods=["POST"])
    @login_required
    @any_tool_required("random_pick", "random_seats")
    def api_create_class():
        row, error = _normalize_class(request.get_json(silent=True) or {}, current_user()["id"])
        if error:
            return jsonify({"ok": False, "error": error}), 400
        save_class(row)
        return jsonify({"ok": True, "class": row})

    @bp.route("/api/classes/<class_id>", methods=["PUT"])
    @login_required
    @any_tool_required("random_pick", "random_seats")
    def api_update_class(class_id):
        existing = get_class(class_id, current_user()["id"])
        if not existing:
            return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404
        row, error = _normalize_class(request.get_json(silent=True) or {}, current_user()["id"], existing)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        save_class(row)
        return jsonify({"ok": True, "class": row})

    @bp.route("/api/classes/<class_id>/duplicate", methods=["POST"])
    @login_required
    @any_tool_required("random_pick", "random_seats")
    def api_duplicate_class(class_id):
        existing = get_class(class_id, current_user()["id"])
        if not existing:
            return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404
        row = dict(existing)
        row["id"] = new_id()
        row["name"] = f"{existing['name']} のコピー"
        row["created_at"] = now_iso()
        save_class(row)
        return jsonify({"ok": True, "class": row})

    @bp.route("/api/classes/<class_id>", methods=["DELETE"])
    @login_required
    @any_tool_required("random_pick", "random_seats")
    def api_delete_class(class_id):
        if not delete_class(class_id, current_user()["id"]):
            return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404
        return jsonify({"ok": True})
