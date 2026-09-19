"""Debate app の表示設定（背景・透過率）の永続化。

GTECアプリの管理画面と同様の考え方だが、依存関係を持たせないよう完全に独立して実装する
（data/debate/settings.json に保存）。
"""
import json
import threading
from copy import deepcopy
from pathlib import Path

from debate.config import (
    DATA_DIR,
    JUDGE_MODEL_OVERRIDE,
    ensure_dirs,
)
from debate.judge_models import (
    DEFAULT_JUDGE_MODEL_MODE,
    get_judge_model_options,
    resolve_judge_model_id,
    resolve_judge_model_mode,
)

_lock = threading.Lock()
SETTINGS_FILE = DATA_DIR / "settings.json"

BACKGROUND_PRESETS = {
    "meadow": {"label": "草原", "image": "debate/images/bg/debate-bg-meadow.jpg"},
    "forest": {"label": "森", "image": "debate/images/bg/debate-bg-forest.jpg"},
    "mountain": {"label": "山", "image": "debate/images/bg/debate-bg-mountain.jpg"},
    "ocean": {"label": "海", "image": "debate/images/bg/debate-bg-ocean.jpg"},
    "lake": {"label": "湖", "image": "debate/images/bg/debate-bg-lake.jpg"},
}

DEFAULT_BACKGROUND_ID = "forest"
DEFAULT_BACKGROUND_OPACITY = 0.32

TRANSCRIPTION_MODES = ("batch", "realtime")

DEFAULT_SETTINGS = {
    "background_id": DEFAULT_BACKGROUND_ID,
    "background_opacity": DEFAULT_BACKGROUND_OPACITY,
    "transcription_mode": "batch",
    "judge_model_mode": DEFAULT_JUDGE_MODEL_MODE,
    "opponent_model_mode": DEFAULT_JUDGE_MODEL_MODE,
}


def resolve_judge_model(mode: str | None = None) -> str:
    """管理画面で選択中のジャッジモデルIDを返す。DEBATE_JUDGE_MODEL があれば最優先。"""
    if JUDGE_MODEL_OVERRIDE:
        return JUDGE_MODEL_OVERRIDE
    selected = mode if mode in get_judge_model_options() else None
    if selected is None:
        stored = load_settings().get("judge_model_mode", DEFAULT_JUDGE_MODEL_MODE)
        selected = resolve_judge_model_mode(stored, fallback_mode=DEFAULT_JUDGE_MODEL_MODE)
    return resolve_judge_model_id(selected)


def resolve_opponent_model(mode: str | None = None) -> str:
    """Solo Practice の対戦AIモデル。選択肢はジャッジと同一（価格定義を再利用）。"""
    selected = mode if mode in get_judge_model_options() else None
    if selected is None:
        stored = load_settings().get("opponent_model_mode", DEFAULT_JUDGE_MODEL_MODE)
        selected = resolve_judge_model_mode(stored, fallback_mode=DEFAULT_JUDGE_MODEL_MODE)
    return resolve_judge_model_id(selected)


def _clamp_opacity(value, default: float = DEFAULT_BACKGROUND_OPACITY) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return round(max(0.0, min(n, 1.0)), 2)


def _normalize(raw: dict | None) -> dict:
    data = deepcopy(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return data

    bg_id = raw.get("background_id")
    if bg_id in BACKGROUND_PRESETS:
        data["background_id"] = bg_id

    if "background_opacity" in raw:
        data["background_opacity"] = _clamp_opacity(raw.get("background_opacity"))

    mode = raw.get("transcription_mode")
    if mode in TRANSCRIPTION_MODES:
        data["transcription_mode"] = mode

    judge_mode = raw.get("judge_model_mode")
    if judge_mode in get_judge_model_options():
        data["judge_model_mode"] = judge_mode
    elif judge_mode:
        data["judge_model_mode"] = DEFAULT_JUDGE_MODEL_MODE

    opponent_mode = raw.get("opponent_model_mode")
    if opponent_mode in get_judge_model_options():
        data["opponent_model_mode"] = opponent_mode
    elif opponent_mode:
        data["opponent_model_mode"] = DEFAULT_JUDGE_MODEL_MODE

    return data


def resolve_background(background_id: str | None = None) -> dict:
    preset_id = background_id if background_id in BACKGROUND_PRESETS else DEFAULT_BACKGROUND_ID
    preset = BACKGROUND_PRESETS[preset_id]
    return {
        "background_id": preset_id,
        "background_label": preset["label"],
        "background_image": preset["image"],
    }


def load_settings() -> dict:
    ensure_dirs()
    with _lock:
        if not SETTINGS_FILE.is_file():
            return deepcopy(DEFAULT_SETTINGS)
        try:
            with SETTINGS_FILE.open(encoding="utf-8") as handle:
                return _normalize(json.load(handle))
        except (json.JSONDecodeError, OSError):
            return deepcopy(DEFAULT_SETTINGS)


def save_settings(data: dict) -> dict:
    ensure_dirs()
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
    settings = load_settings()
    return {**settings, **resolve_background(settings.get("background_id"))}
