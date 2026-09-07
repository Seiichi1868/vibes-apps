"""動画視聴後の理解確認・会話練習用の質問5問を生成する。"""
from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel, Field

from news_app.services.openai_utils import create_parsed_chat_completion

POSTVIEW_MODEL = "gpt-5.6-luna"


class PostviewExtraction(BaseModel):
    questions: list[str] = Field(
        description=(
            "Exactly 5 open-ended post-viewing questions in simple English (6–14 words each). "
            "They check understanding of the news and spark pair/group discussion in class."
        ),
        min_length=5,
        max_length=5,
    )


_SYSTEM_PROMPT = """\
You are an expert English teacher for Japanese high school students (CEFR A2–B1, Eiken Pre-2 to 2).
Students have JUST WATCHED a news video. Create questions they will discuss with classmates.

Return exactly 5 open-ended questions in SIMPLE English (6–14 words each).

Goals:
- Check understanding of the video (main facts, causes, effects, people involved).
- Then move into opinion / personal connection so students can talk with a partner.
- Mix the five questions: about 3 comprehension + 2 discussion/opinion.
- Keep vocabulary simple (Eiken Pre-2 to 2, CEFR A2–B1).
- Do NOT ask questions that can be answered without watching (pure pre-viewing guesses).
- Do NOT ask yes/no questions only. Prefer Why / How / What / Which / Do you think... why?
- Each question should address a DIFFERENT aspect of the story.
- These will be used for speaking practice in pairs or small groups after viewing.
"""


def _build_user_prompt(script: str) -> str:
    return f"""\
Students watched a news clip with this English script.
Create exactly 5 post-viewing questions for pair/group discussion in class.

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
    スクリプトから視聴後の理解・会話質問5問を生成する。

    Returns:
        {"questions": [{"id": int, "text": str, "selected": bool}, ...]}
    """
    script = str(script or "").strip()
    if not script:
        raise ValueError("スクリプトが空です。事後質問を生成するには英語スクリプトが必要です。")
    if not api_key:
        raise ValueError(
            "OpenAI API キーが未設定です。"
            "管理画面の「OpenAI API キー」欄にキーを入力して保存してください。"
        )

    client = OpenAI(api_key=api_key)
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

    questions = [
        {"id": i + 1, "text": q.strip(), "selected": True}
        for i, q in enumerate(extraction.questions[:5])
        if q.strip()
    ]
    if len(questions) < 5:
        raise ValueError("事後質問を5問生成できませんでした。もう一度お試しください。")

    return {"questions": questions}
