"""観戦用スクリプトのサーバー TTS。

ソロ練習の debate/tts.py とは別経路。声・保存先・呼び出し元を共有しない。
"""
from __future__ import annotations

import logging
import os
import time

from debate.config import (
    WATCH_GOV_VOICE,
    WATCH_OPP_VOICE,
    WATCH_SPEECH_INSTRUCTIONS,
    WATCH_SPEECH_MAX_INPUT_CHARS,
    WATCH_SPEECH_MAX_RETRIES,
    WATCH_SPEECH_MODEL,
    WATCH_SPEECH_TIMEOUT_SEC,
)
from debate.speech_pricing import cost_from_usage, estimate_cost_usd

logger = logging.getLogger(__name__)

GOV_VOICE = WATCH_GOV_VOICE
OPP_VOICE = WATCH_OPP_VOICE


def voice_for_side(side: str) -> str:
    return OPP_VOICE if side == "Opp" else GOV_VOICE


def split_for_speech(text: str, limit: int = WATCH_SPEECH_MAX_INPUT_CHARS) -> list[str]:
    """API の入力上限を超えるときは文末で分割する。"""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []
    if len(cleaned) <= limit:
        return [cleaned]

    sentences = _split_sentences(cleaned)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        piece = sentence.strip()
        if not piece:
            continue
        if len(piece) > limit:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(piece), limit):
                chunks.append(piece[start : start + limit])
            continue
        candidate = f"{current} {piece}".strip() if current else piece
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def _split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for char in text:
        buf.append(char)
        if char in ".!?":
            parts.append("".join(buf).strip())
            buf = []
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return [part for part in parts if part]


def _get_client():
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAI(
        api_key=api_key,
        timeout=WATCH_SPEECH_TIMEOUT_SEC,
        max_retries=WATCH_SPEECH_MAX_RETRIES,
    )


def _usage_cost(response, text: str) -> float:
    usage = getattr(response, "usage", None)
    if usage is None:
        return estimate_cost_usd(text)
    input_tokens = int(getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0)
    if input_tokens <= 0 and output_tokens <= 0:
        return estimate_cost_usd(text)
    return cost_from_usage(input_tokens, output_tokens)


def _synthesize_chunk(client, text: str, voice: str) -> tuple[bytes, float]:
    kwargs = {
        "model": WATCH_SPEECH_MODEL,
        "voice": voice,
        "input": text,
        "response_format": "mp3",
        "instructions": WATCH_SPEECH_INSTRUCTIONS,
    }
    try:
        response = client.audio.speech.create(**kwargs)
    except TypeError:
        kwargs.pop("instructions", None)
        response = client.audio.speech.create(**kwargs)
    except Exception:
        if "instructions" not in kwargs:
            raise
        kwargs.pop("instructions", None)
        response = client.audio.speech.create(**kwargs)
    return response.content, _usage_cost(response, text)


def synthesize_watch_speech(text: str, side: str) -> tuple[bytes, float]:
    """陣営ごとの声で MP3 バイト列と概算費用を返す。"""
    client = _get_client()
    if not client:
        raise RuntimeError("OPENAI_API_KEYが設定されていないため、音声を生成できません。")
    chunks = split_for_speech(text)
    if not chunks:
        raise ValueError("読み上げるテキストが空です。")
    voice = voice_for_side(side)
    audio_parts: list[bytes] = []
    cost = 0.0
    for index, chunk in enumerate(chunks):
        started = time.monotonic()
        audio, chunk_cost = _synthesize_chunk(client, chunk, voice)
        audio_parts.append(audio)
        cost += chunk_cost
        logger.info(
            "Watch speech chunk %s/%s finished in %.1fs (voice=%s chars=%s)",
            index + 1,
            len(chunks),
            time.monotonic() - started,
            voice,
            len(chunk),
        )
    return b"".join(audio_parts), round(cost, 6)
