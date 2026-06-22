"""スクリプトから導入用イラスト画像プロンプトと質問5問を生成するサービス。"""
from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel, Field

from news_app.services.openai_utils import create_parsed_chat_completion

WARMUP_MODEL = "gpt-5.4-mini"


class WarmupExtraction(BaseModel):
    image_prompt: str = Field(
        description=(
            "A single DALL-E 3 image generation prompt in English describing a clean, flat vector "
            "illustration suitable for educational materials. The image should symbolically represent "
            "the main topic of the news script. Begin with: "
            "'A clean, flat vector illustration suitable for educational materials, depicting...'"
        )
    )
    questions: list[str] = Field(
        description=(
            "Exactly 5 open-ended questions in simple English (5–12 words each) about the news topic, "
            "suitable for Japanese high school students (Eiken Pre-2 to 2 level, CEFR A2–B1) "
            "to answer intuitively before watching the video."
        ),
        min_length=5,
        max_length=5,
    )


_SYSTEM_PROMPT = """\
You are an expert English teacher for Japanese high school students (CEFR A2–B1, Eiken Pre-2 to 2).
Given an English news script, produce two things:

1. image_prompt: A single English prompt for DALL-E 3.
   - Describe a CLEAN, FLAT VECTOR ILLUSTRATION suitable for educational materials.
   - The image should SYMBOLICALLY represent the main topic of the news script.
   - Must start with: "A clean, flat vector illustration suitable for educational materials, depicting..."
   - Do NOT include any text, letters, or words in the illustration description.
   - Keep it vivid, colorful, and engaging for teenagers.

2. questions: Exactly 5 open-ended questions in SIMPLE English (5–12 words each).
   - Students answer these BEFORE watching the video (intuitive/opinion answers are fine).
   - Keep vocabulary simple (Eiken Pre-2 to 2 level, CEFR A2–B1).
   - Use varied question starters: What do you think...?, Have you ever...?, Why do you think...?,
     Do you know...?, How would you...?, What would you do if...?
   - Each question should address a DIFFERENT aspect of the topic.
"""


def _build_user_prompt(script: str) -> str:
    return f"""\
Please analyze the following English news script and produce:
- One DALL-E 3 image prompt (symbolic flat vector illustration, no text in the image)
- Exactly 5 pre-viewing open questions in simple English for Japanese high school students

--- News Script ---
{script}
--- End ---
"""


def extract_warmup_from_script(
    script: str,
    *,
    api_key: str,
    model: str = WARMUP_MODEL,
) -> dict:
    """
    スクリプトから導入用イラスト画像と5問の質問を生成する。

    Returns:
        {
            "image_url": str,
            "image_prompt": str,
            "questions": [{"id": int, "text": str, "selected": bool}, ...]
        }
    """
    script = str(script or "").strip()
    if not script:
        raise ValueError("スクリプトが空です。ウォームアップを生成するには英語スクリプトが必要です。")
    if not api_key:
        raise ValueError(
            "OpenAI API キーが未設定です。"
            "管理画面の「OpenAI API キー」欄にキーを入力して保存してください。"
        )

    client = OpenAI(api_key=api_key)

    extraction: WarmupExtraction = create_parsed_chat_completion(
        client,
        model,
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(script)},
        ],
        WarmupExtraction,
        temperature=0.7,
    )

    image_response = client.images.generate(
        model="dall-e-3",
        prompt=extraction.image_prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    image_url = image_response.data[0].url

    questions = [
        {"id": i + 1, "text": q.strip(), "selected": True}
        for i, q in enumerate(extraction.questions[:5])
        if q.strip()
    ]

    return {
        "image_url": image_url,
        "image_prompt": extraction.image_prompt,
        "questions": questions,
    }
