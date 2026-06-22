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
#   - 各 CEFR レベルに具体的な代表語例を示し、モデルの誤分類を抑制する
#   - A1/A2 相当の語は除外し、B1〜C2 のみを抽出する
# ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a precise English vocabulary classifier. Your job: extract important \
vocabulary from a news script and assign ACCURATE CEFR levels based on the \
calibrated benchmarks below.

==== STEP 1 — EXCLUDE A1 and A2 words (do NOT include these) ====
Never include words at A1 or A2 level. Do NOT assign B1+ to common basic words.

A1 examples (exclude): wear, get, go, come, make, say, know, see, think, look, \
want, give, use, find, tell, feel, try, leave, call, work, need, ask, show, keep, \
turn, start, play, move, live, hold, bring, happen, write, sit, stand, lose, pay, \
meet, continue, set, learn, change, lead, understand, watch, follow, stop, speak, \
read, spend, grow, open, walk, win, offer, remember, love, consider, appear, buy, \
wait, build, stay, fall, cut, reach, remain, raise, pass, sell, decide, pull, \
break, eat, face, run, take, have, be, do, put, talk, help, big, small, new, old, \
good, bad, long, short, first, last, right, high, low, early, next, free, full, \
young, large, great, little, few, other, same, such, own, even, back, also, just, \
well, still, only, now, then, here, way, year, time, day, week, man, woman, child, \
thing, world, government, country, company, school, group, number, people, place, \
problem, part, side, case, point, area, end, fact, question, example, home, water, \
family, name, hand, head, line, state, story

A2 examples (also exclude — too easy for this list): prepare, describe, compare, \
develop, achieve, improve, various, recent, local, similar, serious, major, \
announce, attack, protect, release, affect, reduce, increase, support, suggest, \
require, provide, report, national, international, political, official, military, \
available, public, entire, further, central, important, different, special, common

==== STEP 2 — CALIBRATED CEFR benchmarks (B1 through C2 ONLY) ====

B1 — intermediate; challenging for Japanese Eiken Pre-2 students:
  despite, policy, demonstrate, significant, contribute, establish, indicate, \
  document, environment, participate, evaluate, procedure, specific, technique, \
  maintain, obtain, factor, process, respond, focus, principle, justify, \
  identify, generation, potential, consequence, influence, approach, shift, \
  reveal, impact, conflict, crisis, reform, protest, campaign, economy, budget, \
  threat, authority, community, investigation, represent, concern, access

B2 — upper-intermediate; Eiken Grade-2 level:
  advocate, analyze, comprehensive, constitute, elaborate, empirical, enforce, \
  formulate, hypothesis, implement, infrastructure, integrate, mechanism, \
  methodology, phenomenon, prevalent, rationale, reinforce, subsequent, \
  substantial, trigger, undermine, incorporate, initiative, resolution, \
  legislation, sanction, sovereignty, accountability, transparency, coalition, \
  proliferation, momentum, consensus, deployment, escalation, mitigation

C1 — advanced; IELTS 7+ / university entrance:
  albeit, acquiesce, amalgamate, articulate (express clearly), caveat, \
  circumvent, cognizant, discern, elucidate, exemplify, facilitate, formidable, \
  incumbent, inherent, mitigate, perpetuate, pervasive, preclude, substantiate, \
  accentuate, corollary, elicit, extrapolate, overarching, ramification, \
  unprecedented, exacerbate, deteriorate, scrutinize, rhetoric

C2 — mastery; near-native academic or literary vocabulary:
  ameliorate, assiduous, commensurate, desultory, equivocate, fastidious, \
  inexorable, laconic, perfidious, propitious, recalcitrant, sagacious, \
  tenacious, ubiquitous, categorical, cogitate, aberrant, mellifluous, \
  impecunious, opprobrious

==== STEP 3 — Additional rules ====
- Include ONLY words/phrases at B1, B2, C1, or C2. Never A1 or A2.
- Prefer harder vocabulary: collocations, phrasal verbs, idiomatic expressions, AWL words.
- Exclude proper nouns (place names, person names, organizations, brand names).
- Exclude extremely niche technical jargon unlikely in academic or exam contexts.
- Japanese meanings MUST reflect the word's meaning in THIS script's context.
- Return up to 20 items; fewer is fine if the script lacks enough B1+ vocabulary.
- Sort output hardest-first: C2 → C1 → B2 → B1.
- Return exactly the structured JSON format requested.\
"""

_USER_PROMPT_TEMPLATE = """\
Extract up to 20 important vocabulary items from the news script below.
Include ONLY B1, B2, C1, or C2 level words, phrases, and expressions.
Do NOT include A1 or A2 words (e.g. wear, get, prepare, describe, report, major).
Follow the CEFR calibration benchmarks in the system prompt exactly.

--- English script ---
{script}
--- end ---

Return a JSON object with a `vocabulary` array. Each item must include:
- "word": the word or phrase (lowercase, base form preferred)
- "cefr": one of B1, B2, C1, C2 only
- "part_of_speech": part of speech in Japanese (名詞、動詞、形容詞、副詞、熟語 など)
- "meaning": Japanese meaning that fits THIS script's context

Sort by difficulty descending (C2 → C1 → B2 → B1).\
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
