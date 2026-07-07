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

DEFAULT_SETTINGS = {
    "part_a_prep_enabled": True,
}


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _normalize(raw: dict | None) -> dict:
    data = deepcopy(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return data
    if "part_a_prep_enabled" in raw:
        data["part_a_prep_enabled"] = bool(raw.get("part_a_prep_enabled"))
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
    """生徒画面向けに公開する設定のみ。"""
    s = load_settings()
    return {"part_a_prep_enabled": s["part_a_prep_enabled"]}
