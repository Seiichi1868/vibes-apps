"""Whisper と Chat。429 は待って再試行する。キーはログに出さない。"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from speech_rec.config import openai_api_key
from speech_rec.pricing import WHISPER_MODEL

logger = logging.getLogger(__name__)


class SpeechRecAIError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _client():
    key = openai_api_key()
    if not key:
        raise SpeechRecAIError("no_api_key")
    from openai import OpenAI

    return OpenAI(api_key=key, timeout=45, max_retries=0)


def _status(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _call(fn, *, retries: int = 2, sleeper=time.sleep):
    """429 のとき 1秒、2秒待って再試行。キー文字列は例外メッセージに残さない。"""
    delay = 1.0
    last = "request_failed"
    for attempt in range(retries + 1):
        try:
            return fn()
        except SpeechRecAIError:
            raise
        except Exception as exc:  # noqa: BLE001 — SDK 例外をコードだけに潰す
            status = _status(exc)
            timed_out = "Timeout" in type(exc).__name__
            last = "timeout" if timed_out else ("rate_limited" if status == 429 else "request_failed")
            logger.warning("speech_rec openai failed status=%s attempt=%s", status, attempt + 1)
            if timed_out:
                raise SpeechRecAIError("timeout") from None
            if status == 429 and attempt < retries:
                sleeper(delay)
                delay *= 2
                continue
            raise SpeechRecAIError(last) from None
    raise SpeechRecAIError(last)


def transcribe_words(path: Path, *, language: str = "en", prompt: str = ""):
    """verbose_json の単語時刻。後続 PR の文字起こしから呼ぶ。"""

    def run():
        client = _client()
        with path.open("rb") as audio:
            kwargs = {
                "model": WHISPER_MODEL,
                "file": audio,
                "language": language,
                "response_format": "verbose_json",
                "timestamp_granularities": ["word"],
            }
            if prompt:
                kwargs["prompt"] = prompt
            return client.audio.transcriptions.create(**kwargs)

    return _call(run, retries=1)


def chat_json(model: str, system: str, user: str, *, max_tokens: int = 1200):
    def run():
        client = _client()
        return client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

    result = _call(run, retries=1)
    content = ""
    usage = {"input_tokens": 0, "output_tokens": 0}
    try:
        content = result.choices[0].message.content or ""
        if result.usage:
            usage["input_tokens"] = int(result.usage.prompt_tokens or 0)
            usage["output_tokens"] = int(result.usage.completion_tokens or 0)
    except (AttributeError, IndexError, TypeError):
        raise SpeechRecAIError("empty_response") from None
    return content, usage
