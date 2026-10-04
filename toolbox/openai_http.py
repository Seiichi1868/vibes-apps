"""OpenAI を HTTPS で呼ぶ（SDK の chat モジュールに依存しない）。"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

from toolbox.config import get_openai_api_key


def _ssl_context():
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


class OpenAIHttpError(Exception):
    pass


def chat_completions(
    *,
    model: str,
    messages: list[dict],
    temperature: float | None,
    timeout: float,
    reasoning: bool = False,
) -> dict:
    api_key = get_openai_api_key()
    if not api_key:
        raise OpenAIHttpError("OpenAI の API キーが設定されていません。管理者に連絡してください。")
    payload: dict = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    if reasoning:
        payload["max_completion_tokens"] = 4096
        payload["reasoning_effort"] = "none"
    elif temperature is not None:
        payload["temperature"] = temperature
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OpenAIHttpError(f"OpenAI HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise OpenAIHttpError(f"OpenAI に接続できません: {exc.reason}") from exc
