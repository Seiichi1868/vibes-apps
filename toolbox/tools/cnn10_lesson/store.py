"""CNN10 授業の現在設定。data/toolbox にだけ保存する。"""
from __future__ import annotations

import json

from toolbox.config import DATA_DIR

LESSON_FILE = DATA_DIR / "cnn10_lesson.json"

EMPTY = {
    "title": "",
    "url": "",
    "video_id": "",
    "start": "0:00",
    "end": "",
    "script": "",
    "translation": "",
    "vocabulary": [],
    "warmup": [],
    "discussion": [],
}


def load_lesson() -> dict:
    if not LESSON_FILE.is_file():
        return dict(EMPTY)
    try:
        data = json.loads(LESSON_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(EMPTY)
    if not isinstance(data, dict):
        return dict(EMPTY)
    merged = dict(EMPTY)
    merged.update({k: data.get(k, EMPTY[k]) for k in EMPTY})
    return merged


def save_lesson(payload: dict) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = load_lesson()
    for key in EMPTY:
        if key in payload:
            current[key] = payload[key]
    LESSON_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current
