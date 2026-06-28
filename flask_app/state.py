"""ランタイムで変更可能なアプリケーション状態"""

import os

from flask_app.config import Config


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in {"1", "true", "on", "yes"}:
        return True
    if value in {"0", "false", "off", "no"}:
        return False
    return default


_on_render = os.environ.get("RENDER", "").strip().lower() == "true"

AI_MODE_OPTIONS: dict[str, dict[str, str | int]] = {
    "4o-mini": {
        "label": "gpt-4o-mini",
        "hint": "gpt-4o-mini",
        "model": Config.MODEL_ECONOMY,
        "cost_performance": 5,
        "performance": 3,
    },
    "5.4-nano": {
        "label": "gpt-5.4-nano",
        "hint": "gpt-5.4-nano",
        "model": "gpt-5.4-nano",
        "cost_performance": 5,
        "performance": 2,
    },
    "5-mini": {
        "label": "gpt-5-mini",
        "hint": "gpt-5-mini",
        "model": "gpt-5-mini",
        "cost_performance": 4,
        "performance": 3,
    },
    "5.4-mini": {
        "label": "gpt-5.4-mini",
        "hint": "gpt-5.4-mini",
        "model": "gpt-5.4-mini",
        "cost_performance": 3,
        "performance": 4,
    },
    "4o": {
        "label": "gpt-4o",
        "hint": "gpt-4o",
        "model": "gpt-4o",
        "cost_performance": 2,
        "performance": 4,
    },
    "5.4": {
        "label": "gpt-5.4",
        "hint": "gpt-5.4",
        "model": "gpt-5.4",
        "cost_performance": 1,
        "performance": 5,
    },
}

TTS_VOICE_BY_LANG = {
    "en-US": "nova",
    "es-ES": "shimmer",
    "ja-JP": "nova",
    "ro-RO": "onyx",
}

TTS_GENERATE_VOICE_BY_LANG = {
    "en-US": "alloy",
    "es-ES": "shimmer",
    "ja-JP": "nova",
    "ro-RO": "onyx",
}

STUDY_LANGUAGE_CATALOG: dict[str, dict[str, str]] = {
    "en": {
        "id": "en",
        "api_lang": "en-US",
        "label": "English",
        "label_ja": "英語",
        "flag": "🇬🇧",
    },
    "es": {
        "id": "es",
        "api_lang": "es-ES",
        "label": "Spanish",
        "label_ja": "スペイン語",
        "flag": "🇪🇸",
    },
    "ja": {
        "id": "ja",
        "api_lang": "ja-JP",
        "label": "Japanese",
        "label_ja": "日本語",
        "flag": "🇯🇵",
    },
    "ro": {
        "id": "ro",
        "api_lang": "ro-RO",
        "label": "Romanian",
        "label_ja": "ルーマニア語",
        "flag": "🇷🇴",
    },
}

DEFAULT_ENABLED_LANGUAGES = ["en", "es", "ja", "ro"]
ENABLED_STUDY_LANGUAGES: list[str] = list(DEFAULT_ENABLED_LANGUAGES)
AI_MODE = Config.DEFAULT_AI_MODE
TTS_ENABLED = False
# Render 本番はデフォルト OFF（管理画面から ON 可能）。ローカルはデフォルト ON。
CLASS_CODE_LOCK_ENABLED = _env_bool(
    "GATE_LOCK_ENABLED",
    default=not _on_render,
)
DEFAULT_UI_LANGUAGE = "ja"
DEFAULT_VISIBLE_SECTIONS: dict[str, bool] = {key: True for key in ("sample", "compose", "grammar", "recorder", "result", "comparison")}
VISIBLE_SECTIONS: dict[str, bool] = dict(DEFAULT_VISIBLE_SECTIONS)
