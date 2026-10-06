"""語彙・ウォームアップ・ディスカッション。Toolbox の OpenAI 呼び出しだけを使う。"""
from __future__ import annotations

import json

from toolbox.config import GENERATE_TIMEOUT_SEC
from toolbox.openai_http import chat_completions
from toolbox.storage import get_setting


def _model() -> str:
    return str(get_setting("generate_model") or "gpt-4o-mini")


def _json_content(messages: list[dict], max_tokens: int = 2500) -> dict:
    data = chat_completions(
        model=_model(),
        messages=messages,
        temperature=0.4,
        timeout=GENERATE_TIMEOUT_SEC,
        max_tokens=max_tokens,
    )
    content = str(data["choices"][0]["message"]["content"] or "").strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
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


def translate_script(script: str) -> dict:
    """原文の文と同じ件数・同じ順の和訳を返す。"""
    from toolbox.services.script_align import split_script_units

    units = split_script_units(script)
    if not units:
        return {"translation": "", "pairs": []}
    numbered = "\n".join(f"{index}. {unit}" for index, unit in enumerate(units, start=1))
    messages = [
        {
            "role": "system",
            "content": (
                "あなたは、日本の高校の英語授業向けにニュース原稿を訳す翻訳者です。"
                "番号付きの英語ユニットを、同じ順番・同じ件数で日本語に翻訳してください。"
                "各ユニットは1文です。左右対訳で並べられるように、文の対応を崩さないでください。"
                "前置き・解説・注釈は付けない。"
                "出力は JSON オブジェクトのみ。キーは translations。"
                "translations は文字列配列で、入力ユニットと同じ件数・同じ順番にする。"
                "1つの英語ユニットに対して、対応する日本語を1つだけ入れる。"
                "ニュースとして自然な日本語にする。固有名詞は一般的な日本語表記があればそれを使い、なければ英語のまま残す。"
                "数字・日付・肩書は原文の情報を落とさない。"
            ),
        },
        {
            "role": "user",
            "content": (
                "次の英語ユニットを日本語に翻訳してください。\n"
                f"translations 配列は必ず {len(units)} 件にしてください。\n\n"
                '{"translations": ["日本語1", "日本語2"]}\n\n'
                f"--- English units ---\n{numbered}\n--- End ---\n"
            ),
        },
    ]
    payload = _json_content(messages, max_tokens=6000)
    translations = payload.get("translations")
    if not isinstance(translations, list):
        translations = []
    translations = [str(item or "").strip() for item in translations]
    if len(translations) != len(units):
        messages.append({"role": "assistant", "content": json.dumps({"translations": translations}, ensure_ascii=False)})
        messages.append({
            "role": "user",
            "content": f"前回は {len(translations)} 件でした。必ず {len(units)} 件にしてください。",
        })
        payload = _json_content(messages, max_tokens=6000)
        translations = payload.get("translations")
        if not isinstance(translations, list):
            translations = []
        translations = [str(item or "").strip() for item in translations]
    if len(translations) != len(units):
        raise RuntimeError("AI が原文と同じ件数の和訳を返しませんでした。再試行してください。")
    pairs = [{"en": en, "ja": ja} for en, ja in zip(units, translations)]
    return {"translation": "\n".join(translations), "pairs": pairs}
