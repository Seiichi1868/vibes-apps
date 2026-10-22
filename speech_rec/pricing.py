"""評価モデルと文字起こしの単価。

確認日: 2026-10-22
- whisper-1: $0.006 / 分（https://developers.openai.com/api/docs/models/whisper-1）
- gpt-4o-mini: 入力 $0.15 / 出力 $0.60 per 1M tokens
  （https://developers.openai.com/api/docs/models/gpt-4o-mini）
- gpt-5.6-luna / gpt-5.6-terra: 入力 $0.20・$2.00、出力 $1.20・$12.00 per 1M tokens
  （OpenAI 公開価格表と一致。設計書 2.7 の概算もこの単価）
"""
from __future__ import annotations

import math

EVAL_MODELS: dict[str, dict] = {
    "gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60},
    "gpt-5.6-luna": {"input_per_1m": 0.20, "output_per_1m": 1.20},
    "gpt-5.6-terra": {"input_per_1m": 2.00, "output_per_1m": 12.00},
}

WHISPER_PER_MIN_USD = 0.006
WHISPER_MODEL = "whisper-1"
JPY_PER_USD = 150


def estimate_eval_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    entry = EVAL_MODELS[model_id]
    return (max(0, int(input_tokens)) / 1_000_000.0) * float(entry["input_per_1m"]) + (
        max(0, int(output_tokens)) / 1_000_000.0
    ) * float(entry["output_per_1m"])


def estimate_whisper_usd(audio_seconds: float) -> float:
    billed = max(1, math.ceil(float(audio_seconds)))
    return (billed / 60.0) * WHISPER_PER_MIN_USD


def estimate_submission_usd(model_id: str, audio_seconds: float, input_tokens: int, output_tokens: int) -> float:
    return estimate_whisper_usd(audio_seconds) + estimate_eval_usd(model_id, input_tokens, output_tokens)
