"""流暢さだけをルールで採点する。発音は見ない。閾値は設定から受け取る。"""
from __future__ import annotations

SOURCE = "rules-v2"

_LABELS = {
    "pause_n": "文の途中で止まる回数",
    "pause_max": "長く止まる場面",
    "silent_ratio": "止まっている時間",
}
_HINTS = {
    "pause_n": "文の途中で止まる回数を減らそう",
    "pause_max": "長く止まる場面を減らそう",
    "silent_ratio": "止まっている時間を短くしよう",
}


def _metric_level(value: float, rules: list[dict], key: str, strict_less: bool) -> int:
    ordered = sorted(rules, key=lambda row: int(row["level"]), reverse=True)
    for row in ordered:
        limit = float(row[key])
        if strict_less:
            if value < limit:
                return int(row["level"])
        elif value <= limit:
            return int(row["level"])
    return 1


def delivery_levels(metrics: dict, rules: list[dict]) -> dict[str, int]:
    return {
        "pause_n": _metric_level(float(metrics.get("pause_n") or 0), rules, "pause_n", False),
        "pause_max": _metric_level(float(metrics.get("pause_max") or 0), rules, "pause_max", True),
        "silent_ratio": _metric_level(float(metrics.get("silent_ratio") or 0), rules, "silent_ratio", True),
    }


def delivery_level(metrics: dict, rules: list[dict]) -> int:
    """3指標のうち最も低いレベル。"""
    return min(delivery_levels(metrics, rules).values())


def delivery_reason(metrics: dict, rules: list[dict], level: int, *, noisy: bool = False) -> dict:
    """表示用の文章。永続記録には書かない。"""
    parts = delivery_levels(metrics, rules)
    limiting = min(parts, key=parts.get)
    pause_n = int(metrics.get("pause_n") or 0)
    pause_max = float(metrics.get("pause_max") or 0)
    silent = round(float(metrics.get("silent_ratio") or 0) * 100)
    if int(level) >= 6:
        text = "ほとんど止まらず自然に話せていました。"
    else:
        text = (
            f"文の途中で0.8秒以上止まった回数が{pause_n}回、"
            f"いちばん長い止まりは{pause_max:g}秒、"
            f"話している間に止まっていた時間は{silent}％でした。"
            f"一番低い指標は『{_LABELS[limiting]}』です。"
        )
    if noisy:
        text += "周りの音が大きいため参考値です。"
    return {
        "limiting": limiting,
        "text": text,
        "hints": dict(_HINTS),
        "hint": _HINTS[limiting],
    }
