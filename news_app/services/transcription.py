"""Whisper API による英語スピーチの文字起こし（news_app 独自実装）。"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def transcribe_audio(file_path: Path, language: str = "en") -> str:
    from openai import OpenAI

    from news_app.config import WHISPER_MAX_RETRIES, WHISPER_MODEL, WHISPER_TIMEOUT_SEC, get_openai_api_key

    api_key = get_openai_api_key()
    if not api_key:
        raise ValueError(
            "OpenAI API キーが未設定です。"
            "管理画面（/news/admin/）の「OpenAI API キー」欄にキーを入力して保存してください。"
        )

    client = OpenAI(api_key=api_key, timeout=WHISPER_TIMEOUT_SEC, max_retries=WHISPER_MAX_RETRIES)
    kwargs: dict = {
        "model": WHISPER_MODEL,
        "language": language,
        "prompt": "High school student speaking an English summary of a news story.",
    }
    if WHISPER_MODEL == "whisper-1":
        kwargs["temperature"] = 0

    with file_path.open("rb") as audio_file:
        result = client.audio.transcriptions.create(file=audio_file, **kwargs)
    text = (getattr(result, "text", "") or "").strip()
    logger.info("news transcription finished (%s, %d chars)", file_path.name, len(text))
    return text
