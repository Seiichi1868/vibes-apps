"""Solo Practice のサーバー側 TTS。ブラウザ speechSynthesis は使わない。"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from debate.config import (
    AUDIO_DIR,
    TTS_FORMAT,
    TTS_INSTRUCTIONS,
    TTS_MAX_INPUT_CHARS,
    TTS_MAX_RETRIES,
    TTS_MODEL,
    TTS_TIMEOUT_SEC,
    TTS_VOICE,
    ensure_dirs,
)
from debate.solo import tts_filename

logger = logging.getLogger(__name__)


def _get_client():
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAI(api_key=api_key, timeout=TTS_TIMEOUT_SEC, max_retries=TTS_MAX_RETRIES)


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [block.strip() for block in (text or "").split("\n") if block.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= TTS_MAX_INPUT_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= TTS_MAX_INPUT_CHARS:
            current = paragraph
            continue
        # 段落が上限を超える場合のみ文単位で切る（文の途中では切らない）
        sentences = _split_sentences(paragraph)
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= TTS_MAX_INPUT_CHARS:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = sentence[:TTS_MAX_INPUT_CHARS]
        if current:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


def _split_sentences(text: str) -> list[str]:
    parts = []
    buf = []
    for char in text:
        buf.append(char)
        if char in ".!?":
            parts.append("".join(buf).strip())
            buf = []
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def _synthesize_chunk(client, text: str) -> bytes:
    kwargs = {
        "model": TTS_MODEL,
        "voice": TTS_VOICE,
        "input": text,
        "response_format": TTS_FORMAT,
    }
    try:
        if TTS_INSTRUCTIONS and "tts-1" not in TTS_MODEL:
            kwargs["instructions"] = TTS_INSTRUCTIONS
            response = client.audio.speech.create(**kwargs)
        else:
            response = client.audio.speech.create(**kwargs)
    except TypeError:
        kwargs.pop("instructions", None)
        response = client.audio.speech.create(**kwargs)
    except Exception:
        if "instructions" in kwargs:
            kwargs.pop("instructions", None)
            response = client.audio.speech.create(**kwargs)
        else:
            raise
    return response.content


def synthesize_speech(text: str) -> bytes:
    """プレーン英語を MP3 バイト列にする。段落単位で分割して連結する。"""
    client = _get_client()
    if not client:
        raise RuntimeError("OPENAI_API_KEYが設定されていないため、音声を生成できません。")

    chunks = _split_paragraphs(text)
    if not chunks:
        raise ValueError("読み上げるテキストが空です。")

    audio_parts: list[bytes] = []
    for index, chunk in enumerate(chunks):
        started = time.monotonic()
        audio_parts.append(_synthesize_chunk(client, chunk))
        logger.info(
            "TTS chunk %s/%s finished in %.1fs (model=%s chars=%s)",
            index + 1,
            len(chunks),
            time.monotonic() - started,
            TTS_MODEL,
            len(chunk),
        )
    return b"".join(audio_parts)


def save_part_tts(session_id: str, part: str, audio_bytes: bytes) -> str:
    ensure_dirs()
    session_dir = AUDIO_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    filename = tts_filename(part)
    path = session_dir / filename
    path.write_bytes(audio_bytes)
    return filename


def tts_path(session_id: str, filename: str) -> Path | None:
    if not filename:
        return None
    path = AUDIO_DIR / session_id / Path(filename).name
    return path if path.is_file() else None
