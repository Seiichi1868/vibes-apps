"""CNN10 タイトルと文字起こしの対応区間を推定する。"""

from __future__ import annotations

import re

from openai import OpenAI

from news_app.services.openai_utils import create_json_chat_completion
from news_app.services.youtube import seconds_to_display

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


def find_title_segment_in_transcript(
    title: str,
    snippets: list[dict],
    *,
    model: str,
    api_key: str,
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
    guessed = _guess_segment_heuristic(snippets, title)
    hint = ""
    if guessed:
        hint = (
            f"A keyword-based guess is {guessed[0]}-{guessed[1]} seconds. "
            "Refine this range. Do not expand it to the whole episode."
        )
    generic_note = ""
    if _title_is_generic(title):
        generic_note = (
            "The title looks like a generic CNN10 episode title (date or show name only). "
            "Return the FIRST full story after the opening headlines, not the entire video."
        )

    client = OpenAI(api_key=api_key, timeout=60.0)
    payload = create_json_chat_completion(
        client,
        model,
        [
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
                    "- Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Video title: {clean_title}\n"
                    f"Episode duration: {duration} seconds\n"
                    f"{generic_note}\n"
                    f"{hint}\n\n"
                    f"Transcript (timestamp at line start in M:SS format):\n{transcript_text}\n\n"
                    "Return JSON with:\n"
                    '- "start_sec": integer seconds where this story begins in depth\n'
                    '- "end_sec": integer seconds at this story\'s end, overlapping the next story by 3 seconds at most\n'
                    '- "confidence": "high", "medium", or "low"\n'
                    '- "note": one short English sentence explaining the match'
                ),
            },
        ],
        temperature=0.1,
    )

    start_sec = int(payload.get("start_sec", 0) or 0)
    end_sec = int(payload.get("end_sec", 0) or 0)
    confidence = str(payload.get("confidence") or "medium").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    note = str(payload.get("note") or "").strip()

    start_sec, end_sec = _clamp_and_pad(start_sec, end_sec, duration, pad=END_PAD_SEC)
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
