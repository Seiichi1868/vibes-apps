"""単語タイムスタンプから語数と間を数える。副作用なし。"""
from __future__ import annotations

import re

FILLERS = {"um", "uh", "er", "erm", "hmm", "mm", "ah"}
_EDGE = re.compile(r"^[^a-z0-9']+|[^a-z0-9']+$")
_PIECE = re.compile(r"[A-Za-z0-9']+[.?!,;:]?")
_SPLIT = re.compile(r"^([A-Za-z0-9']+)([.?!,;:])?$")
SENTENCE_MARKS = {".", "?", "!"}
CLAUSE_MARKS = {",", ";", ":"}


def normalize_word(word: str) -> str:
    text = str(word or "").lower().strip()
    return _EDGE.sub("", text)


def wpm_points(words_counted: int, score_config: dict) -> float:
    cap = score_config.get("wpm_cap")
    counted = words_counted if cap is None else min(words_counted, int(cap))
    return round(max(0, counted) * float(score_config.get("w_wpm") or 0), 4)


def align_boundaries(text: str, words: list) -> tuple[list, str]:
    """句読点つき text と words を先頭から突き合わせる。失敗が5%を超えたら unaligned。"""
    marks = []
    for piece in _PIECE.findall(text or ""):
        matched = _SPLIT.match(piece)
        if not matched:
            continue
        token = normalize_word(matched.group(1))
        if token:
            marks.append((token, matched.group(2) or ""))
    rows = []
    index = 0
    misses = 0
    usable = 0
    for item in words:
        token = normalize_word(item[0])
        if not token:
            continue
        start = float(item[1])
        end = float(item[2])
        if end < start:
            end = start
        usable += 1
        mark = ""
        if index < len(marks) and marks[index][0] == token:
            mark = marks[index][1]
            index += 1
        else:
            misses += 1
        rows.append((token, start, end, mark))
    info = "aligned" if usable and (misses / usable) <= 0.05 else "unaligned"
    if info == "unaligned":
        rows = [(token, start, end, "") for token, start, end, _mark in rows]
    return rows, info


def _hesitation(gap: float, mark: str, *, aligned: bool, sentence_gap_min: float, clause_gap_min: float, mid_gap_min: float, unknown_gap_min: float) -> bool:
    if not aligned:
        return gap >= unknown_gap_min
    if mark in SENTENCE_MARKS:
        return gap >= sentence_gap_min
    if mark in CLAUSE_MARKS:
        return gap >= clause_gap_min
    return gap >= mid_gap_min


def measure(
    words: list,
    *,
    speak_sec: float,
    grace_sec: float,
    pause_gap_sec: float,
    exclude_fillers: bool,
    text: str = "",
    sentence_gap_min: float = 2.0,
    clause_gap_min: float = 1.2,
    mid_gap_min: float = 0.5,
    unknown_gap_min: float = 1.0,
) -> dict:
    """words は (語, start秒, end秒)。語数は speak_sec+grace までに始まった語。

    間は最初の語から最後の語まで。文末のあとの無音（tail）は数えない。
    """
    window = max(0.0, float(speak_sec))
    count_until = window + max(0.0, float(grace_sec))
    aligned_rows, boundary_info = align_boundaries(text, words)
    counted_rows = [row for row in aligned_rows if 0 <= row[1] < count_until]
    fillers = sum(1 for token, _, _, _ in counted_rows if token in FILLERS)
    words_all = len(counted_rows)
    words_counted = words_all - fillers if exclude_fillers else words_all

    speech = sorted((row for row in aligned_rows if 0 <= row[1] <= window), key=lambda row: row[1])
    aligned = boundary_info == "aligned"
    hesitations = []
    for prev, nxt in zip(speech, speech[1:]):
        gap = nxt[1] - prev[2]
        if gap <= 0:
            continue
        if _hesitation(
            gap,
            prev[3],
            aligned=aligned,
            sentence_gap_min=float(sentence_gap_min),
            clause_gap_min=float(clause_gap_min),
            mid_gap_min=float(mid_gap_min),
            unknown_gap_min=float(unknown_gap_min),
        ):
            hesitations.append(gap)
    span = (speech[-1][2] - speech[0][1]) if speech else 0.0
    long_gaps = [gap for gap in hesitations if gap >= float(pause_gap_sec)]
    return {
        "window_sec": window,
        "words_all": words_all,
        "nonlexical_fillers": fillers,
        "words_counted": words_counted,
        "pause_n": len(long_gaps),
        "pause_max": round(max(hesitations) if hesitations else 0.0, 4),
        "silent_ratio": round((sum(hesitations) / span) if span else 0.0, 4),
        "boundary_info": boundary_info,
        "boundaries": [row[3] for row in speech],
    }
