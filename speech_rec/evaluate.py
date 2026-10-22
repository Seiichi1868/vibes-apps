"""3項目と OREO だけを AI に聞く。Delivery は聞かない。本文はログに出さない。"""
from __future__ import annotations

import json

from speech_rec.openai_client import SpeechRecAIError, chat_json
from speech_rec.pricing import estimate_eval_usd
from speech_rec.rubric import PROMPT_VERSION, descriptor_text
from speech_rec.scoring import clamp_level
from speech_rec.usage import record_cost

SYSTEM = """あなたは日本の高校の英語スピーキング評価の採点補助者です。
生徒が「準備1分→スピーチ1分」で話した英語を、音声認識（Whisper）の文字起こしをもとに、ルーブリックで評価します。

【課題】
お題について、OREO形式（Opinion → Reason → Example → Opinion）で、1分間、論理的に述べる。

【前提（必ず守る）】
- transcript は音声認識の結果。大文字小文字・句読点・綴りの揺れは生徒の誤りとして扱わない。
- 音声は聞けない。発音と流暢さ（間・フィラー・速さ）は評価しない（別の仕組みが採点する）。
- 迷ったときは、文字起こしに証拠がある範囲で生徒に有利に解釈する。証拠のない加点はしない。
- 引用（evidence）は transcript からそのまま抜き出し、12語以内にする。見つからなければ空文字。

【手順】
1. transcript を文に分け、各文に role を付ける。
   role = opinion | reason | example | elaboration | transition | filler_or_repair | off_topic | other
2. OREOの4要素 opinion_open / reason / example / opinion_close について、
   present(true/false) と evidence を出す。opinion_close は、終わりの部分で最初の主張に戻れているか。
3. on_topic：お題に答えているか(true/false)。
4. 次の3項目を level 1〜6 の整数で採点する（1が最低、6が最高）。レベルと点数の対応は 1=10, 2=20, 3=25, 4=30, 5=35, 6=40。
   - general_description：理由・説明の十分さ、主張を支える文（reason/example/elaboration）の割合。OREOの Reason と Example を主に反映する。
   - language_use：文法・語彙・表現の正確さと幅。誤りでメッセージが分かりにくくなるかどうかを重視する。
   - topic_development：序論・本論・結論の構成、つなぎ言葉の使い方。OREOの opinion_open / opinion_close と全体の流れを主に反映する。
5. 生徒向けに、日本語で、各項目の comment（1文）、strength（良かった点1文）、next_step（次に直すとよい点を具体的に40字以内）を書く。

【ルーブリック（各レベルの記述）】
{{RUBRIC_DESCRIPTORS}}

【採点の例】
{{ANCHOR_EXAMPLES}}

【出力】次のJSONだけを返す。前置き・コードブロック・説明は書かない。
{
  "on_topic": true,
  "oreo": {
    "opinion_open":  {"present": true, "evidence": ""},
    "reason":        {"present": true, "evidence": ""},
    "example":       {"present": true, "evidence": ""},
    "opinion_close": {"present": true, "evidence": ""}
  },
  "sentences": [{"text": "", "role": "opinion"}],
  "levels": {
    "general_description": {"level": 1, "comment": ""},
    "language_use":        {"level": 1, "comment": ""},
    "topic_development":   {"level": 1, "comment": ""}
  },
  "student_feedback": {"strength": "", "next_step": ""}
}
"""


def system_prompt() -> str:
    return SYSTEM.replace("{{RUBRIC_DESCRIPTORS}}", descriptor_text()).replace("{{ANCHOR_EXAMPLES}}", "")


def support_ratio(sentences: list) -> float:
    useful = [row for row in sentences if isinstance(row, dict) and row.get("role") != "filler_or_repair"]
    if not useful:
        return 0.0
    supported = sum(1 for row in useful if row.get("role") in {"reason", "example", "elaboration"})
    return supported / len(useful)


def interpret(payload: dict, *, words_counted: int) -> dict:
    """AIのJSONを数値と、一時表示用の本文に分ける。"""
    levels_in = payload.get("levels") if isinstance(payload.get("levels"), dict) else {}
    levels = {}
    comments = {}
    for key in ("general_description", "language_use", "topic_development"):
        raw = levels_in.get(key)
        if isinstance(raw, dict):
            levels[key] = clamp_level(raw.get("level"))
            comments[key] = str(raw.get("comment") or "")[:400]
        else:
            levels[key] = clamp_level(raw)
            comments[key] = ""
    oreo_in = payload.get("oreo") if isinstance(payload.get("oreo"), dict) else {}
    oreo = {}
    evidence = {}
    for key in ("opinion_open", "reason", "example", "opinion_close"):
        item = oreo_in.get(key) if isinstance(oreo_in.get(key), dict) else {}
        oreo[key] = bool(item.get("present"))
        evidence[key] = str(item.get("evidence") or "")[:200]
    sentences = payload.get("sentences") if isinstance(payload.get("sentences"), list) else []
    ratio = support_ratio(sentences)
    feedback = payload.get("student_feedback") if isinstance(payload.get("student_feedback"), dict) else {}
    flags = []
    gd = levels["general_description"]
    if (ratio < 0.4 and gd >= 5) or (ratio > 0.7 and gd <= 2):
        flags.append("check_general_description")
    if not oreo["opinion_open"]:
        flags.append("no_open")
    if not oreo["example"]:
        flags.append("no_example")
    if not oreo["opinion_close"]:
        flags.append("no_close")
    if not bool(payload.get("on_topic", True)):
        flags.append("off_topic")
    if words_counted < 30:
        flags.append("short_speech")
    return {
        "on_topic": bool(payload.get("on_topic", True)),
        "levels": levels,
        "oreo": oreo,
        "flags": flags,
        "support_ratio": round(ratio, 4),
        "view": {
            "comments": comments,
            "evidence": evidence,
            "sentences": sentences,
            "student_feedback": {
                "strength": str(feedback.get("strength") or "")[:200],
                "next_step": str(feedback.get("next_step") or "")[:40],
            },
            "support_ratio": round(ratio, 4),
        },
    }


def _bill(model: str, usage: dict) -> float:
    cost = estimate_eval_usd(model, int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0))
    record_cost(cost, kind="eval", model=model)
    return cost


def run_eval(topic: str, transcript: str, speak_sec: int, model: str, *, words_counted: int) -> dict:
    user = json.dumps({"topic": topic, "transcript": transcript, "speak_sec": speak_sec}, ensure_ascii=False)
    system = system_prompt()
    content, usage = chat_json(model, system, user, max_tokens=1200)
    cost = _bill(model, usage)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        content, usage = chat_json(model, system, user, max_tokens=1200)
        cost += _bill(model, usage)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise SpeechRecAIError("eval_failed") from exc
    if not isinstance(payload, dict):
        raise SpeechRecAIError("eval_failed")
    parsed = interpret(payload, words_counted=words_counted)
    parsed["cost_usd"] = round(cost, 6)
    parsed["model"] = model
    parsed["prompt_version"] = PROMPT_VERSION
    return parsed
