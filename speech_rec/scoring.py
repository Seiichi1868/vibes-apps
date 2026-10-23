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


def speaking_wpm(words_counted: int, speak_sec: float) -> float:
    """1分あたりの採用語数。発話枠が60秒なら語数と同じ。"""
    seconds = float(speak_sec or 60)
    if seconds <= 0:
        seconds = 60.0
    return round(int(words_counted or 0) * 60.0 / seconds, 2)


def delivery_cap(wpm: float) -> int | None:
    """遅い発話は、間が少なくても Delivery の点数をここまで。"""
    rate = float(wpm)
    if rate <= 30:
        return 10
    if rate <= 40:
        return 20
    if rate <= 60:
        return 30
    if rate <= 80:
        return 35
    return None


def cap_delivery_level(level: int, wpm: float) -> int:
    cap = delivery_cap(wpm)
    capped = clamp_level(level)
    if cap is None:
        return capped
    while capped > 1 and LEVEL_POINTS[capped] > cap:
        capped -= 1
    return capped


def score(levels: dict, words_counted: int, on_topic: bool, score_config: dict, *, speak_sec: float = 60) -> dict:
    weights = score_config.get("w") or {}
    wpm_rate = speaking_wpm(words_counted, speak_sec)
    capped_levels = dict(levels)
    capped_levels["delivery"] = cap_delivery_level(levels.get("delivery"), wpm_rate)
    points = {key: LEVEL_POINTS[clamp_level(capped_levels.get(key))] for key in RUBRIC_KEYS}
    wpm = wpm_points(int(words_counted or 0), score_config)
    if not on_topic:
        wpm = round(wpm * float(score_config.get("off_topic_multiplier") or 1), 4)
    total = sum(float(weights.get(key, 1)) * points[key] for key in RUBRIC_KEYS) + wpm
    return {
        "points": points,
        "wpm_points": wpm,
        "total": round(total, 4),
        "config_version": score_config.get("version"),
        "wpm": wpm_rate,
        "delivery_cap": delivery_cap(wpm_rate),
    }
