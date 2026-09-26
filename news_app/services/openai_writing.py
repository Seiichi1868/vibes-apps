"""動画視聴後の OREO ライティング（約100語）→ スピーチ用トピックを5つ生成する。

3つは2択（Agree / Disagree など）から立場を選んで理由と具体例を書くもの、
2つは問いに答えてその理由を書くもの。
"""
from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel, Field

from news_app.services.openai_utils import create_parsed_chat_completion

WRITING_MODEL = "gpt-5.6-luna"


class OpinionTopic(BaseModel):
    prompt: str = Field(
        description=(
            "A two-choice writing prompt in simple English, 8–25 words. "
            'Either an "Agree or disagree: <statement>" prompt or a "Which is better, A or B?" prompt.'
        )
    )
    options: list[str] = Field(
        description='Exactly two short choice labels (1–4 words each), e.g. ["Agree", "Disagree"].',
        min_length=2,
        max_length=2,
    )
    prompt_ja: str = Field(description="Natural Japanese translation of the prompt for students.")


class QuestionTopic(BaseModel):
    prompt: str = Field(
        description=(
            "An open question in simple English, 8–25 words, that students answer and then explain why. "
            "Not a yes/no question."
        )
    )
    prompt_ja: str = Field(description="Natural Japanese translation of the question for students.")


class WritingTopicsExtraction(BaseModel):
    opinion_topics: list[OpinionTopic] = Field(
        description="Exactly 3 two-choice opinion prompts.",
        min_length=3,
        max_length=3,
    )
    question_topics: list[QuestionTopic] = Field(
        description="Exactly 2 open questions that ask for an answer and a reason.",
        min_length=2,
        max_length=2,
    )


_SYSTEM_PROMPT = """\
You are an expert English teacher for Japanese high school students (CEFR A2–B1, Eiken Pre-2 to 2).
Students have JUST WATCHED a news video. As the final task, each student writes about 100 words
in the OREO format and then gives a short speech:
  O = Opinion (state your position / answer)
  R = Reason (why)
  E = Example (a concrete example, experience, or fact)
  O = Opinion (restate your position)

Create writing & speech topics CONNECTED TO THE VIDEO'S THEME:

A) opinion_topics — exactly 3 two-choice prompts.
   - Students pick ONE side and support it with a reason and an example.
   - Use "Agree or disagree: <clear statement>" or "Which is better, A or B?" (or "Should ... ? Yes or no").
   - Both sides must be reasonable to defend; avoid prompts with an obvious right answer.
   - options = the two choice labels (e.g. ["Agree", "Disagree"], ["Online classes", "Classroom classes"]).
B) question_topics — exactly 2 open questions.
   - Ask for the student's own answer, which they then explain with a reason and an example
     (e.g. "What is the most important thing to do to stay healthy? Why?").
   - Not yes/no questions.

For all 5 topics:
- SIMPLE English (Eiken Pre-2 to 2), 8–25 words, one or two short sentences.
- Go from the video's specific story to a wider, personal or social issue that teenagers can discuss.
- Students must be able to write 100 words from their own life and knowledge, without re-watching.
- Each topic should focus on a DIFFERENT angle of the theme.
- prompt_ja: natural Japanese a high school student understands (not word-for-word).
"""


def _build_user_prompt(script: str) -> str:
    return f"""\
Students watched a news clip with this English script.
Create 3 two-choice opinion prompts and 2 open questions for a 100-word OREO writing and speech task.

--- News Script ---
{script}
--- End ---
"""


def extract_writing_topics_from_script(
    script: str,
    *,
    api_key: str,
    model: str = WRITING_MODEL,
) -> dict:
    """
    スクリプトから OREO ライティング用トピック5つ（2択3つ＋問い2つ）を生成する。

    Returns:
        {"topics": [{"id", "kind": "opinion"|"question", "text", "text_ja", "options", "selected"}, ...]}
    """
    script = str(script or "").strip()
    if not script:
        raise ValueError("スクリプトが空です。ライティングトピックを生成するには英語スクリプトが必要です。")
    if not api_key:
        raise ValueError(
            "OpenAI API キーが未設定です。"
            "管理画面の「OpenAI API キー」欄にキーを入力して保存してください。"
        )

    client = OpenAI(api_key=api_key, timeout=60.0)
    extraction: WritingTopicsExtraction = create_parsed_chat_completion(
        client,
        model,
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(script)},
        ],
        WritingTopicsExtraction,
        temperature=0.7,
    )

    topics: list[dict] = []
    for item in extraction.opinion_topics[:3]:
        text = str(item.prompt or "").strip()
        options = [str(opt or "").strip() for opt in item.options if str(opt or "").strip()][:2]
        if not text or len(options) < 2:
            continue
        topics.append(
            {
                "id": len(topics) + 1,
                "kind": "opinion",
                "text": text,
                "text_ja": str(item.prompt_ja or "").strip(),
                "options": options,
                "selected": False,
            }
        )
    for item in extraction.question_topics[:2]:
        text = str(item.prompt or "").strip()
        if not text:
            continue
        topics.append(
            {
                "id": len(topics) + 1,
                "kind": "question",
                "text": text,
                "text_ja": str(item.prompt_ja or "").strip(),
                "options": [],
                "selected": False,
            }
        )
    if len(topics) < 5:
        raise ValueError("ライティングトピックを5つ生成できませんでした。もう一度お試しください。")

    return {"topics": topics}
