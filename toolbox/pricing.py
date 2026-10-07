"""モデル単価の一元管理。値は後で確認して入れる。未設定は 0 扱いにしない。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 生成モデル: 1M トークンあたり USD。既存ディベート定義からコピー（import しない）。
GENERATE_PRICES: dict[str, dict] = {
    "gpt-5.6-luna": {
        "input_per_1m": 0.20,  # TODO: 要確認
        "output_per_1m": 1.20,  # TODO: 要確認
    },
    "gpt-5.6-terra": {
        "input_per_1m": 2.00,  # TODO: 要確認
        "output_per_1m": 12.00,  # TODO: 要確認
    },
    "gpt-5.6-sol": {
        "input_per_1m": 5.00,  # TODO: 要確認
        "output_per_1m": 30.00,  # TODO: 要確認
    },
    "gpt-4o-mini": {
        "input_per_1m": 0.15,  # TODO: 要確認
        "output_per_1m": 0.60,  # TODO: 要確認
    },
    "gpt-5.4-mini": {
        "input_per_1m": 0.40,  # TODO: 要確認
        "output_per_1m": 1.60,  # TODO: 要確認
    },
    "gpt-5.4-nano": {
        "input_per_1m": 0.10,  # TODO: 要確認
        "output_per_1m": 0.40,  # TODO: 要確認
    },
}

# 文字起こし: 1分あたり USD。
TRANSCRIBE_PRICES: dict[str, dict] = {
    "whisper-1": {
        "per_min": 0.006,  # TODO: 要確認
    },
    "gpt-4o-mini-transcribe": {
        "per_min": 0.003,  # TODO: 要確認
    },
    "gpt-4o-transcribe": {
        "per_min": None,  # TODO: 要確認
    },
}


# 埋め込み: 1M トークンあたり USD。
EMBED_PRICES: dict[str, dict] = {
    "text-embedding-3-small": {
        "input_per_1m": 0.02,  # TODO: 要確認
    },
}


def generate_price(model_id: str) -> dict | None:
    return GENERATE_PRICES.get(model_id)


def transcribe_price(model_id: str) -> dict | None:
    return TRANSCRIBE_PRICES.get(model_id)


def embed_price(model_id: str) -> dict | None:
    return EMBED_PRICES.get(model_id)


def has_price(kind: str, model_id: str) -> bool:
    if kind == "transcribe":
        entry = TRANSCRIBE_PRICES.get(model_id) or {}
        return entry.get("per_min") is not None
    if kind == "embed":
        entry = EMBED_PRICES.get(model_id) or {}
        return entry.get("input_per_1m") is not None
    entry = GENERATE_PRICES.get(model_id) or {}
    return entry.get("input_per_1m") is not None and entry.get("output_per_1m") is not None


def estimate_generate_usd(model_id: str, input_tokens: int, output_tokens: int) -> float | None:
    entry = generate_price(model_id)
    if not entry or entry.get("input_per_1m") is None or entry.get("output_per_1m") is None:
        logger.warning("Toolbox: 価格未設定の生成モデルです: %s", model_id)
        return None
    return (input_tokens / 1_000_000.0) * float(entry["input_per_1m"]) + (
        output_tokens / 1_000_000.0
    ) * float(entry["output_per_1m"])


def estimate_embed_usd(model_id: str, input_tokens: int) -> float | None:
    entry = embed_price(model_id)
    if not entry or entry.get("input_per_1m") is None:
        logger.warning("Toolbox: 価格未設定の埋め込みモデルです: %s", model_id)
        return None
    return (max(0, int(input_tokens)) / 1_000_000.0) * float(entry["input_per_1m"])


def estimate_transcribe_usd(model_id: str, audio_seconds: float) -> float | None:
    entry = transcribe_price(model_id)
    if not entry or entry.get("per_min") is None:
        logger.warning("Toolbox: 価格未設定の文字起こしモデルです: %s", model_id)
        return None
    billed_sec = max(1, int(float(audio_seconds) + 0.999999))
    return (billed_sec / 60.0) * float(entry["per_min"])
