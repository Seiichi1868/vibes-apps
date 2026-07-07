"""GTEC Part B 質問読み上げ（OpenAI TTS）。ブラウザ Speech Synthesis に依存しない。"""

import hashlib
import logging
import os
from pathlib import Path

from openai import OpenAI

logger = logging.getLogger(__name__)

TTS_MODEL = "tts-1"
TTS_VOICE = "nova"
CACHE_DIR = Path(__file__).resolve().parent.parent / "static" / "audio" / "gtec"

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _client


def _cache_key(text: str) -> str:
    digest = hashlib.sha256(f"gtec\n{TTS_VOICE}\n{text}".encode("utf-8")).hexdigest()
    return digest[:32]


def synthesize_question(text: str) -> tuple[Path, bool]:
    """MP3 を生成またはキャッシュから返す。(path, was_cached)"""
    content = str(text or "").strip()
    if not content:
        raise ValueError("text is required")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{_cache_key(content)}.mp3"

    if cache_path.is_file():
        return cache_path, True

    speech = _get_client().audio.speech.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=content,
        response_format="mp3",
    )
    cache_path.write_bytes(speech.read())
    logger.info("GTEC TTS cached: %s", cache_path.name)
    return cache_path, False
