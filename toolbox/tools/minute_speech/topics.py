"""1分スピーチのお題。シードは読み取り専用、編集は data/toolbox の上書き。"""
from __future__ import annotations

import hashlib
import json
import random
import re
import unicodedata
from copy import deepcopy

from toolbox.config import MINUTE_SPEECH_OVERLAY_FILE, MINUTE_SPEECH_SEED_FILE
from toolbox.storage import _lock, _read_json, _write_json, new_id

_seed_cache: dict = {"mtime": None, "topics": []}
_overlay_lock = _lock

EDIT_KEYS = {
    "text",
    "ja",
    "level",
    "themes",
    "status",
    "suffix",
    "words",
    "flags",
    "ai_pending",
    "ai_sensitive",
    "ai_reason",
}

SUFFIX_LABEL = "Include specific details."
JA_NOTICE = "日本語訳が未付与のお題は、日本語では見つかりません。英語で検索するか、AI検索を使ってください。"
SEARCH_LIMIT = 20
SEARCH_WINDOW = 80


def _load_seed() -> list[dict]:
    path = MINUTE_SPEECH_SEED_FILE
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    if _seed_cache["mtime"] != mtime:
        data = json.loads(path.read_text(encoding="utf-8"))
        topics = data.get("topics") if isinstance(data, dict) else []
        _seed_cache["topics"] = topics if isinstance(topics, list) else []
        _seed_cache["mtime"] = mtime
    return _seed_cache["topics"]


def load_overlay() -> dict:
    data = _read_json(MINUTE_SPEECH_OVERLAY_FILE, {"topics": {}, "originals": []})
    if not isinstance(data, dict):
        data = {"topics": {}, "originals": []}
    if not isinstance(data.get("topics"), dict):
        data["topics"] = {}
    if not isinstance(data.get("originals"), list):
        data["originals"] = []
    return data


def save_overlay(data: dict) -> None:
    with _overlay_lock:
        _write_json(MINUTE_SPEECH_OVERLAY_FILE, data)


def merged_topics() -> list[dict]:
    overlay = load_overlay()
    edits = overlay["topics"]
    rows: list[dict] = []
    for raw in _load_seed():
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        item = dict(raw)
        item.setdefault("themes", None)
        extra = edits.get(item["id"])
        if isinstance(extra, dict):
            for key, value in extra.items():
                if key in EDIT_KEYS:
                    item[key] = value
        rows.append(item)
    for original in overlay["originals"]:
        if isinstance(original, dict) and original.get("id"):
            rows.append(dict(original))
    return rows


def topic_by_id(topic_id: str) -> dict | None:
    for topic in merged_topics():
        if topic.get("id") == topic_id:
            return topic
    return None


def public_topic(topic: dict, *, used: bool = False) -> dict:
    return {
        "id": topic.get("id"),
        "type": int(topic.get("type") or 1),
        "text": topic.get("text") or "",
        "suffix": topic.get("suffix"),
        "words": topic.get("words") or 0,
        "ja": topic.get("ja"),
        "level": topic.get("level"),
        "flags": list(topic.get("flags") or []),
        "themes": topic.get("themes"),
        "status": topic.get("status") or "active",
        "source_order": topic.get("source_order"),
        "used": bool(used),
    }


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _flagged(topic: dict) -> bool:
    return bool(topic.get("flags"))


def passes_filters(
    topic: dict,
    *,
    type_value,
    level_max,
    include_flagged: bool,
    include_unleveled: bool,
) -> bool:
    if (topic.get("status") or "active") != "active":
        return False
    if type_value not in (None, "", "all", "mixed"):
        if int(topic.get("type") or 0) != _as_int(type_value, 0):
            return False
    if not include_flagged and _flagged(topic):
        return False
    level = topic.get("level")
    if level is None:
        return bool(include_unleveled)
    return _as_int(level, 99) <= _as_int(level_max, 3)


def _eligible(topics: list[dict], **filters) -> list[dict]:
    return [topic for topic in topics if passes_filters(topic, **filters)]


def draw_topic(
    *,
    type_value,
    exclude_ids: list[str] | None,
    level_max,
    include_flagged: bool,
    include_unleveled: bool,
) -> dict:
    filters = {
        "type_value": None if type_value in ("mixed", "all", "", None) else type_value,
        "level_max": level_max if level_max not in (None, "") else 3,
        "include_flagged": bool(include_flagged),
        "include_unleveled": bool(include_unleveled),
    }
    if type_value in ("mixed", "all"):
        filters["type_value"] = None
        pool = [topic for topic in _eligible(merged_topics(), **filters) if int(topic.get("type") or 0) in (1, 2)]
    else:
        pool = _eligible(merged_topics(), **filters)
    blocked = {str(item) for item in (exclude_ids or []) if item}
    remaining = [topic for topic in pool if topic.get("id") not in blocked]
    topic = random.choice(remaining) if remaining else None
    return {
        "topic": public_topic(topic) if topic else None,
        "pool": {"remaining": len(remaining), "total": len(pool)},
    }


def stats(*, type_value=None, level_max=3, include_flagged=False, include_unleveled=True) -> dict:
    topics = merged_topics()
    themes = set()
    by_type = {}
    for number in (1, 2):
        typed = [topic for topic in topics if int(topic.get("type") or 0) == number]
        active = _eligible(
            typed,
            type_value=number,
            level_max=level_max,
            include_flagged=include_flagged,
            include_unleveled=include_unleveled,
        )
        by_type[str(number)] = {
            "total": len(typed),
            "active": len(active),
            "flagged": sum(1 for topic in typed if _flagged(topic)),
            "hidden": sum(1 for topic in typed if (topic.get("status") or "active") != "active"),
        }
        for topic in typed:
            for theme in topic.get("themes") or []:
                if theme:
                    themes.add(str(theme))
    return {"types": by_type, "themes": sorted(themes)}


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").lower()
    return value


def _is_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text or ""))


def parse_number_query(query: str) -> tuple[int | None, int] | None:
    """「12」「1-12」「タイプ2 5」「#8」をお題番号として読む。番号でなければ None。"""
    text = _normalize(query).strip()
    text = re.sub(r"[ー−‐–—]", "-", text)
    typed = re.fullmatch(
        r"(?:(?:タイプ|type|t)\s*)?([12])\s*[-.．]\s*(?:no\.?|番号|#)?\s*(\d{1,4})",
        text,
    )
    if typed:
        order = int(typed.group(2))
        return (int(typed.group(1)), order) if order > 0 else None
    plain = re.fullmatch(
        r"(?:(?:タイプ|type|t)\s*([12])\s+)?(?:no\.?|番号|#)?\s*(\d{1,4})",
        text,
    )
    if not plain:
        return None
    order = int(plain.group(2))
    if order <= 0:
        return None
    type_num = int(plain.group(1)) if plain.group(1) else None
    return type_num, order


def _query_parts(query: str) -> tuple[list[str], list[str]]:
    normalized = _normalize(query)
    phrases = [a or b for a, b in re.findall(r'"([^"]+)"|「([^」]+)」', normalized)]
    rest = re.sub(r'"[^"]+"|「[^」]+」', " ", normalized)
    rest = re.sub(r"[^\w\s\u3040-\u30ff\u4e00-\u9fff'-]", " ", rest, flags=re.UNICODE)
    words = [word for word in rest.split() if word]
    return phrases, words


def _english_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", _normalize(text))


def _word_hit(word: str, text: str) -> int:
    """2=完全一致, 1=先頭一致, 0=不一致。"""
    if _is_japanese(word):
        return 2 if word in _normalize(text) else 0
    best = 0
    for token in _english_words(text):
        if token == word:
            return 2
        if len(word) >= 3 and token.startswith(word):
            best = 1
    return best


def keyword_search(
    *,
    query: str,
    type_value=None,
    level_max=3,
    include_flagged=False,
    include_unleveled=True,
    used_ids=None,
    exclude_used=False,
    hidden_ids=None,
    themes=None,
    limit=20,
    offset=0,
) -> dict:
    number = parse_number_query(query)
    if number:
        return _search_by_number(
            number,
            type_value=type_value,
            level_max=level_max,
            include_flagged=include_flagged,
            include_unleveled=include_unleveled,
            used_ids=used_ids,
            exclude_used=exclude_used,
            hidden_ids=hidden_ids,
            limit=limit,
            offset=offset,
        )
    phrases, words = _query_parts(query)
    if len("".join(phrases + words)) < 2:
        return {"error": "検索語は2文字以上にしてください。", "code": "query_too_short"}
    limit = max(1, min(_as_int(limit, SEARCH_LIMIT), SEARCH_LIMIT))
    offset = max(0, min(_as_int(offset, 0), SEARCH_WINDOW - limit))
    used = {str(item) for item in (used_ids or [])}
    hidden = {str(item) for item in (hidden_ids or [])}
    theme_filter = {str(item) for item in (themes or []) if item}
    japanese = _is_japanese(query)
    filters = {
        "type_value": None if type_value in (None, "", "all", "mixed") else type_value,
        "level_max": level_max if level_max not in (None, "") else 3,
        "include_flagged": bool(include_flagged),
        "include_unleveled": bool(include_unleveled),
    }
    pool = _eligible(merged_topics(), **filters)
    ja_ready = any((topic.get("ja") or "").strip() for topic in pool)
    ranked = []
    for topic in pool:
        if topic.get("id") in hidden:
            continue
        if exclude_used and topic.get("id") in used:
            continue
        if theme_filter:
            owned = {str(item) for item in (topic.get("themes") or [])}
            if not theme_filter.issubset(owned):
                continue
        target = topic.get("ja") or "" if japanese else topic.get("text") or ""
        if japanese and not (topic.get("ja") or "").strip():
            continue
        phrase_ok = all(_normalize(phrase) in _normalize(target) for phrase in phrases)
        if not phrase_ok:
            continue
        hits = [_word_hit(word, target) for word in words]
        if any(hit == 0 for hit in hits):
            continue
        if phrases:
            rank = 3
        elif words and all(hit == 2 for hit in hits):
            rank = 2
        else:
            rank = 1
        ranked.append((rank, _as_int(topic.get("source_order"), 10**9), topic))
    ranked.sort(key=lambda row: (-row[0], row[1], str(row[2].get("id"))))
    window = ranked[:SEARCH_WINDOW]
    page = window[offset:offset + limit]
    notice = JA_NOTICE if japanese and not ja_ready else ""
    return {
        "results": [public_topic(topic, used=topic.get("id") in used) for _, _, topic in page],
        "has_more": offset + len(page) < len(window),
        "notice": notice,
    }


def _search_by_number(
    number: tuple[int | None, int],
    *,
    type_value,
    level_max,
    include_flagged,
    include_unleveled,
    used_ids,
    exclude_used,
    hidden_ids,
    limit,
    offset,
) -> dict:
    query_type, order = number
    limit = max(1, min(_as_int(limit, SEARCH_LIMIT), SEARCH_LIMIT))
    offset = max(0, min(_as_int(offset, 0), SEARCH_WINDOW - limit))
    used = {str(item) for item in (used_ids or [])}
    hidden = {str(item) for item in (hidden_ids or [])}
    selected = None if type_value in (None, "", "all", "mixed") else _as_int(type_value, 0)
    if query_type and selected and query_type != selected:
        return {
            "results": [],
            "has_more": False,
            "notice": "選んでいるタイプと、番号に書いたタイプが違います。",
        }
    want_type = query_type or selected
    filters = {
        "type_value": want_type,
        "level_max": level_max if level_max not in (None, "") else 3,
        "include_flagged": bool(include_flagged),
        "include_unleveled": bool(include_unleveled),
    }
    matched = []
    blocked = []
    for topic in merged_topics():
        if _as_int(topic.get("source_order"), 0) != order:
            continue
        if want_type and int(topic.get("type") or 0) != int(want_type):
            continue
        if topic.get("id") in hidden or (exclude_used and topic.get("id") in used):
            continue
        if passes_filters(topic, **filters):
            matched.append(topic)
        else:
            blocked.append(topic)
    matched.sort(key=lambda topic: (int(topic.get("type") or 0), str(topic.get("id"))))
    page = matched[offset:offset + limit]
    notice = ""
    if not page and blocked:
        notice = "この番号のお題は、いまの難易度・フラグ・非公開の条件では出ません。"
    elif not page:
        notice = "その番号のお題はありません。"
    return {
        "results": [public_topic(topic, used=topic.get("id") in used) for topic in page],
        "has_more": offset + len(page) < len(matched),
        "notice": notice,
    }


def list_catalog(*, type_value, offset=0, limit=50) -> dict:
    """タイプごとの番号順。1ページ分だけ返す。"""
    type_num = _as_int(type_value, 1)
    if type_num not in (1, 2):
        type_num = 1
    rows = []
    for topic in merged_topics():
        if int(topic.get("type") or 0) != type_num:
            continue
        if (topic.get("status") or "active") != "active":
            continue
        order = _as_int(topic.get("source_order"), 0)
        if order <= 0 or order > 10000:
            continue
        rows.append(topic)
    offset = max(0, _as_int(offset, 0))
    limit = max(1, min(_as_int(limit, 50), 100))
    page = rows[offset:offset + limit]
    return {
        "results": [public_topic(topic) for topic in page],
        "has_more": offset + len(page) < len(rows),
        "count": len(rows),
        "offset": offset,
    }


def content_hash(topic: dict) -> str:
    themes = " ".join(str(item) for item in (topic.get("themes") or []))
    source = "\n".join([topic.get("text") or "", topic.get("ja") or "", themes])
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def embed_document(topic: dict) -> str:
    parts = [topic.get("text") or ""]
    if topic.get("ja"):
        parts.append(str(topic["ja"]))
    themes = [str(item) for item in (topic.get("themes") or []) if item]
    if themes:
        parts.append(" ".join(themes))
    return "\n".join(parts)


def update_topic(topic_id: str, fields: dict) -> dict | None:
    overlay = load_overlay()
    originals = overlay["originals"]
    for index, original in enumerate(originals):
        if original.get("id") == topic_id:
            current = dict(original)
            for key, value in fields.items():
                if key in EDIT_KEYS or key in ("type",):
                    current[key] = value
            if "text" in fields:
                current["words"] = len(re.findall(r"[A-Za-z0-9']+", current.get("text") or ""))
            originals[index] = current
            overlay["originals"] = originals
            save_overlay(overlay)
            return current
    if topic_by_id(topic_id) is None:
        return None
    edits = dict(overlay["topics"].get(topic_id) or {})
    for key, value in fields.items():
        if key in EDIT_KEYS:
            edits[key] = value
    if "text" in fields:
        edits["words"] = len(re.findall(r"[A-Za-z0-9']+", str(fields.get("text") or "")))
    overlay["topics"][topic_id] = edits
    save_overlay(overlay)
    return topic_by_id(topic_id)


def add_original(*, type_value: int, text: str, level, ja: str) -> dict:
    topic = {
        "id": "orig-" + new_id(),
        "type": 1 if int(type_value) != 2 else 2,
        "source_order": 10**9,
        "text": text.strip(),
        "suffix": None,
        "words": len(re.findall(r"[A-Za-z0-9']+", text)),
        "flags": [],
        "level": level,
        "ja": ja.strip() or None,
        "themes": None,
        "status": "active",
    }
    overlay = load_overlay()
    overlay["originals"].append(topic)
    save_overlay(overlay)
    return topic


def hide_flagged() -> int:
    overlay = load_overlay()
    changed = 0
    for topic in merged_topics():
        if not _flagged(topic) or (topic.get("status") or "active") == "hidden":
            continue
        if str(topic.get("id") or "").startswith("orig-"):
            for original in overlay["originals"]:
                if original.get("id") == topic["id"]:
                    original["status"] = "hidden"
                    changed += 1
        else:
            edits = dict(overlay["topics"].get(topic["id"]) or {})
            edits["status"] = "hidden"
            overlay["topics"][topic["id"]] = edits
            changed += 1
    save_overlay(overlay)
    return changed


def approve_ai() -> int:
    overlay = load_overlay()
    changed = 0
    for topic_id, edits in list(overlay["topics"].items()):
        if isinstance(edits, dict) and edits.get("ai_pending"):
            edits["ai_pending"] = False
            overlay["topics"][topic_id] = edits
            changed += 1
    for original in overlay["originals"]:
        if original.get("ai_pending"):
            original["ai_pending"] = False
            changed += 1
    save_overlay(overlay)
    return changed


def apply_ai_rows(rows: list[dict]) -> int:
    overlay = load_overlay()
    applied = 0
    by_id = {topic["id"]: topic for topic in merged_topics()}
    for row in rows:
        topic_id = str(row.get("id") or "")
        current = by_id.get(topic_id)
        if not current:
            continue
        level = row.get("level")
        try:
            level = int(level)
        except (TypeError, ValueError):
            level = None
        if level not in (1, 2, 3):
            level = None
        sensitive = bool(row.get("sensitive"))
        fields = {
            "level": level if level is not None else current.get("level"),
            "ja": (str(row.get("ja") or "").strip() or current.get("ja")),
            "themes": row.get("themes") if isinstance(row.get("themes"), list) else current.get("themes"),
            "ai_pending": True,
            "ai_sensitive": sensitive,
            "ai_reason": str(row.get("sensitive_reason") or "")[:200],
        }
        if sensitive:
            fields["status"] = "hidden"
        if str(topic_id).startswith("orig-"):
            for original in overlay["originals"]:
                if original.get("id") == topic_id:
                    original.update(fields)
                    applied += 1
        else:
            edits = dict(overlay["topics"].get(topic_id) or {})
            edits.update(fields)
            overlay["topics"][topic_id] = edits
            applied += 1
    save_overlay(overlay)
    return applied


def pending_classification(limit: int = 20) -> list[dict]:
    pending = []
    for topic in merged_topics():
        if topic.get("level") is None or not (topic.get("ja") or "").strip():
            pending.append(topic)
            if len(pending) >= limit:
                break
    return pending


def classification_count() -> int:
    return sum(
        1
        for topic in merged_topics()
        if topic.get("level") is None or not (topic.get("ja") or "").strip()
    )


def admin_page_topics(*, type_value=None, status=None, flagged=None, level=None, has_ja=None, q="", offset=0, limit=40) -> dict:
    rows = merged_topics()
    needle = _normalize(q)
    filtered = []
    for topic in rows:
        if type_value in (1, 2, "1", "2") and int(topic.get("type") or 0) != int(type_value):
            continue
        if status in ("active", "hidden") and (topic.get("status") or "active") != status:
            continue
        if flagged == "yes" and not _flagged(topic):
            continue
        if flagged == "no" and _flagged(topic):
            continue
        if level in ("1", "2", "3", 1, 2, 3):
            if str(topic.get("level")) != str(level):
                continue
        if level == "none" and topic.get("level") is not None:
            continue
        if has_ja == "yes" and not (topic.get("ja") or "").strip():
            continue
        if has_ja == "no" and (topic.get("ja") or "").strip():
            continue
        if needle and needle not in _normalize(topic.get("text") or "") and needle not in _normalize(topic.get("ja") or ""):
            continue
        filtered.append(topic)
    offset = max(0, _as_int(offset, 0))
    limit = max(1, min(_as_int(limit, 40), 50))
    page = filtered[offset:offset + limit]
    slim = []
    for topic in page:
        item = public_topic(topic)
        item["ai_pending"] = bool(topic.get("ai_pending"))
        item["ai_reason"] = topic.get("ai_reason") or ""
        item["source_order"] = topic.get("source_order")
        slim.append(item)
    return {
        "results": slim,
        "has_more": offset + len(page) < len(filtered),
        "matched": len(filtered),
    }


def snapshot_for_tests():
    return deepcopy(merged_topics()[:2])
