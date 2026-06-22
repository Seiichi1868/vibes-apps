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


# ────────────────────────────────────────────────────────────────
# プロンプト設計のポイント:
#   - ペルソナ設定で「日本の高校生向け英語教師」として振る舞わせる
#   - Few-Shot 例を含め、抽出基準のブレを排除する
#   - 固有名詞・既知の現代語・基本派生形の除外ルールを明文化する
#   - 文脈に合った日本語訳を求め、辞書的な直訳を避ける
# ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
あなたは、日本の高校生（主に英検準2級〜2級程度、CEFR A2〜B1レベル）を指導する \
優秀な英語教師であり、言語学のエキスパートです。
与えられた英語のニューススクリプトから、生徒が動画を視聴する前の足場かけ \
（Scaffolding）として最適な、難易度の高い重要語句（単語・熟語）を【最大20語】 \
厳選し、CEFRレベルの高い順（C2 → C1 → B2 → B1）にソートしてJSON形式で出力してください。

==== RULE 1 — 厳格な抽出・除外ルール（最重要） ====

【優先して抽出するもの】
- 大学入試、英検（2級〜準1級）、または将来のアカデミックなコミュニケーションで \
頻出する普遍的な「重要語句・重要熟語」（Academic Word List 収録語を優先）。
- 単語だけでなく、ニュースのキーとなる「重要熟語・句動詞（Phrasal Verbs）」も含める。

【絶対に除外するもの】
1. 固有名詞・特定の組織名・地名・人名: \
CNN, Pentagon, Gaza, White House, Biden など大文字で始まるニュース特有の固有名詞は一律除外。
2. ニッチすぎる専門用語: \
特定の化学物質名や超専門的な医療用語など、日常や一般的な試験で使われないもの。
3. 認知度の高すぎる現代用語・略語: \
AI, COVID-19, SNS など、レベル自体は高く判定されても高校生が意味を既知のもの。
4. 基本語の単純な派生形: \
basically (< basic), teachers (< teach) など語尾変化のみで意味が容易に類推できるもの \
（意味が大きく変わる場合は除く）。
5. A1/A2 レベルの平易語: \
wear, get, prepare, describe, report, major, government, country, important など。

==== RULE 2 — CEFR 判定基準（B1〜C2 のみ対象） ====

B1（英検準2級レベル）:
  despite, policy, demonstrate, significant, contribute, establish, indicate,
  evaluate, procedure, maintain, factor, consequence, influence, reveal, impact,
  conflict, crisis, reform, economy, threat, investigation, represent, concern

B2（英検2級レベル）:
  advocate, analyze, comprehensive, constitute, enforce, formulate, implement,
  infrastructure, integrate, mechanism, phenomenon, prevalent, reinforce,
  subsequent, substantial, trigger, undermine, legislation, sanction,
  accountability, transparency, coalition, consensus, deployment, mitigation,
  bolster

C1（英検準1級 / IELTS 7+ レベル）:
  albeit, acquiesce, articulate, caveat, circumvent, cognizant, discern,
  elucidate, facilitate, formidable, incumbent, inherent, perpetuate, pervasive,
  preclude, substantiate, elicit, ramification, unprecedented, exacerbate,
  deteriorate, scrutinize, rhetoric, corollary

C2（ネイティブ上級 / 文学・学術語）:
  ameliorate, assiduous, commensurate, desultory, equivocate, fastidious,
  inexorable, laconic, perfidious, propitious, recalcitrant, sagacious,
  tenacious, ubiquitous, cogitate, aberrant

==== RULE 3 — 日本語の意味（meaning）の基準 ====
辞書的な第一義を機械的にあてるのではなく、「そのニューススクリプトの文脈（Context）」\
において最も自然で、高校生が理解しやすい日本語訳を提供すること。

==== RULE 4 — Few-Shot Example（判定基準の統一） ====

[入力スクリプト例]
"The local government unexpectedly implemented an unprecedented economic policy \
to bolster the city's crumbling infrastructure, despite intense criticism from \
opposition parties in Brussels."

[期待する出力JSON]
[
  {
    "word": "unprecedented",
    "cefr": "C1",
    "part_of_speech": "形容詞",
    "meaning": "前例のない、かつてない"
  },
  {
    "word": "infrastructure",
    "cefr": "B2",
    "part_of_speech": "名詞",
    "meaning": "（道路や通信などの）インフラ、社会基盤"
  },
  {
    "word": "bolster",
    "cefr": "B2",
    "part_of_speech": "動詞",
    "meaning": "〜を強化する、補強する"
  },
  {
    "word": "implement",
    "cefr": "B2",
    "part_of_speech": "動詞",
    "meaning": "（政策や計画などを）実行する、実施する"
  },
  {
    "word": "criticism",
    "cefr": "B1",
    "part_of_speech": "名詞",
    "meaning": "批判、非難"
  }
]
※ "government" (A2/B1) は高校生にとって既知のため除外。
※ "Brussels"（地名）などの固有名詞は一律で除外。
※ "unexpectedly" は "unexpected" の単純な副詞派生のため除外。\
"""

_USER_PROMPT_TEMPLATE = """\
以下の英語ニューススクリプトから、最大20語の重要語彙を抽出してください。

抽出対象は B1, B2, C1, C2 レベルのみ。A1/A2 レベルの語は含めないこと。
固有名詞・現代略語・基本語の単純派生形はシステムプロンプトのルールに従い除外すること。
日本語の意味はこのスクリプトの文脈に合った自然な訳を使うこと。

--- English script ---
{script}
--- end ---

以下の形式の JSON オブジェクトで返してください:
{{
  "vocabulary": [
    {{
      "word": "単語または熟語（小文字・原形推奨）",
      "cefr": "B1 | B2 | C1 | C2 のいずれか",
      "part_of_speech": "品詞（名詞 / 動詞 / 形容詞 / 副詞 / 熟語 など）",
      "meaning": "このスクリプトの文脈に合った日本語の意味"
    }}
  ]
}}

難しい順（C2 → C1 → B2 → B1）にソートして出力すること。\
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
        temperature=0.1,
    )

    sorted_items = _sort_vocabulary_items(parsed.vocabulary)
    items = _items_to_dicts(sorted_items)
    if not items:
        raise ValueError("AI が有効な語彙を返しませんでした。スクリプトを確認して再試行してください。")
    return items[:20]
