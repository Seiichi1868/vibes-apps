import json
import os
import threading
from copy import deepcopy
from pathlib import Path

import flask_app.state as state
from flask_app.state import DEFAULT_ENABLED_LANGUAGES
from flask_app.utils.language_utils import (
    normalize_ai_mode,
    normalize_enabled_languages,
    normalize_ui_language,
)

_lock = threading.Lock()
DATA_DIR = Path(
    os.environ.get("NEWS_DATA_DIR", str(Path(__file__).resolve().parent.parent.parent / "data"))
).expanduser()
SETTINGS_FILE = DATA_DIR / "vibespeak_runtime.json"

DEFAULT_SETTINGS = {
    "tts_enabled": False,
    "gate_lock_enabled": None,
    "ai_mode": None,
    "enabled_study_languages": None,
    "default_ui_language": None,
}


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_settings(raw: dict | None) -> dict:
    data = deepcopy(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return data

    if "tts_enabled" in raw:
        data["tts_enabled"] = bool(raw.get("tts_enabled"))

    if "gate_lock_enabled" in raw:
        value = raw.get("gate_lock_enabled")
        if isinstance(value, bool):
            data["gate_lock_enabled"] = value

    if raw.get("ai_mode"):
        try:
            data["ai_mode"] = normalize_ai_mode(str(raw.get("ai_mode")))
        except ValueError:
            data["ai_mode"] = None

    if raw.get("enabled_study_languages") is not None:
        try:
            data["enabled_study_languages"] = normalize_enabled_languages(raw.get("enabled_study_languages"))
        except ValueError:
            data["enabled_study_languages"] = None

    if raw.get("default_ui_language"):
        data["default_ui_language"] = normalize_ui_language(raw.get("default_ui_language"))

    return data


def load_runtime_settings() -> dict:
    _ensure_data_dir()
    with _lock:
        if not SETTINGS_FILE.is_file():
            return deepcopy(DEFAULT_SETTINGS)
        try:
            with SETTINGS_FILE.open(encoding="utf-8") as handle:
                return _normalize_settings(json.load(handle))
        except (json.JSONDecodeError, OSError):
            return deepcopy(DEFAULT_SETTINGS)


def save_runtime_settings(data: dict) -> dict:
    _ensure_data_dir()
    normalized = _normalize_settings(data)
    with _lock:
        with SETTINGS_FILE.open("w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
    return normalized


def current_runtime_settings() -> dict:
    return {
        "tts_enabled": bool(state.TTS_ENABLED),
        "gate_lock_enabled": bool(state.CLASS_CODE_LOCK_ENABLED),
        "ai_mode": state.AI_MODE,
        "enabled_study_languages": list(state.ENABLED_STUDY_LANGUAGES),
        "default_ui_language": state.DEFAULT_UI_LANGUAGE,
    }


def persist_current_runtime_settings() -> dict:
    return save_runtime_settings(current_runtime_settings())


def apply_runtime_settings(data: dict | None = None) -> None:
    normalized = _normalize_settings(data or load_runtime_settings())

    state.TTS_ENABLED = bool(normalized["tts_enabled"])

    if normalized["gate_lock_enabled"] is not None:
        state.CLASS_CODE_LOCK_ENABLED = bool(normalized["gate_lock_enabled"])

    if normalized["ai_mode"]:
        state.AI_MODE = normalized["ai_mode"]

    if normalized["enabled_study_languages"]:
        state.ENABLED_STUDY_LANGUAGES = list(normalized["enabled_study_languages"])
    else:
        state.ENABLED_STUDY_LANGUAGES = list(DEFAULT_ENABLED_LANGUAGES)

    if normalized["default_ui_language"]:
        state.DEFAULT_UI_LANGUAGE = normalized["default_ui_language"]


def update_runtime_settings(**kwargs) -> dict:
    current = current_runtime_settings()
    current.update(kwargs)
    saved = save_runtime_settings(current)
    apply_runtime_settings(saved)
    return saved


def load_and_apply_runtime_settings() -> None:
    apply_runtime_settings(load_runtime_settings())
