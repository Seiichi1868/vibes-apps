"""動画視聴後の理解確認・会話練習用の質問5問と模範解答を生成する。"""
from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel, Field

from news_app.services.openai_utils import create_parsed_chat_completion

POSTVIEW_MODEL = "gpt-5.6-luna"


class PostviewItem(BaseModel):
    question: str = Field(
        description="One open-ended post-viewing question in simple English, 6–14 words."
    )
    answer: str = Field(
        description=(
            "One model answer in simple English, 8–20 words, a single sentence "
            "a student could say aloud."
        )
    )


class PostviewExtraction(BaseModel):
    items: list[PostviewItem] = Field(
        description="Exactly 5 post-viewing questions, each with a model answer.",
        min_length=5,
        max_length=5,
    )


_SYSTEM_PROMPT = """\
You are an expert English teacher for Japanese high school students (CEFR A2–B1, Eiken Pre-2 to 2).
Students have JUST WATCHED a news video. Create questions they will discuss with classmates,
and a short model answer for each question.

Return exactly 5 items. Each item has a question and an answer.

Questions — SIMPLE English, 6–14 words each:
- Check understanding of the video (main facts, causes, effects, people involved).
- Then move into opinion / personal connection so students can talk with a partner.
- Mix the five questions: about 3 comprehension + 2 discussion/opinion.
- Keep vocabulary simple (Eiken Pre-2 to 2, CEFR A2–B1).
- Do NOT ask questions that can be answered without watching (pure pre-viewing guesses).
- Do NOT ask yes/no questions only. Prefer Why / How / What / Which / Do you think... why?
- Each question should address a DIFFERENT aspect of the story.

Model answers — SIMPLE English, one sentence, about 8–20 words:
- Comprehension: a factual sentence supported by the script. Do not invent details.
- Opinion: a first-person sample a student could say (I think... / I would...).
- Do not copy a long stretch of the script. No Japanese.
"""


def _build_user_prompt(script: str) -> str:
    return f"""\
Students watched a news clip with this English script.
Create exactly 5 post-viewing questions for pair/group discussion in class.
Write one model answer for each question.

--- News Script ---
{script}
--- End ---
"""


def extract_postview_from_script(
    script: str,
    *,
    api_key: str,
    model: str = POSTVIEW_MODEL,
) -> dict:
    """
    スクリプトから視聴後の理解・会話質問5問と模範解答を生成する。

    Returns:
        {"questions": [{"id": int, "text": str, "answer": str, "selected": bool}, ...]}
    """
    script = str(script or "").strip()
    if not script:
        raise ValueError("スクリプトが空です。事後質問を生成するには英語スクリプトが必要です。")
    if not api_key:
        raise ValueError(
            "OpenAI API キーが未設定です。"
            "管理画面の「OpenAI API キー」欄にキーを入力して保存してください。"
        )

    client = OpenAI(api_key=api_key, timeout=60.0)
    extraction: PostviewExtraction = create_parsed_chat_completion(
        client,
        model,
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(script)},
        ],
        PostviewExtraction,
        temperature=0.7,
    )

    questions = []
    for item in extraction.items[:5]:
        text = str(item.question or "").strip()
        answer = str(item.answer or "").strip()
        if not text or not answer:
            continue
        questions.append(
            {
                "id": len(questions) + 1,
                "text": text,
                "answer": answer,
                "selected": True,
            }
        )
    if len(questions) < 5:
        raise ValueError("事後質問と模範解答を5問分生成できませんでした。もう一度お試しください。")

    return {"questions": questions}
