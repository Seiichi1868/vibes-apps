"""CNN10 タイトルと文字起こしの対応区間を推定する。"""

from __future__ import annotations

import json
import re

from toolbox.config import GENERATE_TIMEOUT_SEC, get_openai_api_key
from toolbox.openai_http import chat_completions


def seconds_to_display(sec: int) -> str:
    sec = int(sec or 0)
    if sec <= 0:
        return "0:00"
    return f"{sec // 60:02d}:{sec % 60:02d}"

_TITLE_DATE_SUFFIX_RE = re.compile(r"\s*\|\s*[A-Za-z]+\s+\d{1,2},?\s+\d{4}\s*$")
_TITLE_DATE_PREFIX_RE = re.compile(
    r"^\s*(?:CNN\s*10|CNN10)?\s*[-|:]*\s*[A-Za-z]+\s+\d{1,2},?\s+\d{4}\s*$",
    re.IGNORECASE,
)
_STOP_WORDS = {
    "about",
    "after",
    "been",
    "before",
    "cnn",
    "daily",
    "from",
    "have",
    "into",
    "more",
    "news",
    "over",
    "show",
    "than",
    "that",
    "their",
    "them",
    "then",
    "they",
    "this",
    "today",
    "were",
    "what",
    "when",
    "will",
    "with",
    "your",
}
INTRO_SKIP_SEC = 35
DEFAULT_STORY_SEC = 150
END_PAD_SEC = 3
MIN_STORY_SEC = 40
MAX_STORY_RATIO = 0.55


def _clean_title(title: str) -> str:
    cleaned = _TITLE_DATE_SUFFIX_RE.sub("", str(title or "").strip()).strip()
    return cleaned or str(title or "").strip()


def _format_snippet_time(sec: float) -> str:
    return seconds_to_display(max(0, int(sec))) or "0:00"


def _build_timed_transcript(snippets: list[dict]) -> str:
    lines = []
    for snippet in snippets:
        text = str(snippet.get("text") or "").strip()
        if not text:
            continue
        start = float(snippet.get("start") or 0)
        lines.append(f"{_format_snippet_time(start)}  {text}")
    return "\n".join(lines)


def _video_duration_sec(snippets: list[dict]) -> int:
    duration = 0
    for snippet in snippets:
        start = float(snippet.get("start") or 0)
        end = start + float(snippet.get("duration") or 0)
        duration = max(duration, int(end))
    return duration


def _title_keywords(title: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9']+", _clean_title(title))
    keys = []
    for word in words:
        low = word.lower()
        if len(low) < 4 or low in _STOP_WORDS:
            continue
        keys.append(low)
    return keys


def _title_is_generic(title: str) -> bool:
    cleaned = _clean_title(title)
    if _TITLE_DATE_PREFIX_RE.match(str(title or "").strip()):
        return True
    if re.fullmatch(r"(?:CNN\s*10|CNN10)?", cleaned, re.IGNORECASE):
        return True
    return len(_title_keywords(cleaned)) < 2


def _guess_segment_heuristic(snippets: list[dict], title: str) -> tuple[int, int] | None:
    duration = _video_duration_sec(snippets)
    if duration <= 0:
        return None

    if _title_is_generic(title):
        start = min(INTRO_SKIP_SEC, max(0, duration // 8))
        end = min(duration, start + DEFAULT_STORY_SEC + END_PAD_SEC)
        if end - start < MIN_STORY_SEC:
            return None
        return start, end

    keywords = _title_keywords(title)
    if not keywords:
        return None

    mentions: list[float] = []
    for snippet in snippets:
        text = str(snippet.get("text") or "").lower()
        start = float(snippet.get("start") or 0)
        if any(key in text for key in keywords):
            mentions.append(start)
    if not mentions:
        return None

    body_mentions = [sec for sec in mentions if sec >= INTRO_SKIP_SEC]
    seed = body_mentions[0] if body_mentions else mentions[0]
    later = [sec for sec in mentions if sec >= seed + 45]
    if seed < INTRO_SKIP_SEC and later:
        seed = later[0]

    start = max(0, int(seed) - 8)
    window = [sec for sec in mentions if start <= sec <= start + 210]
    last = window[-1] if window else start + DEFAULT_STORY_SEC
    end = min(duration, int(last) + END_PAD_SEC)
    if end - start < MIN_STORY_SEC:
        end = min(duration, start + DEFAULT_STORY_SEC)
    if end - start > duration * MAX_STORY_RATIO:
        end = min(duration, start + DEFAULT_STORY_SEC + END_PAD_SEC)
    if end - start < MIN_STORY_SEC:
        return None
    return start, end


def _ranges_overlap(start: int, end: int, other_start: int, other_end: int) -> bool:
    return min(end, other_end) - max(start, other_start) > 20


def _avoid_ranges(raw) -> list[tuple[int, int]]:
    ranges = []
    if not isinstance(raw, list):
        return ranges
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            start = int(item.get("start_sec"))
            end = int(item.get("end_sec"))
        except (TypeError, ValueError):
            continue
        if end > start:
            ranges.append((start, end))
    return ranges


def _overlaps_any(start: int, end: int, avoided: list[tuple[int, int]]) -> bool:
    return any(_ranges_overlap(start, end, other_start, other_end) for other_start, other_end in avoided)


def _next_keyword_window(snippets: list[dict], title: str, avoided: list[tuple[int, int]], duration: int) -> tuple[int, int] | None:
    keywords = _title_keywords(title)
    if not keywords or duration <= 0:
        return None
    mentions = []
    for snippet in snippets:
        text = str(snippet.get("text") or "").lower()
        start = float(snippet.get("start") or 0)
        if any(key in text for key in keywords):
            mentions.append(start)
    for seed in mentions:
        start = max(0, int(seed) - 8)
        end = min(duration, start + DEFAULT_STORY_SEC)
        if _overlaps_any(start, end, avoided):
            continue
        return _clamp_and_pad(start, end, duration, pad=0)
    return None


def _looks_like_full_video(start_sec: int, end_sec: int, duration: int) -> bool:
    if duration <= 0 or end_sec <= start_sec:
        return True
    span = end_sec - start_sec
    if span >= duration * MAX_STORY_RATIO:
        return True
    if start_sec <= 5 and end_sec >= duration - 8:
        return True
    return False


def _clamp_and_pad(start_sec: int, end_sec: int, duration: int, pad: int = END_PAD_SEC) -> tuple[int, int]:
    start_sec = max(0, min(start_sec, max(0, duration - MIN_STORY_SEC)))
    end_sec = max(0, min(end_sec, duration))
    if pad and end_sec < duration:
        end_sec = min(duration, end_sec + pad)
    if end_sec - start_sec < MIN_STORY_SEC:
        end_sec = min(duration, start_sec + MIN_STORY_SEC)
    return start_sec, end_sec


def _parse_model_json(data: dict) -> dict:
    content = str(data["choices"][0]["message"]["content"] or "").strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("AI の応答を読み取れませんでした。")
    return payload


def find_title_segment_in_transcript(
    title: str,
    snippets: list[dict],
    *,
    model: str,
    api_key: str,
    avoid: list | None = None,
) -> dict:
    """動画タイトルに対応するニュース区間の開始・終了秒を推定する。"""
    clean_title = _clean_title(title)
    if not clean_title:
        raise ValueError("動画タイトルがありません。")
    if not snippets:
        raise ValueError("文字起こしが空です。")

    transcript_text = _build_timed_transcript(snippets)
    if not transcript_text.strip():
        raise ValueError("文字起こしが空です。")

    duration = _video_duration_sec(snippets)
    avoided = _avoid_ranges(avoid)
    guessed = _guess_segment_heuristic(snippets, title)
    if guessed and _overlaps_any(guessed[0], guessed[1], avoided):
        guessed = _next_keyword_window(snippets, title, avoided, duration)
    hint = ""
    if guessed:
        hint = (
            f"A keyword-based guess is {guessed[0]}-{guessed[1]} seconds. "
            "Refine this range. Do not expand it to the whole episode."
        )
    avoid_note = ""
    if avoided:
        listed = ", ".join(f"{start}-{end} seconds" for start, end in avoided)
        avoid_note = (
            "These earlier ranges were listened to and do NOT match the title: "
            f"{listed}. Return a different story. Do not overlap those ranges."
        )
    generic_note = ""
    if _title_is_generic(title):
        generic_note = (
            "The title looks like a generic CNN10 episode title (date or show name only). "
            "Return the FIRST full story after the opening headlines, not the entire video."
        )

    if not get_openai_api_key():
        raise ValueError("OpenAI の API キーが設定されていません。")
    reasoning = model.startswith("gpt-5") and "chat" not in model
    messages = [
        {
            "role": "system",
            "content": (
                "You analyze CNN 10 transcripts. Each episode has an opening/headlines "
                "segment, then several standalone stories of about 90-180 seconds, "
                "sometimes ending with trivia.\n"
                "Find the ONE story that matches the given English title.\n"
                "Rules:\n"
                "- Ignore brief teaser mentions in the first 30-90 seconds unless the full story starts there.\n"
                "- start_sec: when the host begins covering this story in depth.\n"
                "- end_sec: when this story ends, plus at most 3 seconds into the next story or transition "
                "so the last line is not cut. Do NOT include the next story's content.\n"
                "- A valid story is usually 60-240 seconds. NEVER return almost the entire episode.\n"
                "- If earlier ranges are listed as wrong, choose a different story.\n"
                "- Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Video title: {clean_title}\n"
                f"Episode duration: {duration} seconds\n"
                f"{generic_note}\n"
                f"{avoid_note}\n"
                f"{hint}\n\n"
                f"Transcript (timestamp at line start in M:SS format):\n{transcript_text}\n\n"
                "Return JSON with:\n"
                '- "start_sec": integer seconds where this story begins in depth\n'
                '- "end_sec": integer seconds at this story\'s end, overlapping the next story by 3 seconds at most\n'
                '- "confidence": "high", "medium", or "low"\n'
                '- "note": one short English sentence explaining the match'
            ),
        },
    ]
    data = chat_completions(
        model=model,
        messages=messages,
        temperature=None if reasoning else 0.1,
        timeout=max(GENERATE_TIMEOUT_SEC, 60),
        reasoning=reasoning,
        max_tokens=400,
    )
    payload = _parse_model_json(data)

    start_sec = int(payload.get("start_sec", 0) or 0)
    end_sec = int(payload.get("end_sec", 0) or 0)
    confidence = str(payload.get("confidence") or "medium").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    note = str(payload.get("note") or "").strip()

    start_sec, end_sec = _clamp_and_pad(start_sec, end_sec, duration, pad=END_PAD_SEC)
    if avoided and _overlaps_any(start_sec, end_sec, avoided):
        alternative = _next_keyword_window(snippets, title, avoided, duration)
        if alternative is None and avoided:
            last_end = max(end for _, end in avoided)
            alternative = _clamp_and_pad(last_end + 5, last_end + 5 + DEFAULT_STORY_SEC, duration, pad=0)
            if _overlaps_any(alternative[0], alternative[1], avoided):
                alternative = None
        if alternative:
            start_sec, end_sec = alternative
            confidence = "low"
            note = "Retried away from a range that did not match the title."
    if _looks_like_full_video(start_sec, end_sec, duration):
        if guessed:
            start_sec, end_sec = _clamp_and_pad(guessed[0], guessed[1], duration, pad=0)
            confidence = "low"
            note = note or "Used a keyword-based range because the model returned almost the whole video."
        else:
            raise ValueError("このタイトルに対応する明確な区間を特定できませんでした。スライダーで手動調整してください。")

    if end_sec <= start_sec:
        raise ValueError("AI が有効な時間範囲を返しませんでした。手動で開始・終了時間を設定してください。")

    return {
        "ok": True,
        "title": clean_title,
        "start_sec": start_sec,
        "end_sec": end_sec,
        "start_display": seconds_to_display(start_sec),
        "end_display": seconds_to_display(end_sec),
        "confidence": confidence,
        "note": note,
    }
