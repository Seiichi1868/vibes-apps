"""OpenAI 呼び出しと利用量・上限。他アプリの usage は import しない。"""
from __future__ import annotations

import logging
import time
from datetime import datetime

from toolbox.config import (
    GENERATE_MAX_RETRIES,
    GENERATE_TIMEOUT_SEC,
    WHISPER_MAX_RETRIES,
    WHISPER_TIMEOUT_SEC,
    get_openai_api_key,
)
from toolbox.model_catalog import resolved_catalog
from toolbox.openai_http import OpenAIHttpError, chat_completions
from toolbox.pricing import estimate_generate_usd, estimate_transcribe_usd, has_price
from toolbox.storage import append_usage, get_setting, list_usage, now_dt

logger = logging.getLogger(__name__)


class UsageLimitError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UsageError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _today_key(dt: datetime | None = None) -> str:
    current = dt or now_dt()
    return current.strftime("%Y-%m-%d")


def _month_key(dt: datetime | None = None) -> str:
    current = dt or now_dt()
    return current.strftime("%Y-%m")


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def today_cost_usd() -> float:
    key = _today_key()
    total = 0.0
    for row in list_usage():
        dt = _parse_ts(row.get("ts"))
        if not dt or dt.strftime("%Y-%m-%d") != key:
            continue
        if row.get("kind") not in ("transcribe", "llm"):
            continue
        try:
            total += float(row.get("est_cost_usd") or 0)
        except (TypeError, ValueError):
            continue
    return total


def check_daily_limit() -> None:
    limit = float(get_setting("daily_limit_usd") or 0)
    if limit <= 0:
        return
    used = today_cost_usd()
    if used >= limit:
        raise UsageLimitError(
            f"本日の利用上限（約 ${limit:.2f}）に達しました。管理画面の設定から上限を変更できます。"
        )


def selected_model(kind: str) -> str:
    key = "transcribe_model" if kind == "transcribe" else "generate_model"
    model_id = str(get_setting(key) or "")
    catalog = {row["id"]: row for row in resolved_catalog(kind)}
    if model_id in catalog and catalog[model_id]["priced"]:
        return model_id
    for row in resolved_catalog(kind):
        if row["priced"]:
            return row["id"]
    raise UsageError("利用できるモデルがありません。管理画面で価格が設定されたモデルを選んでください。")


def _client(timeout: float, retries: int):
    api_key = get_openai_api_key()
    if not api_key:
        raise UsageError("OpenAI の API キーが設定されていません。管理者に連絡してください。")
    from openai import OpenAI

    return OpenAI(api_key=api_key, timeout=timeout, max_retries=retries)


def record_event(user_id: str, tool_id: str, name: str, extra: dict | None = None) -> None:
    entry = {
        "user_id": user_id,
        "tool_id": tool_id,
        "kind": "event",
        "model": name,
        "audio_seconds": None,
        "input_tokens": None,
        "output_tokens": None,
        "est_cost_usd": 0,
        "latency_ms": None,
    }
    if extra:
        entry.update(extra)
    append_usage(entry)


def transcribe_file(
    *,
    file_path,
    duration_sec: float,
    keywords: str,
    user_id: str,
    tool_id: str,
) -> str:
    check_daily_limit()
    model_id = selected_model("transcribe")
    if not has_price("transcribe", model_id):
        raise UsageError("選択中の文字起こしモデルは価格未設定のため使えません。")
    client = _client(WHISPER_TIMEOUT_SEC, WHISPER_MAX_RETRIES)
    prompt = (keywords or "").strip()
    started = time.monotonic()
    try:
        with open(file_path, "rb") as audio_file:
            kwargs = {
                "model": model_id,
                "file": audio_file,
                "language": "en",
            }
            if prompt:
                kwargs["prompt"] = prompt
            result = client.audio.transcriptions.create(**kwargs)
    except UsageLimitError:
        raise
    except Exception as exc:
        logger.exception("Toolbox transcribe failed: %s", exc)
        raise UsageError("文字起こしに失敗しました。通信を確認して、もう一度送るかテキスト貼り付けを使ってください。") from exc
    latency_ms = int((time.monotonic() - started) * 1000)
    text = (getattr(result, "text", "") or "").strip()
    cost = estimate_transcribe_usd(model_id, duration_sec)
    if cost is None:
        raise UsageError("文字起こしモデルの価格が未設定です。管理画面で別のモデルを選んでください。")
    append_usage(
        {
            "user_id": user_id,
            "tool_id": tool_id,
            "kind": "transcribe",
            "model": model_id,
            "audio_seconds": float(duration_sec or 0),
            "input_tokens": None,
            "output_tokens": None,
            "est_cost_usd": round(cost, 6),
            "latency_ms": latency_ms,
        }
    )
    return text


def _is_reasoning_model(model: str) -> bool:
    name = (model or "").strip().lower()
    if name.startswith("gpt-5") and "chat" not in name:
        return True
    return name.startswith(("o1", "o3", "o4"))


def generate_json(
    *,
    messages: list[dict],
    user_id: str,
    tool_id: str,
    temperature: float = 0.25,
) -> tuple[dict, str]:
    check_daily_limit()
    model_id = selected_model("generate")
    if not has_price("generate", model_id):
        raise UsageError("選択中の生成モデルは価格未設定のため使えません。")
    started = time.monotonic()
    try:
        raw = chat_completions(
            model=model_id,
            messages=messages,
            temperature=None if _is_reasoning_model(model_id) else temperature,
            timeout=GENERATE_TIMEOUT_SEC,
            reasoning=_is_reasoning_model(model_id),
        )
    except UsageLimitError:
        raise
    except OpenAIHttpError as exc:
        logger.exception("Toolbox generate failed: %s", exc)
        raise UsageError("問題の作成に失敗しました。もう一度試してください。") from exc
    latency_ms = int((time.monotonic() - started) * 1000)
    usage = raw.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    cost = estimate_generate_usd(model_id, input_tokens, output_tokens)
    if cost is None:
        raise UsageError("生成モデルの価格が未設定です。管理画面で別のモデルを選んでください。")
    append_usage(
        {
            "user_id": user_id,
            "tool_id": tool_id,
            "kind": "llm",
            "model": model_id,
            "audio_seconds": None,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "est_cost_usd": round(cost, 6),
            "latency_ms": latency_ms,
        }
    )
    content = ""
    choices = raw.get("choices") or []
    if choices:
        content = ((choices[0].get("message") or {}).get("content") or "").strip()
    return raw, content


def usage_summary() -> dict:
    today = _today_key()
    month = _month_key()
    rows = [row for row in list_usage() if row.get("kind") in ("transcribe", "llm")]
    def _bucket(predicate):
        items = [row for row in rows if predicate(row)]
        return {
            "count": len(items),
            "est_cost_usd": round(sum(float(row.get("est_cost_usd") or 0) for row in items), 4),
        }

    def _by(key, predicate):
        grouped: dict[str, dict] = {}
        for row in rows:
            if not predicate(row):
                continue
            name = str(row.get(key) or "unknown")
            bucket = grouped.setdefault(name, {"count": 0, "est_cost_usd": 0.0})
            bucket["count"] += 1
            bucket["est_cost_usd"] += float(row.get("est_cost_usd") or 0)
        return {
            name: {"count": value["count"], "est_cost_usd": round(value["est_cost_usd"], 4)}
            for name, value in grouped.items()
        }

    def _in_day(row, key):
        dt = _parse_ts(row.get("ts"))
        return bool(dt and dt.strftime("%Y-%m-%d") == key)

    def _in_month(row, key):
        dt = _parse_ts(row.get("ts"))
        return bool(dt and dt.strftime("%Y-%m") == key)

    return {
        "today": _bucket(lambda row: _in_day(row, today)),
        "month": _bucket(lambda row: _in_month(row, month)),
        "by_user_today": _by("user_id", lambda row: _in_day(row, today)),
        "by_user_month": _by("user_id", lambda row: _in_month(row, month)),
        "by_tool_today": _by("tool_id", lambda row: _in_day(row, today)),
        "by_tool_month": _by("tool_id", lambda row: _in_month(row, month)),
        "daily_limit_usd": float(get_setting("daily_limit_usd") or 0),
        "used_today_usd": round(today_cost_usd(), 4),
    }


def measured_stats(model_id: str, kind: str) -> dict:
    mapped = "transcribe" if kind == "transcribe" else "llm"
    rows = [row for row in list_usage() if row.get("model") == model_id and row.get("kind") == mapped]
    if len(rows) < 3:
        return {"n": len(rows), "avg_latency_ms": None, "avg_cost_usd": None}
    latencies = [int(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None]
    costs = [float(row.get("est_cost_usd") or 0) for row in rows]
    return {
        "n": len(rows),
        "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else None,
        "avg_cost_usd": round(sum(costs) / len(costs), 6) if costs else None,
    }
