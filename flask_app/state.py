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

AI_MODE_OPTIONS: dict[str, dict[str, str]] = {
    "4o-mini": {
        "label": "節約モード",
        "hint": "全機能で gpt-4o-mini を使用",
        "model": Config.MODEL_ECONOMY,
    },
    "5-mini": {
        "label": "前世代miniモード",
        "hint": "添削・解説・発音に gpt-5-mini",
        "model": "gpt-5-mini",
    },
    "5.4-mini": {
        "label": "最新高精度モード",
        "hint": "添削・解説・発音に gpt-5.4-mini",
        "model": "gpt-5.4-mini",
    },
    "5.4-nano": {
        "label": "最安実験モード",
        "hint": "添削・解説・発音に gpt-5.4-nano",
        "model": "gpt-5.4-nano",
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
