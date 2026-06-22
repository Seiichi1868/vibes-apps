"""英語スクリプトから CEFR B1〜C2 の重要語彙を抽出する。"""

from __future__ import annotations

from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from news_app.config import (
    VOCABULARY_EXTRACTION_MODEL,
    VOCAB_CEFR_LEVELS,
    VOCAB_EXTRACTION_MAX,
    VOCAB_EXTRACTION_MIN,
    VOCAB_EXTRACTION_TARGET,
)
from news_app.services.openai_utils import create_parsed_chat_completion

VOCAB_CEFR_ORDER = {level: index for index, level in enumerate(VOCAB_CEFR_LEVELS)}


class VocabularyItem(BaseModel):
    word: str = Field(description="単語、熟語、句動詞、またはコロケーション")
    cefr: Literal["B1", "B2", "C1", "C2"] = Field(description="CEFR 難易度レベル")
    part_of_speech: str = Field(
        description="品詞（名詞、動詞、形容詞、副詞、熟語、句動詞 など）"
    )
    meaning: str = Field(description="スクリプト内の文脈に合致した日本語の意味")


class VocabularyExtractionResult(BaseModel):
    vocabulary: list[VocabularyItem] = Field(
        description=(
            f"難しい順（C2→C1→B2→B1）に並べた重要語彙。"
            f"目標{VOCAB_EXTRACTION_TARGET}語（最低{VOCAB_EXTRACTION_MIN}語）"
        ),
        min_length=1,
        max_length=VOCAB_EXTRACTION_MAX,
    )


class VocabularySupplementResult(BaseModel):
    vocabulary: list[VocabularyItem] = Field(
        description="追加で抽出した重要語彙（既出語と重複しないこと）",
        min_length=1,
        max_length=VOCAB_EXTRACTION_MAX,
    )


def _build_system_prompt() -> str:
    return f"""\
あなたは、日本の高校生（主に英検準2級〜2級程度、CEFR A2〜B1レベル）を指導する \
優秀な英語教師であり、言語学のエキスパートです。
与えられた英語のニューススクリプトから、生徒が動画を視聴する前の足場かけ \
（Scaffolding）として最適な重要語句を【必ず{VOCAB_EXTRACTION_MIN}〜{VOCAB_EXTRACTION_MAX}語】 \
抽出し、CEFRレベルの高い順（C2 → C1 → B2 → B1）にソートしてJSON形式で出力してください。

==== RULE 0 — 出力件数（最優先） ====
- 「最大{VOCAB_EXTRACTION_MAX}語」ではなく、**毎回 {VOCAB_EXTRACTION_MIN}〜{VOCAB_EXTRACTION_MAX} 語を必ず出力**すること。
- 教師が後から約10語を除外する前提のため、**少なすぎる抽出（20語以下）は不可**。
- 単語だけでなく、**句動詞・コロケーション・熟語表現を全体の8〜12語程度**積極的に含めること。
  例: carry out, set up, deal with, in response to, according to, as a result of, \
take action, face criticism, economic policy, opposition party など（スクリプトに実在するもののみ）。

==== RULE 1 — 厳格な抽出・除外ルール ====

【優先して抽出するもの】
- 大学入試、英検（2級〜準1級）、または将来のアカデミックなコミュニケーションで \
頻出する普遍的な「重要語句・重要熟語」（Academic Word List 収録語を優先）。
- ニュースのキーとなる「重要熟語・句動詞（Phrasal Verbs）・固定表現」。

【絶対に除外するもの】
1. 固有名詞・特定の組織名・地名・人名 \
（CNN, Pentagon, Gaza, White House, Biden など）。
2. ニッチすぎる専門用語（超専門的な医療・化学用語など）。
3. 認知度の高すぎる現代用語・略語（AI, COVID-19, SNS など）。
4. 基本語の単純な派生形 \
（basically, teachers など、意味が容易に類推できるもの。意味が大きく変わる場合は除く）。
5. A1/A2 レベルの平易語 \
（wear, get, prepare, describe, report, major, government, country, important など）。

==== RULE 2 — CEFR 判定基準（B1〜C2 のみ対象） ====

B1: despite, policy, demonstrate, significant, contribute, establish, criticism, \
impact, conflict, crisis, reform, economy, threat, investigation, concern
B2: advocate, analyze, implement, infrastructure, reinforce, substantial, trigger, \
undermine, legislation, accountability, transparency, coalition, bolster, carry out, \
deal with
C1: articulate, facilitate, formidable, inherent, pervasive, unprecedented, \
exacerbate, scrutinize, rhetoric, in response to
C2: ameliorate, commensurate, inexorable, ubiquitous, propitious

==== RULE 3 — 日本語の意味（meaning）の基準 ====
辞書的な第一義を機械的にあてるのではなく、「そのニューススクリプトの文脈（Context）」\
において最も自然で、高校生が理解しやすい日本語訳を提供すること。

==== RULE 4 — Few-Shot Example（判定基準の統一） ====

[入力スクリプト例]
"The local government unexpectedly implemented an unprecedented economic policy \
to bolster the city's crumbling infrastructure, despite intense criticism from \
opposition parties in Brussels."

[期待する出力JSON — 注: 実際のニューススクリプトでは必ず{VOCAB_EXTRACTION_MIN}〜{VOCAB_EXTRACTION_MAX}語出力]
[
  {{
    "word": "unprecedented",
    "cefr": "C1",
    "part_of_speech": "形容詞",
    "meaning": "前例のない、かつてない"
  }},
  {{
    "word": "infrastructure",
    "cefr": "B2",
    "part_of_speech": "名詞",
    "meaning": "（道路や通信などの）インフラ、社会基盤"
  }},
  {{
    "word": "bolster",
    "cefr": "B2",
    "part_of_speech": "動詞",
    "meaning": "〜を強化する、補強する"
  }},
  {{
    "word": "economic policy",
    "cefr": "B2",
    "part_of_speech": "熟語",
    "meaning": "経済政策"
  }},
  {{
    "word": "implement",
    "cefr": "B2",
    "part_of_speech": "動詞",
    "meaning": "（政策や計画などを）実行する、実施する"
  }},
  {{
    "word": "criticism",
    "cefr": "B1",
    "part_of_speech": "名詞",
    "meaning": "批判、非難"
  }}
]
※ "government" は高校生にとって既知のため除外。"Brussels" は固有名詞のため除外。\
"""


def _build_user_prompt(script: str) -> str:
    return f"""\
以下の英語ニューススクリプトから、**必ず{VOCAB_EXTRACTION_MIN}〜{VOCAB_EXTRACTION_MAX}語** \
の重要語彙を抽出してください。20語以下の出力は不可です。

- 単語に加え、句動詞・コロケーション・熟語表現を8語以上含めること
- 抽出対象は B1, B2, C1, C2 レベルのみ（A1/A2 は除外）
- 固有名詞・現代略語・基本語の単純派生形は除外
- 日本語の意味はこのスクリプトの文脈に合った自然な訳を使うこと

--- English script ---
{script}
--- end ---

以下の形式の JSON オブジェクトで返してください:
{{
  "vocabulary": [
    {{
      "word": "単語・熟語・句動詞（小文字・原形推奨）",
      "cefr": "B1 | B2 | C1 | C2 のいずれか",
      "part_of_speech": "品詞（名詞 / 動詞 / 形容詞 / 副詞 / 熟語 / 句動詞 など）",
      "meaning": "このスクリプトの文脈に合った日本語の意味"
    }}
  ]
}}

難しい順（C2 → C1 → B2 → B1）にソートし、件数が{VOCAB_EXTRACTION_MIN}未満にならないよう十分に抽出すること。\
"""


def _build_supplement_user_prompt(script: str, existing_words: list[str], need: int) -> str:
    existing_block = "\n".join(f"- {word}" for word in existing_words) or "（なし）"
    return f"""\
前回の抽出では語数が不足しています。以下のスクリプトから、**あと{need}語以上** \
の追加語彙を抽出してください（合計{VOCAB_EXTRACTION_TARGET}語前後を目標）。

- 既に抽出済みの語句は絶対に含めない
- 句動詞・コロケーション・熟語表現を優先的に探す
- B1〜C2 のみ。固有名詞・A1/A2 語は除外

【既出語句（重複禁止）】
{existing_block}

--- English script ---
{script}
--- end ---

JSON 形式: {{ "vocabulary": [ ... ] }}（{need}語以上、最大{need + 5}語）\
"""


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
            "selected": True,
        }
        for item in items
        if item.word.strip() and item.meaning.strip()
    ]


def _merge_vocab_dicts(primary: list[dict], extra: list[dict]) -> list[dict]:
    seen = {item["word"].strip().lower() for item in primary}
    merged = list(primary)
    for item in extra:
        word_key = item["word"].strip().lower()
        if not word_key or word_key in seen:
            continue
        seen.add(word_key)
        merged.append(item)
    merged.sort(
        key=lambda item: (VOCAB_CEFR_ORDER.get(item.get("cefr", ""), 99), item["word"].lower())
    )
    return merged[:VOCAB_EXTRACTION_MAX]


def _request_vocabulary(
    client: OpenAI,
    model: str,
    messages: list[dict],
    *,
    response_model: type[BaseModel],
    temperature: float,
) -> list[VocabularyItem]:
    parsed = create_parsed_chat_completion(
        client,
        model,
        messages,
        response_model,
        temperature=temperature,
    )
    return _sort_vocabulary_items(parsed.vocabulary)


def extract_vocabulary_from_script(
    script: str,
    *,
    api_key: str,
    model: str = VOCABULARY_EXTRACTION_MODEL,
) -> list[dict]:
    """英語スクリプトから語彙リスト（25〜30件）を抽出する。"""
    script = str(script or "").strip()
    if not script:
        raise ValueError("スクリプトが空です。語彙を抽出するには英語スクリプトが必要です。")
    if not api_key:
        raise ValueError(
            "OpenAI API キーが未設定です。"
            "管理画面（/news/admin/）の「OpenAI API キー」欄にキーを入力して保存してください。"
        )

    client = OpenAI(api_key=api_key)
    system_prompt = _build_system_prompt()

    initial_items = _request_vocabulary(
        client,
        model,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_user_prompt(script)},
        ],
        response_model=VocabularyExtractionResult,
        temperature=0.1,
    )
    items = _items_to_dicts(initial_items)

    supplement_attempts = 0
    while len(items) < VOCAB_EXTRACTION_MIN and supplement_attempts < 2:
        need = VOCAB_EXTRACTION_TARGET - len(items)
        existing_words = [item["word"] for item in items]
        supplement_items = _request_vocabulary(
            client,
            model,
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": _build_supplement_user_prompt(script, existing_words, need),
                },
            ],
            response_model=VocabularySupplementResult,
            temperature=0.15,
        )
        items = _merge_vocab_dicts(items, _items_to_dicts(supplement_items))
        supplement_attempts += 1

    if not items:
        raise ValueError("AI が有効な語彙を返しませんでした。スクリプトを確認して再試行してください。")
    return items[:VOCAB_EXTRACTION_MAX]
