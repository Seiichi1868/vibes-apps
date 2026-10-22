"""ルーブリック点数と WPM 点の合計。副作用なし。"""
from __future__ import annotations

from speech_rec.metrics import wpm_points
from speech_rec.rubric import LEVEL_POINTS

RUBRIC_KEYS = ("general_description", "delivery", "language_use", "topic_development")


def clamp_level(value) -> int:
    try:
        level = int(round(float(value)))
    except (TypeError, ValueError):
        level = 1
    return min(6, max(1, level))


def score(levels: dict, words_counted: int, on_topic: bool, score_config: dict) -> dict:
    weights = score_config.get("w") or {}
    points = {key: LEVEL_POINTS[clamp_level(levels.get(key))] for key in RUBRIC_KEYS}
    wpm = wpm_points(int(words_counted or 0), score_config)
    if not on_topic:
        wpm = round(wpm * float(score_config.get("off_topic_multiplier") or 1), 4)
    total = sum(float(weights.get(key, 1)) * points[key] for key in RUBRIC_KEYS) + wpm
    return {
        "points": points,
        "wpm_points": wpm,
        "total": round(total, 4),
        "config_version": score_config.get("version"),
    }
