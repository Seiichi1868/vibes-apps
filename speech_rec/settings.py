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

DEFAULT_DELIVERY_RULES: list[dict[str, Any]] = [
    {"level": 6, "pause_n": 1, "pause_max": 1.5, "silent_ratio": 0.10},
    {"level": 5, "pause_n": 3, "pause_max": 2.0, "silent_ratio": 0.20},
    {"level": 4, "pause_n": 5, "pause_max": 3.0, "silent_ratio": 0.30},
    {"level": 3, "pause_n": 8, "pause_max": 4.5, "silent_ratio": 0.40},
    {"level": 2, "pause_n": 12, "pause_max": 7.0, "silent_ratio": 0.55},
]

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
    "queue_limit": 60,
    "audio_cap_mb": 100,
    "transcript_ttl_min": 30,
    "record_retention_days": 60,
    "pause_gap_sec": 0.8,
    "sentence_gap_min": 2.0,
    "clause_gap_min": 1.2,
    "mid_gap_min": 0.5,
    "unknown_gap_min": 1.0,
    "calibration_mode": False,
    "whisper_hint": False,
    "settings_rev": 0,
    "score_config": DEFAULT_SCORE_CONFIG,
    "delivery_rules": DEFAULT_DELIVERY_RULES,
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
        elif key == "delivery_rules" and isinstance(value, list) and value:
            merged["delivery_rules"] = value
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
    current["settings_rev"] = int(current.get("settings_rev") or 0) + 1
    write_json(settings_path(), current)
    return current


def bump_settings_rev() -> int:
    """設定の中身は変えず、開いている生徒画面へ取り直しを知らせる。"""
    current = get_settings()
    rev = int(current.get("settings_rev") or 0) + 1
    current["settings_rev"] = rev
    write_json(settings_path(), current)
    return rev
