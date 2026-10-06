"""語彙・ウォームアップ・ディスカッション。Toolbox の OpenAI 呼び出しだけを使う。"""
from __future__ import annotations

import json

from toolbox.config import GENERATE_TIMEOUT_SEC
from toolbox.openai_http import chat_completions
from toolbox.storage import get_setting


def _model() -> str:
    return str(get_setting("generate_model") or "gpt-4o-mini")


def _json_content(messages: list[dict]) -> dict:
    data = chat_completions(
        model=_model(),
        messages=messages,
        temperature=0.4,
        timeout=GENERATE_TIMEOUT_SEC,
        max_tokens=2500,
    )
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


def extract_vocabulary(script: str, min_cefr: str = "B1") -> list[dict]:
    payload = _json_content([
        {
            "role": "system",
            "content": (
                "You extract classroom vocabulary for Japanese high school students. "
                f"Return JSON {{\"vocabulary\":[{{\"word\",\"pos\",\"meaning\",\"cefr\"}}]}}. "
                f"8 to 16 items at CEFR {min_cefr} or harder. Japanese meanings. "
                "Skip proper nouns. Include some phrasal verbs that appear in the script."
            ),
        },
        {"role": "user", "content": script[:12000]},
    ])
    items = payload.get("vocabulary") or []
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word") or "").strip()
        if not word:
            continue
        cleaned.append({
            "word": word,
            "pos": str(item.get("pos") or "").strip(),
            "meaning": str(item.get("meaning") or "").strip(),
            "cefr": str(item.get("cefr") or min_cefr).strip(),
        })
    return cleaned[:16]


def extract_questions(script: str, kind: str) -> list[dict]:
    if kind == "warmup":
        instruction = "視聴前のウォームアップ質問を3つ。答えは短い英語の模範。"
    else:
        instruction = "視聴後のディスカッション質問を3つ。答えは短い英語の要点。"
    payload = _json_content([
        {
            "role": "system",
            "content": (
                f"{instruction} JSON {{\"items\":[{{\"q\",\"a\"}}]}} 。質問は英語。"
            ),
        },
        {"role": "user", "content": script[:12000]},
    ])
    items = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        q = str(item.get("q") or "").strip()
        if not q:
            continue
        items.append({"q": q, "a": str(item.get("a") or "").strip()})
    return items[:5]


def translate_script(script: str) -> str:
    payload = _json_content([
        {
            "role": "system",
            "content": "英語ニュース原稿を自然な日本語に訳す。JSON {\"translation\":\"...\"} のみ。",
        },
        {"role": "user", "content": script[:12000]},
    ])
    return str(payload.get("translation") or "").strip()
