"""CNN10 授業の現在設定とアーカイブ。data/toolbox にだけ保存する。"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone

from toolbox.config import DATA_DIR

LESSON_FILE = DATA_DIR / "cnn10_lesson.json"

EMPTY = {
    "title": "",
    "lesson_name": "",
    "url": "",
    "video_id": "",
    "start": "0:00",
    "end": "",
    "script": "",
    "translation": "",
    "pairs": [],
    "vocabulary": [],
    "warmup": [],
    "discussion": [],
    "writing": [],
    "subtitles": True,
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _lesson(raw) -> dict:
    merged = dict(EMPTY)
    if isinstance(raw, dict):
        for key in EMPTY:
            if key in raw:
                merged[key] = raw[key]
    return merged


def _load_raw() -> dict:
    if not LESSON_FILE.is_file():
        return {"current": dict(EMPTY), "archives": []}
    try:
        data = json.loads(LESSON_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"current": dict(EMPTY), "archives": []}
    if not isinstance(data, dict):
        return {"current": dict(EMPTY), "archives": []}
    if "current" not in data and "archives" not in data:
        return {"current": _lesson(data), "archives": []}
    archives = data.get("archives") if isinstance(data.get("archives"), list) else []
    return {"current": _lesson(data.get("current")), "archives": archives}


def _save_raw(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LESSON_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_lesson() -> dict:
    return _load_raw()["current"]


def _sync_translation(current: dict, previous_script: str) -> None:
    new_script = str(current.get("script") or "")
    if re.sub(r"\s+", " ", new_script).strip() == re.sub(r"\s+", " ", previous_script).strip():
        return
    pairs = current.get("pairs") if isinstance(current.get("pairs"), list) else []
    if not pairs and not str(current.get("translation") or "").strip():
        return
    from toolbox.services.script_align import sync_pairs_to_script
    from toolbox.tools.cnn10_lesson.assist import translate_script

    synced = sync_pairs_to_script(new_script, pairs)
    if not synced:
        return
    kept = synced["pairs"]
    indexes = synced["retranslate"]
    if indexes:
        snippet = " ".join(str(kept[index].get("en") or "") for index in indexes)
        try:
            fresh = translate_script(snippet).get("pairs") or []
            if len(fresh) == len(indexes):
                for index, pair in zip(indexes, fresh):
                    kept[index]["ja"] = str(pair.get("ja") or "").strip()
        except Exception:
            pass
    current["pairs"] = kept
    current["translation"] = "\n".join(
        str(row.get("ja") or "").strip() for row in kept if str(row.get("ja") or "").strip()
    )


def save_lesson(payload: dict) -> dict:
    data = _load_raw()
    current = data["current"]
    previous_script = str(current.get("script") or "")
    if isinstance(payload, dict):
        for key in EMPTY:
            if key in payload:
                current[key] = payload[key]
        if "script" in payload:
            _sync_translation(current, previous_script)
        if "url" in payload:
            current["video_id"] = _video_id_from_url(payload.get("url") or "")
    data["current"] = _lesson(current)
    _save_raw(data)
    return data["current"]


_YT_ID = re.compile(r"(?:v=|vi=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})")


def _video_id_from_url(url: str) -> str:
    text = str(url or "")
    match = _YT_ID.search(text)
    if match:
        return match.group(1)
    match = re.search(r"([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])", text)
    return match.group(1) if match else ""


def _video_id(item: dict) -> str:
    from_url = _video_id_from_url(item.get("url") or "")
    if from_url:
        return from_url
    video_id = str(item.get("video_id") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return video_id
    return ""


def list_archives() -> list[dict]:
    rows = []
    for item in _load_raw()["archives"]:
        if not isinstance(item, dict):
            continue
        video_id = _video_id(item)
        rows.append({
            "archive_id": item.get("archive_id") or "",
            "title": item.get("title") or item.get("lesson_name") or "無題",
            "lesson_name": item.get("lesson_name") or "",
            "archived_at": item.get("archived_at") or "",
            "video_id": video_id,
            "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg" if video_id else "",
            "script": str(item.get("script") or ""),
            "has_vocab": bool(item.get("vocabulary")),
            "has_warmup": bool(item.get("warmup")),
            "has_discussion": bool(item.get("discussion")),
            "has_writing": bool(item.get("writing")),
        })
    return rows


def get_archive(archive_id: str) -> dict | None:
    archive_id = str(archive_id or "").strip()
    for item in _load_raw()["archives"]:
        if isinstance(item, dict) and str(item.get("archive_id") or "") == archive_id:
            lesson = _lesson(item)
            lesson["video_id"] = _video_id(lesson)
            lesson["archive_id"] = archive_id
            lesson["archived_at"] = item.get("archived_at") or ""
            return lesson
    return None


def archive_current(title: str = "", lesson_name: str = "") -> dict:
    data = _load_raw()
    item = _lesson(data["current"])
    if title:
        item["title"] = title
    if lesson_name:
        item["lesson_name"] = lesson_name
    item["video_id"] = _video_id(item)
    if not (item.get("url") or item.get("script")):
        raise ValueError("保存する授業設定がありません。")
    item["archive_id"] = secrets.token_hex(8)
    item["archived_at"] = _now()
    data["archives"].insert(0, item)
    _save_raw(data)
    return item


def restore_archive(archive_id: str) -> dict:
    item = get_archive(archive_id)
    if not item:
        raise LookupError("アーカイブが見つかりません。")
    return save_lesson(item)


def delete_archive(archive_id: str) -> None:
    data = _load_raw()
    archive_id = str(archive_id or "").strip()
    kept = [
        item for item in data["archives"]
        if not (isinstance(item, dict) and str(item.get("archive_id") or "") == archive_id)
    ]
    if len(kept) == len(data["archives"]):
        raise LookupError("アーカイブが見つかりません。")
    data["archives"] = kept
    _save_raw(data)
