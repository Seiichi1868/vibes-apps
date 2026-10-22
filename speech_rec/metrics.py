"""単語タイムスタンプから語数と間を数える。副作用なし。"""
from __future__ import annotations

import re

FILLERS = {"um", "uh", "er", "erm", "hmm", "mm", "ah"}
_EDGE = re.compile(r"^[^a-z0-9']+|[^a-z0-9']+$")


def normalize_word(word: str) -> str:
    text = str(word or "").lower().strip()
    return _EDGE.sub("", text)


def wpm_points(words_counted: int, score_config: dict) -> float:
    cap = score_config.get("wpm_cap")
    counted = words_counted if cap is None else min(words_counted, int(cap))
    return round(max(0, counted) * float(score_config.get("w_wpm") or 0), 4)


def measure(words: list, *, speak_sec: float, grace_sec: float, pause_gap_sec: float, exclude_fillers: bool) -> dict:
    """words は (語, start秒, end秒)。間の窓は speak_sec。語数は speak_sec+grace までに始まった語。"""
    window = max(0.0, float(speak_sec))
    count_until = window + max(0.0, float(grace_sec))
    cleaned = []
    for item in words:
        token = normalize_word(item[0])
        if not token:
            continue
        start = float(item[1])
        end = float(item[2])
        if end < start:
            end = start
        cleaned.append((token, start, end))

    counted_rows = [row for row in cleaned if 0 <= row[1] < count_until]
    fillers = sum(1 for token, _, _ in counted_rows if token in FILLERS)
    words_all = len(counted_rows)
    words_counted = words_all - fillers if exclude_fillers else words_all

    speech = sorted((row for row in cleaned if 0 <= row[1] <= window), key=lambda row: row[1])
    gaps = []
    for prev, nxt in zip(speech, speech[1:]):
        gap = nxt[1] - prev[2]
        if gap > 0:
            gaps.append(gap)
    if speech:
        tail = window - speech[-1][2]
        if tail > 0:
            gaps.append(tail)
    elif window > 0:
        gaps.append(window)

    long_gaps = [gap for gap in gaps if gap >= float(pause_gap_sec)]
    silent = sum(gap for gap in gaps if gap >= 0.5)
    return {
        "window_sec": window,
        "words_all": words_all,
        "nonlexical_fillers": fillers,
        "words_counted": words_counted,
        "pause_n": len(long_gaps),
        "pause_max": round(max(gaps) if gaps else 0.0, 4),
        "silent_ratio": round((silent / window) if window else 0.0, 4),
    }
