"""GTEC アプリ設定の永続化（data/gtec_settings.json）。"""

import json
import os
import threading
from copy import deepcopy
from pathlib import Path

_lock = threading.Lock()
DATA_DIR = Path(
    os.environ.get("GTEC_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))
).expanduser()
SETTINGS_FILE = DATA_DIR / "gtec_settings.json"

PART_DEFAULTS = {
    "a": {"prep_enabled": True, "prep_seconds": 30},
    "b": {"prep_enabled": True, "prep_seconds": 10},
    "c": {"prep_enabled": True, "prep_seconds": 30},
    "d": {"prep_enabled": True, "prep_seconds": 60},
}

DEFAULT_SETTINGS = {
    f"part_{p}_prep_enabled": v["prep_enabled"]
    for p, v in PART_DEFAULTS.items()
} | {
    f"part_{p}_prep_seconds": v["prep_seconds"]
    for p, v in PART_DEFAULTS.items()
}


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _clamp_seconds(value, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(n, 600))


def _normalize(raw: dict | None) -> dict:
    data = deepcopy(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return data

    for part, defaults in PART_DEFAULTS.items():
        enabled_key = f"part_{part}_prep_enabled"
        seconds_key = f"part_{part}_prep_seconds"
        if enabled_key in raw:
            data[enabled_key] = bool(raw.get(enabled_key))
        if seconds_key in raw:
            data[seconds_key] = _clamp_seconds(raw.get(seconds_key), defaults["prep_seconds"])

    return data


def load_settings() -> dict:
    _ensure_data_dir()
    with _lock:
        if not SETTINGS_FILE.is_file():
            return deepcopy(DEFAULT_SETTINGS)
        try:
            with SETTINGS_FILE.open(encoding="utf-8") as handle:
                return _normalize(json.load(handle))
        except (json.JSONDecodeError, OSError):
            return deepcopy(DEFAULT_SETTINGS)


def save_settings(data: dict) -> dict:
    _ensure_data_dir()
    normalized = _normalize(data)
    with _lock:
        with SETTINGS_FILE.open("w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
    return normalized


def update_settings(**kwargs) -> dict:
    current = load_settings()
    current.update(kwargs)
    return save_settings(current)


def public_settings() -> dict:
    """生徒画面向けに公開する設定。"""
    return load_settings()
