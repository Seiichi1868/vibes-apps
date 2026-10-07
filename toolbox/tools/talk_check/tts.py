"""理解度チェックの問題文を OpenAI TTS で読む。同じ文はキャッシュする。"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request

from toolbox.config import DATA_DIR, get_openai_api_key
from toolbox.openai_http import OpenAIHttpError, _ssl_context

TTS_MODEL = "tts-1"
TTS_VOICE = "nova"
# tts-1 の公表単価（$/1000文字）
TTS_COST_PER_1K = 0.015
CACHE_DIR = DATA_DIR / "talk_tts"


def cache_path(text: str):
    digest = hashlib.sha256(f"{TTS_MODEL}\n{TTS_VOICE}\n{text}".encode("utf-8")).hexdigest()[:32]
    return CACHE_DIR / f"{digest}.mp3"


def synthesize(text: str) -> tuple[bytes, bool]:
    """(mp3 bytes, was_cached)。新規生成時だけ API を呼ぶ。"""
    content = str(text or "").strip()
    if not content:
        raise OpenAIHttpError("読み上げる文がありません。")
    if len(content) > 600:
        content = content[:600]

    path = cache_path(content)
    if path.is_file() and path.stat().st_size > 0:
        return path.read_bytes(), True

    api_key = get_openai_api_key()
    if not api_key:
        raise OpenAIHttpError("OpenAI の API キーが設定されていません。管理者に連絡してください。")

    payload = {
        "model": TTS_MODEL,
        "voice": TTS_VOICE,
        "input": content,
        "response_format": "mp3",
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OpenAIHttpError(f"音声の生成に失敗しました（HTTP {exc.code}）。") from exc
    except urllib.error.URLError as exc:
        raise OpenAIHttpError(f"OpenAI に接続できません: {exc.reason}") from exc

    if not audio:
        raise OpenAIHttpError("音声データが空でした。")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return audio, False


def estimate_cost_usd(text: str) -> float:
    chars = len(str(text or "").strip()[:600])
    return round((chars / 1000.0) * TTS_COST_PER_1K, 6)
