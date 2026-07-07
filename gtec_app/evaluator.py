"""GTEC Speaking 自動採点モジュール。

音声ファイルは受け取らず、ブラウザ側で文字起こしされたテキストと発話秒数から
OpenAI API で各パートの GTEC 公式基準に基づいたスコアとフィードバックを生成する。
"""

import json
import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _client


MODEL = "gpt-4o-mini"

_SYSTEM = (
    "You are an expert GTEC Speaking Test examiner for Japanese high school students. "
    "Evaluate spoken English using official GTEC scoring rubrics. "
    "Return ONLY a valid JSON object matching the exact schema in the prompt. "
    "Write all feedback text in Japanese. "
    "Grammar and vocabulary corrections must be in English. "
    "Be encouraging, specific, and constructive. "
    "Score fluency_pronunciation generously: when uncertain between two adjacent scores, choose the higher one."
)

_FLUENCY_LENIENT = """Score fluency_pronunciation generously for high school learners.
- Award 3–4 when speech is generally understandable and flows reasonably well.
- Minor pauses, slightly slow/fast pace, or browser-transcription gaps should NOT heavily reduce the score.
- WPM outside 120–150 is acceptable if delivery is still clear.
- When uncertain between two adjacent scores, choose the higher one."""


def _wpm(text: str, duration: float) -> float:
    words = len(text.split()) if text.strip() else 0
    return round(words / duration * 60, 1) if duration > 0 else 0.0


def _call(prompt: str) -> dict:
    resp = _get_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        max_tokens=1200,
        temperature=0.3,
    )
    return json.loads(resp.choices[0].message.content)


# ─── Part A: Reading Aloud ────────────────────────────────────────────────────

def evaluate_part_a(text: str, duration: float, target_text: str) -> dict:
    """発音・流ちょうさ 0〜4点を WPM・単語抜けから推定。"""
    wpm = _wpm(text, duration)
    prompt = f"""GTEC Part A – Reading Aloud

Target text (shown to student):
"{target_text}"

Student's speech (browser transcription):
"{text}"

Duration: {duration:.1f}s | WPM: {wpm} (ideal 120–150)

=== Fluency & Pronunciation (0–4) ===
{_FLUENCY_LENIENT}
4 – Reads well with natural or mostly natural pace; only minor hesitations or a few small omissions
3 – Generally smooth; some hesitations, slightly slow/fast pace, or several minor omissions are acceptable
2 – Noticeable hesitations or pace issues, but a substantial portion of the text was read
1 – Major difficulty delivering the text; many omissions or repetitions
0 – No meaningful speech or entirely off-task

Omissions: words present in target but absent in student text.
Repetitions: same word/phrase appearing twice or more in student text.
Browser transcription may miss or alter words — do NOT heavily penalize minor transcription differences.

Return exactly this JSON (no extra keys):
{{
  "scores": {{
    "fluency_pronunciation": <integer 0–4>
  }},
  "wpm_calculated": {wpm}
}}"""
    return _call(prompt)


# ─── Part B: Interacting with Others ─────────────────────────────────────────

def evaluate_part_b(text: str, duration: float, question: str, context: str) -> dict:
    """Goal Achievement 0 or 1 per question."""
    prompt = f"""GTEC Part B – Interacting with Others

Context shown to student: {context}
Question asked (audio only): "{question}"
Student's response (transcription): "{text}"
Duration: {duration:.1f}s

=== Goal Achievement (0 or 1) ===
1 – Student conveyed the necessary information (even a single word or number is fine)
0 – No response, irrelevant response, or required information not conveyed

IMPORTANT:
- Even one-word answers earn full marks if they correctly answer the question.
- Part B only requires stating facts visible on the chart. Do NOT suggest elaborating, explaining more, or giving longer answers.
- Do NOT advise the student to "explain in more detail" or similar.

Return exactly:
{{
  "scores": {{
    "goal_achievement": <0 or 1>
  }},
  "feedback": {{
    "grammar_corrections": [{{"original": "<phrase or word>", "corrected": "<corrected>", "explanation": "<brief Japanese or empty>"}}]
  }}
}}

grammar_corrections may include both grammar mistakes and awkward word choices / vocabulary improvements.
Only include clear errors. Use an empty array if none.
Do NOT include good_points, next_step_advice, upgrade_vocabulary, or any advice about speaking more."""
    return _call(prompt)


# ─── Part C: Telling a Story ──────────────────────────────────────────────────

def evaluate_part_c(text: str, duration: float, panel_descriptions: list[str]) -> dict:
    """Goal Achievement per panel + 語い・文法 + 流ちょうさ。"""
    wpm = _wpm(text, duration)
    panels = "\n".join(f"  Panel {i+1}: {d}" for i, d in enumerate(panel_descriptions))
    prompt = f"""GTEC Part C – Telling a Story

4-panel comic (what each panel depicts):
{panels}

Student's narration (transcription): "{text}"
Duration: {duration:.1f}s | WPM: {wpm} (ideal 120–150)

=== Goal Achievement per panel (0 or 1 each) ===
1 – Student mentioned the key action/event of that panel
0 – Panel was skipped or its content not conveyed

=== Vocabulary & Grammar (0–4) ===
4 – Excellent; varied vocabulary, accurate grammar
3 – Good; minor errors not affecting meaning
2 – Fair; errors noticeable but meaning generally clear
1 – Poor; frequent errors affecting comprehension
0 – Incomprehensible

=== Fluency & Pronunciation (0–4) ===
{_FLUENCY_LENIENT}
WPM: {wpm}

Return exactly:
{{
  "scores": {{
    "goal_achievement_panel1": <0 or 1>,
    "goal_achievement_panel2": <0 or 1>,
    "goal_achievement_panel3": <0 or 1>,
    "goal_achievement_panel4": <0 or 1>,
    "vocabulary_grammar": <0–4>,
    "fluency_pronunciation": <0–4>
  }},
  "wpm_calculated": {wpm},
  "feedback": {{
    "grammar_corrections": [{{"original": "<phrase or word>", "corrected": "<corrected>", "explanation": "<brief Japanese or empty>"}}]
  }}
}}

grammar_corrections may include both grammar mistakes and awkward word choices / vocabulary improvements.
Only include clear errors. Use an empty array if none.
Do NOT include good_points, next_step_advice, or upgrade_vocabulary."""
    return _call(prompt)


# ─── Part D: Expressing Your Opinion ─────────────────────────────────────────

def evaluate_part_d(text: str, duration: float, topic: str) -> dict:
    """GA1(意見), GA2(理由), 語い・文法, 流ちょうさ の4軸評価。"""
    wpm = _wpm(text, duration)
    prompt = f"""GTEC Part D – Expressing Your Opinion

Topic: "{topic}"
Student's response (transcription): "{text}"
Duration: {duration:.1f}s | WPM: {wpm} (ideal 120–150)

=== Goal Achievement 1 – Opinion (0 or 1) ===
1 – Student clearly stated a personal opinion
0 – No clear opinion expressed

=== Goal Achievement 2 – Reasoning (0, 1, or 2) ===
2 – Provided objective reasoning from a broader societal/general perspective with specific examples
1 – Only gave personal experiences or feelings; no broader/objective perspective
0 – No reasons or examples provided

=== Vocabulary & Grammar (0–4) ===
4 – Excellent; varied, precise vocabulary; accurate grammar
3 – Good; minor errors
2 – Fair; errors noticeable but meaning clear
1 – Poor; frequent errors affecting comprehension
0 – Incomprehensible

=== Fluency & Pronunciation (0–4) ===
{_FLUENCY_LENIENT}
WPM: {wpm}

Return exactly:
{{
  "scores": {{
    "goal_achievement_opinion": <0 or 1>,
    "goal_achievement_reason": <0, 1, or 2>,
    "vocabulary_grammar": <0–4>,
    "fluency_pronunciation": <0–4>
  }},
  "wpm_calculated": {wpm},
  "feedback": {{
    "grammar_corrections": [{{"original": "<phrase or word>", "corrected": "<corrected>", "explanation": "<brief Japanese or empty>"}}]
  }}
}}

grammar_corrections may include both grammar mistakes and awkward word choices / vocabulary improvements.
Only include clear errors. Use an empty array if none.
Do NOT include good_points, next_step_advice, or upgrade_vocabulary."""
    return _call(prompt)
