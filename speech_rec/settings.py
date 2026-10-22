"""設定 JSON。生徒公開は既定でオフ。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from speech_rec.config import data_dir
from speech_rec.store import read_json, write_json

DEFAULT_SCORE_CONFIG: dict[str, Any] = {
    "version": 1,
    "w": {
        "general_description": 1.0,
        "delivery": 1.0,
        "language_use": 1.0,
        "topic_development": 1.0,
    },
    "w_wpm": 1.0,
    "wpm_cap": None,
    "grace_sec": 3,
    "exclude_nonlexical_fillers": True,
    "off_topic_multiplier": 1.0,
}

DEFAULTS: dict[str, Any] = {
    "student_enabled": False,
    "id_fields": {
        "enabled": False,
        "year": True,
        "grade": True,
        "class": True,
        "number": True,
        "class_max": 10,
        "number_max": 45,
    },
    "eval_model": "gpt-4o-mini",
    "daily_limit_usd": 2.0,
    "audio_cap_mb": 100,
    "transcript_ttl_min": 30,
    "record_retention_days": 60,
    "pause_gap_sec": 0.8,
    "calibration_mode": False,
    "whisper_hint": False,
    "score_config": DEFAULT_SCORE_CONFIG,
}


def settings_path():
    return data_dir() / "settings.json"


def get_settings() -> dict[str, Any]:
    stored = read_json(settings_path(), {})
    if not isinstance(stored, dict):
        stored = {}
    merged = deepcopy(DEFAULTS)
    for key, value in stored.items():
        if key == "id_fields" and isinstance(value, dict):
            merged["id_fields"].update(value)
        elif key == "score_config" and isinstance(value, dict):
            merged["score_config"].update(value)
            if isinstance(value.get("w"), dict):
                merged["score_config"]["w"] = {**DEFAULT_SCORE_CONFIG["w"], **value["w"]}
        elif key in merged:
            merged[key] = value
    return merged


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    current = get_settings()
    for key, value in updates.items():
        if key not in DEFAULTS:
            continue
        if key == "id_fields" and isinstance(value, dict):
            current["id_fields"].update(value)
        elif key == "score_config" and isinstance(value, dict):
            current["score_config"].update(value)
        else:
            current[key] = value
    write_json(settings_path(), current)
    return current
