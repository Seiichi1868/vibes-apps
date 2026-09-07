"""英語ニューススクリプトを日本語に翻訳する。"""
from __future__ import annotations

import json
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from news_app.config import DEFAULT_AI_MODEL
from news_app.services.openai_utils import (
    PREMIUM_MAX_COMPLETION_TOKENS,
    is_reasoning_chat_model,
    parse_json_object,
    reasoning_effort_for_model,
)

TRANSLATION_MODEL = DEFAULT_AI_MODEL
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
TRANSLATE_TIMEOUT_SEC = 90
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

_SYSTEM_PROMPT = """\
あなたは、日本の高校の英語授業向けにニュース原稿を訳す翻訳者です。
番号付きの英語ユニットを、同じ順番・同じ件数で日本語に翻訳してください。

ルール:
- 前置き・解説・注釈は付けない。
- 出力は JSON オブジェクトのみ。キーは translations。
- translations は文字列配列で、入力ユニットと同じ件数・同じ順番にする。
- 1つの英語ユニットに対して、対応する日本語を1つだけ入れる。
- ニュースとして自然な日本語にする（直訳調にしない）。
- 固有名詞は、一般的な日本語表記があればそれを使い、なければ英語のまま残す。
- 数字・日付・肩書は原文の情報を落とさない。
"""


def split_script_units(script: str) -> list[str]:
    """授業スクリプトを、左右対訳用の英文ユニットに分ける。"""
    text = str(script or "").strip()
    if not text:
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return lines
    parts = [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]
    return parts or [text]


def _build_user_prompt(units: list[str]) -> str:
    numbered = "\n".join(f"{index}. {unit}" for index, unit in enumerate(units, start=1))
    return f"""\
次の英語ユニットを日本語に翻訳してください。
translations 配列は必ず {len(units)} 件にしてください。

形式: {{"translations": ["日本語1", "日本語2"]}}

--- English units ---
{numbered}
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


def _create_chat_completion(*, api_key: str, model: str, messages: list[dict]) -> dict:
    payload: dict = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
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


def _request_translations(*, api_key: str, model: str, units: list[str], extra_note: str = "") -> list[str]:
    user_prompt = _build_user_prompt(units)
    if extra_note:
        user_prompt += f"\n\n{extra_note}"
    payload = _create_chat_completion(
        api_key=api_key,
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    parsed = parse_json_object(_extract_message_text(payload))
    raw_items = parsed.get("translations")
    if not isinstance(raw_items, list):
        raise ValueError("AI が対訳配列を返しませんでした。")
    return [str(item or "").strip() for item in raw_items]


def translate_script_to_japanese(
    script: str,
    *,
    api_key: str,
    model: str = TRANSLATION_MODEL,
) -> dict:
    """英語スクリプトを日本語訳し、左右対訳ペアも返す。"""
    script = str(script or "").strip()
    if not script:
        raise ValueError("スクリプトが空です。和訳するには英語スクリプトが必要です。")
    if not api_key:
        raise ValueError(
            "OpenAI API キーが未設定です。"
            "管理画面（/news/admin/）の「OpenAI API キー」欄にキーを入力して保存してください。"
        )

    units = split_script_units(script)
    translations = _request_translations(api_key=api_key, model=model, units=units)
    if len(translations) != len(units):
        translations = _request_translations(
            api_key=api_key,
            model=model,
            units=units,
            extra_note=f"前回は {len(translations)} 件でした。必ず {len(units)} 件にしてください。",
        )
    if len(translations) != len(units) or not any(translations):
        raise ValueError("AI が原文と同じ件数の和訳を返しませんでした。再試行してください。")

    pairs = [{"en": en, "ja": ja} for en, ja in zip(units, translations)]
    return {
        "script_ja": "\n".join(item["ja"] for item in pairs).strip(),
        "pairs": pairs,
    }
