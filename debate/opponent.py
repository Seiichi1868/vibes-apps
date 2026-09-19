"""Solo Practice の対戦AI発話生成。

ジャッジ（debate/judge.py）とは別系統。プロンプトを流用しない。
責務はセッション状態から指定パートの英語スピーチ本文を返すことのみ。
"""
from __future__ import annotations

import logging
import os
import re
import time

from debate.config import (
    DEFAULT_AI_DIFFICULTY,
    OPPONENT_MAX_RETRIES,
    OPPONENT_TIMEOUT_SEC,
    PART_ORDER,
    PART_ROLES,
    VALID_DIFFICULTIES,
)

logger = logging.getLogger(__name__)

MIN_SPEECH_WORDS = 50

WORD_TARGETS = {
    "PM": (300, 380),
    "LO": (300, 380),
    "MG": (300, 380),
    "MO": (300, 380),
    "LOR": (220, 270),
    "PMR": (220, 270),
}

DIFFICULTY_INSTRUCTIONS = {
    "easy": """Difficulty: easy
Control argument strength only. English must remain grammatically correct and natural.
- Rebuttal coverage: rebut only one of the opponent's main points. Leave the other largely unaddressed.
- Depth: give a claim and a reason. Use almost no concrete examples.
- Defence: after being rebutted, leave at least one of your own points undefended.
- Language: simple vocabulary and shorter sentences. Never add grammar mistakes or awkward phrasing.""",
    "normal": """Difficulty: normal
Control argument strength only. English must remain grammatically correct and natural.
- Rebuttal coverage: rebut both of the opponent's main points.
- Depth: include claim, reason, and a concrete example.
- Defence: reconstruct and defend your main points after they are attacked.
- Language: standard parliamentary debate phrasing.""",
    "hard": """Difficulty: hard
Control argument strength only. English must remain grammatically correct and natural.
- Rebuttal coverage: rebut both of the opponent's main points, and also attack an unstated assumption or missing burden.
- Depth: include claim, reason, concrete example, and explicit comparative weighing (whose harm/impact is larger and why).
- Defence: defend all of your points and point out the weakness of the opponent's replies.
- Language: use debate terms such as comparative weighing and burden of proof naturally. Do not make the English worse.""",
}


SYSTEM_PROMPT = """You are a parliamentary debate speaker in an English practice round for Japanese high school students.

Write only the spoken speech in plain English. Do not include:
- headings, bullet points, speaker labels, or stage directions
- meta comments such as "Here is my speech"
- markdown or quotation wrappers

Keep paragraph breaks so the student can follow which point you are answering.

Hard role constraints:
- Each side has exactly two regular points (Point 1 and Point 2). Never create a third point.
- LOR and PMR must not introduce new points.
- PMR must first rebut Opposition Point 2, then summarise.

Match the assigned part's role exactly.
"""


def _get_client():
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAI(api_key=api_key, timeout=OPPONENT_TIMEOUT_SEC, max_retries=OPPONENT_MAX_RETRIES)


def _is_reasoning_model(model: str) -> bool:
    name = (model or "").strip().lower()
    if name.startswith("gpt-5") and "chat" not in name:
        return True
    return name.startswith(("o1", "o3", "o4"))


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def _clean_speech(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    cleaned = re.sub(r"^(here is (my )?speech:?\s*)", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _extract_text(completion) -> str:
    if not completion.choices:
        return ""
    content = getattr(completion.choices[0].message, "content", None)
    return _clean_speech(content or "")


def build_opponent_input(session: dict, part: str) -> dict:
    from debate.storage import get_part

    user_side = session.get("user_side") or "Gov"
    ai_side = "Opp" if user_side == "Gov" else "Gov"
    difficulty = session.get("ai_difficulty") or DEFAULT_AI_DIFFICULTY
    if difficulty not in VALID_DIFFICULTIES:
        difficulty = DEFAULT_AI_DIFFICULTY

    prior = []
    for name in PART_ORDER:
        if name == part:
            break
        part_data = get_part(session, name) or {}
        prior.append(
            {
                "part": name,
                "side": part_data.get("side"),
                "speaker": part_data.get("speaker") or "human",
                "transcript": str(part_data.get("transcript_edited") or "").strip(),
            }
        )

    low, high = WORD_TARGETS.get(part, (300, 380))
    return {
        "motion": session.get("motion", ""),
        "user_side": user_side,
        "ai_side": ai_side,
        "part": part,
        "part_role": PART_ROLES.get(part, ""),
        "target_words": {"min": low, "max": high},
        "difficulty": difficulty,
        "prior_speeches": prior,
    }


def _user_prompt(payload: dict) -> str:
    difficulty = payload.get("difficulty") or "normal"
    difficulty_block = DIFFICULTY_INSTRUCTIONS.get(difficulty, DIFFICULTY_INSTRUCTIONS["normal"])
    prior_lines = []
    for item in payload.get("prior_speeches") or []:
        transcript = item.get("transcript") or "(no speech yet)"
        prior_lines.append(
            f"[{item.get('part')} / {item.get('side')} / {item.get('speaker')}]\n{transcript}"
        )
    prior_block = "\n\n".join(prior_lines) if prior_lines else "(This is the first speech.)"
    low = payload["target_words"]["min"]
    high = payload["target_words"]["max"]
    return (
        f"Motion: {payload.get('motion')}\n"
        f"You are speaking as {payload.get('ai_side')} in the {payload.get('part')} speech.\n"
        f"The student is {payload.get('user_side')}.\n"
        f"Part role: {payload.get('part_role')}\n"
        f"Target length: {low}-{high} words.\n\n"
        f"{difficulty_block}\n\n"
        f"Confirmed speeches so far, in order:\n{prior_block}\n\n"
        "Write the full speech now."
    )


def generate_speech(session: dict, part: str) -> str:
    """指定パートのAI発話本文を返す。空または50語未満なら1回リトライする。"""
    client = _get_client()
    if not client:
        raise RuntimeError("OPENAI_API_KEYが設定されていないため、相手の発話を生成できません。")

    from debate.settings import resolve_opponent_model

    model = resolve_opponent_model()
    payload = build_opponent_input(session, part)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(payload)},
    ]

    last_text = ""
    last_error = None
    for attempt in range(2):
        kwargs: dict = {"model": model, "messages": messages}
        if not _is_reasoning_model(model):
            kwargs["temperature"] = 0.7
        started = time.monotonic()
        try:
            completion = client.chat.completions.create(**kwargs)
        except Exception as exc:
            elapsed = time.monotonic() - started
            logger.warning(
                "Opponent request failed after %.1fs (model=%s part=%s attempt=%s): %s",
                elapsed,
                model,
                part,
                attempt + 1,
                exc,
            )
            last_error = exc
            continue
        elapsed = time.monotonic() - started
        last_text = _extract_text(completion)
        words = _word_count(last_text)
        logger.info(
            "Opponent finished in %.1fs (model=%s part=%s words=%s attempt=%s)",
            elapsed,
            model,
            part,
            words,
            attempt + 1,
        )
        if words >= MIN_SPEECH_WORDS:
            return last_text
        last_error = ValueError(f"生成文が短すぎます（{words}語）。")

    if last_error:
        raise last_error
    raise ValueError("相手の発話を生成できませんでした。")
