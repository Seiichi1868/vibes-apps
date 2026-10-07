"""未付与のお題へ難易度・日本語訳・テーマ・配慮をまとめて付ける。"""
from __future__ import annotations

import json
import logging
import math
import threading

from toolbox.pricing import estimate_generate_usd
from toolbox.tools.minute_speech.topics import apply_ai_rows, classification_count, pending_classification
from toolbox.usage import UsageError, UsageLimitError, generate_json, selected_model

logger = logging.getLogger(__name__)

TOOL_ID = "minute-speech"
_lock = threading.Lock()
_job = {"running": False, "done": 0, "total": 0, "error": ""}


def estimate() -> dict:
    count = classification_count()
    batches = math.ceil(count / 20) if count else 0
    try:
        model_id = selected_model("generate")
    except UsageError as exc:
        return {"count": count, "batches": batches, "est_cost_usd": None, "error": exc.message, "model": None}
    input_tokens = batches * (500 + 20 * 50)
    output_tokens = batches * (20 * 90)
    cost = estimate_generate_usd(model_id, input_tokens, output_tokens)
    return {
        "count": count,
        "batches": batches,
        "model": model_id,
        "est_cost_usd": None if cost is None else round(cost, 4),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def _prompt(topics: list[dict]) -> list[dict]:
    payload = [{"id": topic["id"], "type": topic.get("type"), "text": topic.get("text")} for topic in topics]
    return [
        {
            "role": "system",
            "content": (
                "高校の英語授業向けに、スピーチお題を分類する。"
                "JSONオブジェクトだけを返す。形式は "
                '{"items":[{"id":"","level":1,"ja":"","sensitive":false,"sensitive_reason":"","themes":["学校"]}]}。'
                "level は 1（高校生が1分の準備で具体的に話せる身近な話題）、"
                "2（標準。やや抽象的、語彙に配慮が必要）、"
                "3（難しい。社会問題・抽象的・大人前提・長文）。"
                "ja は自然な日本語訳。sensitive は死・自殺、犯罪、性、宗教、戦争など授業に不向きなら true。"
                "themes は学校、趣味、社会などの短いタグを1〜3個。"
            ),
        },
        {"role": "user", "content": json.dumps({"items": payload}, ensure_ascii=False)},
    ]


def _parse(content: str) -> list[dict]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1]
    data = json.loads(text)
    rows = data.get("items") if isinstance(data, dict) else data
    return rows if isinstance(rows, list) else []


def run_batch(user_id: str) -> dict:
    batch = pending_classification(20)
    if not batch:
        return {"applied": 0, "remaining": 0}
    _raw, content = generate_json(
        messages=_prompt(batch),
        user_id=user_id,
        tool_id=TOOL_ID,
        temperature=0.2,
        max_tokens=2500,
    )
    applied = apply_ai_rows(_parse(content))
    return {"applied": applied, "remaining": classification_count()}


def _run(user_id: str) -> None:
    try:
        _job["total"] = classification_count()
        _job["done"] = 0
        while True:
            before = classification_count()
            if before <= 0:
                break
            result = run_batch(user_id)
            if result["applied"] <= 0:
                _job["error"] = "分類結果を保存できませんでした。"
                break
            _job["done"] = _job["total"] - result["remaining"]
            if result["remaining"] >= before:
                _job["error"] = "分類が進みませんでした。"
                break
    except (UsageError, UsageLimitError, json.JSONDecodeError) as exc:
        message = getattr(exc, "message", None) or "分類に失敗しました。"
        _job["error"] = message
        logger.warning("minute speech classify stopped: %s", exc)
    except Exception as exc:
        _job["error"] = "分類に失敗しました。"
        logger.exception("minute speech classify failed: %s", exc)
    finally:
        _job["running"] = False


def start(user_id: str) -> dict:
    with _lock:
        if _job["running"]:
            return {"started": False, **status()}
        _job.update({"running": True, "done": 0, "total": classification_count(), "error": ""})
    threading.Thread(target=_run, args=(user_id,), daemon=True).start()
    return {"started": True, **status()}


def status() -> dict:
    return {
        "running": _job["running"],
        "done": _job["done"],
        "total": _job["total"],
        "error": _job["error"],
        "remaining": classification_count(),
    }
