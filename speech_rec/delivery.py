"""流暢さだけをルールで採点する。発音は見ない。閾値は設定から受け取る。"""
from __future__ import annotations

SOURCE = "rules-v1"


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


def delivery_level(metrics: dict, rules: list[dict]) -> int:
    """3指標のうち最も低いレベル。"""
    pause_n = _metric_level(float(metrics.get("pause_n") or 0), rules, "pause_n", False)
    pause_max = _metric_level(float(metrics.get("pause_max") or 0), rules, "pause_max", True)
    silent = _metric_level(float(metrics.get("silent_ratio") or 0), rules, "silent_ratio", True)
    return min(pause_n, pause_max, silent)
