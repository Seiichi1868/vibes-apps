"""英語ニューススクリプトを日本語に翻訳する。"""
from __future__ import annotations

import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from news_app.config import DEFAULT_AI_MODEL
from news_app.services.openai_utils import (
    PREMIUM_MAX_COMPLETION_TOKENS,
    is_reasoning_chat_model,
    reasoning_effort_for_model,
)

TRANSLATION_MODEL = DEFAULT_AI_MODEL
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
TRANSLATE_TIMEOUT_SEC = 90

_SYSTEM_PROMPT = """\
あなたは、日本の高校の英語授業向けにニュース原稿を訳す翻訳者です。
与えられた英語スクリプトを、意味が正確で自然な日本語に翻訳してください。

ルール:
- 前置き・解説・注釈・見出しは付けない。翻訳本文だけを返す。
- 原文の段落・改行の区切りはできるだけ保つ。
- ニュースとして自然な日本語にする（直訳調にしない）。
- 固有名詞は、一般的な日本語表記があればそれを使い、なければ英語のまま残す。
- 数字・日付・肩書は原文の情報を落とさない。
"""


def _build_user_prompt(script: str) -> str:
    return f"""\
次の英語ニューススクリプトを日本語に翻訳してください。翻訳本文だけを返してください。

--- English script ---
{script}
--- End ---
"""


def _extract_message_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
        return "".join(parts).strip()
    return str(content or "").strip()


def _create_chat_completion(*, api_key: str, model: str, script: str) -> dict:
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(script)},
        ],
    }
    if is_reasoning_chat_model(model):
        payload["max_completion_tokens"] = PREMIUM_MAX_COMPLETION_TOKENS
        effort = reasoning_effort_for_model(model)
        if effort:
            payload["reasoning_effort"] = effort
    else:
        payload["temperature"] = 0.2

    request = Request(
        OPENAI_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(request, timeout=TRANSLATE_TIMEOUT_SEC, context=ssl_context) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API エラー ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"OpenAI API に接続できませんでした: {exc.reason}") from exc

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("AI からの応答形式が不正です。")
    return data


def translate_script_to_japanese(
    script: str,
    *,
    api_key: str,
    model: str = TRANSLATION_MODEL,
) -> str:
    """英語スクリプトを日本語訳して返す。"""
    script = str(script or "").strip()
    if not script:
        raise ValueError("スクリプトが空です。和訳するには英語スクリプトが必要です。")
    if not api_key:
        raise ValueError(
            "OpenAI API キーが未設定です。"
            "管理画面（/news/admin/）の「OpenAI API キー」欄にキーを入力して保存してください。"
        )

    payload = _create_chat_completion(api_key=api_key, model=model, script=script)
    translation = _extract_message_text(payload)
    if not translation:
        finish_reason = ""
        choices = payload.get("choices") or []
        if choices and isinstance(choices[0], dict):
            finish_reason = str(choices[0].get("finish_reason") or "")
        raise ValueError(f"AI が有効な和訳を返しませんでした (finish_reason={finish_reason or 'unknown'})")
    return translation
