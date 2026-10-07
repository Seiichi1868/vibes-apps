"""1分スピーチの画面と API。全件を返す公開 API は置かない。"""
from __future__ import annotations

import json
import time

from flask import jsonify, render_template, request

from toolbox.auth import admin_panel_required, current_user, login_required, require_admin_reauth
from toolbox.routes import tool_required
from toolbox.storage import get_setting, update_app_settings
from toolbox.tools.minute_speech import classify, embed
from toolbox.tools.minute_speech.topics import (
    SEARCH_LIMIT,
    _is_japanese,
    add_original,
    admin_page_topics,
    approve_ai,
    draw_topic,
    hide_flagged,
    keyword_search,
    merged_topics,
    passes_filters,
    public_topic,
    stats,
    update_topic,
)
from toolbox.usage import UsageError, UsageLimitError, generate_json

_hits: dict[str, list[float]] = {}
KEYWORD_RPM = 30
AI_RPM = 10


def _user_id() -> str:
    user = current_user()
    return str(user.get("id")) if user else "guest"


def _bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("1", "true", "yes", "on")


def _ids(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item][:4000]


def _rate_ok(bucket: str, limit: int) -> bool:
    now = time.time()
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "local").split(",")[0].strip()
    key = f"{bucket}:{ip}"
    rows = [stamp for stamp in _hits.get(key, []) if now - stamp < 60]
    if len(rows) >= limit:
        _hits[key] = rows
        return False
    rows.append(now)
    _hits[key] = rows
    return True


def _filters(payload: dict) -> dict:
    level = payload.get("level_max", 2)
    try:
        level = int(level)
    except (TypeError, ValueError):
        level = 2
    return {
        "type_value": payload.get("type"),
        "level_max": level,
        "include_flagged": _bool(payload.get("include_flagged"), False),
        "include_unleveled": _bool(payload.get("include_unleveled"), True),
    }


def _translate(query: str, user_id: str) -> str:
    _raw, content = generate_json(
        messages=[
            {
                "role": "system",
                "content": '日本語の検索語を、英語のお題を探すための短い英語にする。JSONだけ。形式: {"english":"..."}',
            },
            {"role": "user", "content": query[:200]},
        ],
        user_id=user_id,
        tool_id="minute-speech",
        temperature=0,
        max_tokens=80,
    )
    data = json.loads(content)
    english = str(data.get("english") or "").strip()
    return english or query


def register(bp):
    @bp.route("/minute-speech")
    @login_required
    @tool_required("minute-speech")
    def minute_speech_page():
        return render_template("toolbox/tools/minute_speech.html")

    @bp.route("/api/minute-speech/draw", methods=["POST"])
    @login_required
    @tool_required("minute-speech")
    def minute_speech_draw():
        payload = request.get_json(silent=True) or {}
        filters = _filters(payload)
        result = draw_topic(exclude_ids=_ids(payload.get("exclude_ids")), **filters)
        return jsonify({"ok": True, **result})

    @bp.route("/api/minute-speech/stats")
    @login_required
    @tool_required("minute-speech")
    def minute_speech_stats():
        filters = _filters(request.args)
        return jsonify({"ok": True, **stats(**filters)})

    @bp.route("/api/minute-speech/search", methods=["POST"])
    @login_required
    @tool_required("minute-speech")
    def minute_speech_search():
        payload = request.get_json(silent=True) or {}
        mode = str(payload.get("mode") or "keyword")
        query = str(payload.get("q") or "").strip()
        if len(query) < 2:
            return jsonify({"ok": False, "error": "検索語は2文字以上にしてください。"}), 400
        filters = _filters(payload)
        limit = payload.get("limit", SEARCH_LIMIT)
        offset = payload.get("offset", 0)
        if mode == "ai":
            if not _rate_ok("minute-ai", AI_RPM):
                return jsonify({"ok": False, "error": "AI検索の回数が多いため、少し待ってからもう一度試してください。一致検索は使えます。"}), 429
            return _ai_search(query, payload, filters, limit, offset)
        if not _rate_ok("minute-keyword", KEYWORD_RPM):
            return jsonify({"ok": False, "error": "検索の回数が多いため、少し待ってからもう一度試してください。"}), 429
        found = keyword_search(
            query=query,
            used_ids=_ids(payload.get("used_ids")),
            exclude_used=_bool(payload.get("exclude_used"), False),
            hidden_ids=_ids(payload.get("hidden_ids")),
            themes=payload.get("themes") if isinstance(payload.get("themes"), list) else [],
            limit=limit,
            offset=offset,
            **filters,
        )
        if found.get("error"):
            return jsonify({"ok": False, "error": found["error"]}), 400
        return jsonify({"ok": True, "results": found["results"], "has_more": found["has_more"], "notice": found.get("notice") or ""})

    def _ai_search(query: str, payload: dict, filters: dict, limit, offset) -> tuple:
        status = embed.index_status()
        if not status.get("ready"):
            return jsonify({
                "ok": False,
                "error": "AI検索の準備ができていません。一致検索を使うか、管理画面でインデックスを作成してください。",
                "code": "index_missing",
            }), 409
        user_id = _user_id()
        search_query = query
        try:
            if embed.index_includes_ja() is False and _bool(get_setting("minute_speech_translate_query"), True):
                if _is_japanese(query):
                    search_query = _translate(query, user_id)
            vector = embed.query_vector(search_query, user_id)
        except UsageLimitError as exc:
            return jsonify({"ok": False, "error": exc.message + " 一致検索は使えます。"}), 429
        except (UsageError, json.JSONDecodeError) as exc:
            message = getattr(exc, "message", None) or "AI検索に失敗しました。一致検索を使ってください。"
            return jsonify({"ok": False, "error": message}), 502
        try:
            threshold = float(get_setting("minute_speech_sim_min") or 0.25)
        except (TypeError, ValueError):
            threshold = 0.25
        used = set(_ids(payload.get("used_ids")))
        hidden = set(_ids(payload.get("hidden_ids")))
        exclude_used = _bool(payload.get("exclude_used"), False)
        themes = {str(item) for item in (payload.get("themes") or []) if item} if isinstance(payload.get("themes"), list) else set()
        vectors = embed.indexed_vectors()
        by_id = {topic["id"]: topic for topic in merged_topics()}
        scored = []
        for topic_id, values in vectors.items():
            topic = by_id.get(topic_id)
            if not topic or topic_id in hidden:
                continue
            if exclude_used and topic_id in used:
                continue
            if not passes_filters(topic, **filters):
                continue
            if themes and not themes.issubset({str(item) for item in (topic.get("themes") or [])}):
                continue
            score = embed._cosine(vector, values)
            if score < threshold:
                continue
            scored.append((score, topic))
        scored.sort(key=lambda row: row[0], reverse=True)
        try:
            limit_n = max(1, min(int(limit or SEARCH_LIMIT), SEARCH_LIMIT))
            offset_n = max(0, min(int(offset or 0), 80 - limit_n))
        except (TypeError, ValueError):
            limit_n, offset_n = SEARCH_LIMIT, 0
        window = scored[:80]
        page = window[offset_n:offset_n + limit_n]
        if not page and offset_n == 0:
            notice = "近いお題が見つかりませんでした。言い方を変えてみてください。"
        else:
            notice = ""
        return jsonify({
            "ok": True,
            "results": [public_topic(topic, used=topic.get("id") in used) for _, topic in page],
            "has_more": offset_n + len(page) < len(window),
            "notice": notice,
        })

    @bp.route("/admin/minute-speech")
    @admin_panel_required
    def minute_speech_admin_page():
        return render_template(
            "toolbox/admin_minute_speech.html",
            embed_status=embed.index_status(),
            embed_estimate=embed.index_estimate(),
            classify_estimate=classify.estimate(),
            sim_min=get_setting("minute_speech_sim_min"),
            translate_query=_bool(get_setting("minute_speech_translate_query"), True),
        )

    @bp.route("/admin/api/minute-speech/topics")
    @admin_panel_required
    def minute_speech_admin_topics():
        return jsonify({"ok": True, **admin_page_topics(
            type_value=request.args.get("type"),
            status=request.args.get("status"),
            flagged=request.args.get("flagged"),
            level=request.args.get("level"),
            has_ja=request.args.get("has_ja"),
            q=request.args.get("q") or "",
            offset=request.args.get("offset") or 0,
        )})

    @bp.route("/admin/api/minute-speech/topics", methods=["POST"])
    @admin_panel_required
    def minute_speech_admin_add():
        guard = require_admin_reauth()
        if guard:
            return guard
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text") or "").strip()
        if len(text) < 8:
            return jsonify({"ok": False, "error": "本文は8文字以上にしてください。"}), 400
        level = payload.get("level")
        try:
            level = int(level) if level not in (None, "") else None
        except (TypeError, ValueError):
            level = None
        if level not in (None, 1, 2, 3):
            return jsonify({"ok": False, "error": "難易度は1〜3です。"}), 400
        topic = add_original(
            type_value=payload.get("type") or 1,
            text=text[:500],
            level=level,
            ja=str(payload.get("ja") or "")[:300],
        )
        return jsonify({"ok": True, "topic": public_topic(topic)})

    @bp.route("/admin/api/minute-speech/topics/<topic_id>", methods=["POST"])
    @admin_panel_required
    def minute_speech_admin_edit(topic_id):
        payload = request.get_json(silent=True) or {}
        fields = {}
        if "text" in payload:
            text = str(payload.get("text") or "").strip()
            if len(text) < 8:
                return jsonify({"ok": False, "error": "本文は8文字以上にしてください。"}), 400
            fields["text"] = text[:500]
        if "ja" in payload:
            fields["ja"] = str(payload.get("ja") or "").strip()[:300] or None
        if "level" in payload:
            level = payload.get("level")
            if level in ("", None):
                fields["level"] = None
            else:
                try:
                    level = int(level)
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": "難易度は1〜3です。"}), 400
                if level not in (1, 2, 3):
                    return jsonify({"ok": False, "error": "難易度は1〜3です。"}), 400
                fields["level"] = level
        if "status" in payload:
            status = str(payload.get("status") or "")
            if status not in ("active", "hidden"):
                return jsonify({"ok": False, "error": "状態が不正です。"}), 400
            fields["status"] = status
        if "themes" in payload and isinstance(payload.get("themes"), list):
            fields["themes"] = [str(item)[:24] for item in payload["themes"][:6] if str(item).strip()]
        topic = update_topic(topic_id, fields)
        if not topic:
            return jsonify({"ok": False, "error": "お題が見つかりません。"}), 404
        return jsonify({"ok": True, "topic": public_topic(topic)})

    @bp.route("/admin/api/minute-speech/hide-flagged", methods=["POST"])
    @admin_panel_required
    def minute_speech_hide_flagged():
        guard = require_admin_reauth()
        if guard:
            return guard
        return jsonify({"ok": True, "changed": hide_flagged()})

    @bp.route("/admin/api/minute-speech/approve-ai", methods=["POST"])
    @admin_panel_required
    def minute_speech_approve_ai():
        guard = require_admin_reauth()
        if guard:
            return guard
        return jsonify({"ok": True, "changed": approve_ai()})

    @bp.route("/admin/api/minute-speech/classify/estimate")
    @admin_panel_required
    def minute_speech_classify_estimate():
        return jsonify({"ok": True, **classify.estimate(), **classify.status()})

    @bp.route("/admin/api/minute-speech/classify/start", methods=["POST"])
    @admin_panel_required
    def minute_speech_classify_start():
        guard = require_admin_reauth()
        if guard:
            return guard
        try:
            return jsonify({"ok": True, **classify.start(_user_id())})
        except UsageError as exc:
            return jsonify({"ok": False, "error": exc.message}), 400

    @bp.route("/admin/api/minute-speech/embed/estimate")
    @admin_panel_required
    def minute_speech_embed_estimate():
        return jsonify({"ok": True, **embed.index_estimate(), **embed.index_status()})

    @bp.route("/admin/api/minute-speech/embed/start", methods=["POST"])
    @admin_panel_required
    def minute_speech_embed_start():
        guard = require_admin_reauth()
        if guard:
            return guard
        try:
            return jsonify({"ok": True, **embed.start_index(_user_id())})
        except UsageError as exc:
            return jsonify({"ok": False, "error": exc.message}), 400

    @bp.route("/admin/api/minute-speech/settings", methods=["POST"])
    @admin_panel_required
    def minute_speech_admin_settings():
        guard = require_admin_reauth()
        if guard:
            return guard
        payload = request.get_json(silent=True) or {}
        updates = {}
        if "minute_speech_sim_min" in payload:
            try:
                value = float(payload["minute_speech_sim_min"])
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "しきい値は数字です。"}), 400
            updates["minute_speech_sim_min"] = max(0.0, min(0.95, value))
        if "minute_speech_translate_query" in payload:
            updates["minute_speech_translate_query"] = _bool(payload.get("minute_speech_translate_query"), True)
        if updates:
            update_app_settings(updates)
        return jsonify({"ok": True})
