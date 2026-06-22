"""英語スクリプトから CEFR B1〜C2 の重要語彙を抽出する。"""

from __future__ import annotations

from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from news_app.config import VOCABULARY_EXTRACTION_MODEL, VOCAB_CEFR_LEVELS
from news_app.services.openai_utils import create_parsed_chat_completion

VOCAB_CEFR_ORDER = {level: index for index, level in enumerate(VOCAB_CEFR_LEVELS)}


class VocabularyItem(BaseModel):
    word: str = Field(description="単語または熟語")
    cefr: Literal["B1", "B2", "C1", "C2"] = Field(description="CEFR 難易度レベル")
    part_of_speech: str = Field(description="品詞（名詞、動詞、形容詞、副詞、熟語 など）")
    meaning: str = Field(description="スクリプト内の文脈に合致した日本語の意味")


class VocabularyExtractionResult(BaseModel):
    vocabulary: list[VocabularyItem] = Field(
        description="難しい順（C2→C1→B2→B1）に並べた重要語彙（最大20語）",
        min_length=1,
        max_length=20,
    )


_SYSTEM_PROMPT = (
    "You are an English vocabulary expert for Japanese high school students "
    "(roughly Eiken Pre-2 to Grade 2 level). "
    "From an English news script, extract up to 20 important words and phrases "
    "at CEFR B1 through C2 that students are likely to find challenging.\n\n"
    "Rules:\n"
    "- Order items from hardest to easiest: C2 first, then C1, B2, B1.\n"
    "- Exclude proper nouns (place names, person names, brand names).\n"
    "- Exclude overly specialized jargon unlikely to appear on university entrance exams.\n"
    "- Prefer academic and high-frequency words useful for exams and general communication (AWL-style).\n"
    "- Include useful collocations/phrasal verbs when they matter in the script.\n"
    "- Japanese meanings must reflect the word's meaning IN THIS SCRIPT's context, not generic dictionary glosses.\n"
    "- Return exactly the structured JSON schema requested."
)

_USER_PROMPT_TEMPLATE = (
    "Extract up to 20 important vocabulary items from the English script below.\n\n"
    "--- English script ---\n"
    "{script}\n"
    "--- end ---\n\n"
    "Return a JSON object with a `vocabulary` array. Each item must include:\n"
    '- "word": the word or phrase\n'
    '- "cefr": one of B1, B2, C1, C2\n'
    '- "part_of_speech": part of speech in Japanese (名詞、動詞、形容詞、副詞、熟語 など)\n'
    '- "meaning": Japanese meaning matching the script context\n\n'
    "Sort by difficulty descending (C2 → C1 → B2 → B1)."
)


def _sort_vocabulary_items(items: list[VocabularyItem]) -> list[VocabularyItem]:
    return sorted(
        items,
        key=lambda item: (VOCAB_CEFR_ORDER.get(item.cefr, 99), item.word.lower()),
    )


def _items_to_dicts(items: list[VocabularyItem]) -> list[dict]:
    return [
        {
            "word": item.word.strip(),
            "cefr": item.cefr,
            "part_of_speech": item.part_of_speech.strip(),
            "meaning": item.meaning.strip(),
        }
        for item in items
        if item.word.strip() and item.meaning.strip()
    ]


def extract_vocabulary_from_script(
    script: str,
    *,
    api_key: str,
    model: str = VOCABULARY_EXTRACTION_MODEL,
) -> list[dict]:
    """英語スクリプトから語彙リスト（最大20件）を抽出する。"""
    script = str(script or "").strip()
    if not script:
        raise ValueError("スクリプトが空です。語彙を抽出するには英語スクリプトが必要です。")
    if not api_key:
        raise ValueError(
            "OpenAI API キーが未設定です。"
            "管理画面（/news/admin/）の「OpenAI API キー」欄にキーを入力して保存してください。"
        )

    client = OpenAI(api_key=api_key)
    parsed = create_parsed_chat_completion(
        client,
        model,
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_PROMPT_TEMPLATE.format(script=script)},
        ],
        VocabularyExtractionResult,
        temperature=0.2,
    )

    sorted_items = _sort_vocabulary_items(parsed.vocabulary)
    items = _items_to_dicts(sorted_items)
    if not items:
        raise ValueError("AI が有効な語彙を返しませんでした。スクリプトを確認して再試行してください。")
    return items[:20]
