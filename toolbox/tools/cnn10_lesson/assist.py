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
            "part_of_speech": str(item.get("part_of_speech") or item.get("pos") or "").strip(),
            "meaning": str(item.get("meaning") or "").strip(),
            "cefr": str(item.get("cefr") or min_cefr).strip(),
            "selected": True,
        })
    return cleaned[:16]


def _qa_items(payload: dict) -> list[dict]:
    items = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("q") or "").strip()
        if not text:
            continue
        items.append({
            "text": text,
            "answer": str(item.get("answer") or item.get("a") or "").strip(),
            "selected": True,
        })
    return items[:5]


def extract_questions(script: str, kind: str) -> list[dict]:
    if kind == "warmup":
        instruction = "視聴前のウォームアップ質問を3つ。答えは短い英語の模範。"
    else:
        instruction = "視聴後のディスカッション質問を3つ。答えは短い英語の要点。"
    payload = _json_content([
        {
            "role": "system",
            "content": (
                f"{instruction} JSON {{\"items\":[{{\"text\",\"answer\"}}]}} 。質問は英語。"
            ),
        },
        {"role": "user", "content": script[:12000]},
    ])
    return _qa_items(payload)


def extract_writing(script: str) -> list[dict]:
    payload = _json_content([
        {
            "role": "system",
            "content": (
                "高校生向けの英語ライティング話題を2つ。"
                " JSON {\"items\":[{\"text\",\"text_ja\",\"kind\":\"opinion\",\"options\":[\"A\",\"B\"]}]}。"
                " text は英語の問い。options は意見が分かれる2択。"
            ),
        },
        {"role": "user", "content": script[:12000]},
    ])
    items = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        options = [str(opt).strip() for opt in (item.get("options") or []) if str(opt).strip()]
        items.append({
            "text": text,
            "text_ja": str(item.get("text_ja") or "").strip(),
            "kind": "opinion",
            "options": options[:2],
            "selected": True,
        })
    return items[:4]


def translate_script(script: str) -> str:
    payload = _json_content([
        {
            "role": "system",
            "content": "英語ニュース原稿を自然な日本語に訳す。JSON {\"translation\":\"...\"} のみ。",
        },
        {"role": "user", "content": script[:12000]},
    ])
    return str(payload.get("translation") or "").strip()
