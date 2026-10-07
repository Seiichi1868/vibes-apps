"""文字起こし／生成モデルの候補。既存アプリは import せず、必要な項目をコピー。"""
from __future__ import annotations

from copy import deepcopy

from toolbox.pricing import EMBED_PRICES, GENERATE_PRICES, TRANSCRIBE_PRICES, has_price
from toolbox.storage import load_app_settings

# 性能スコアは既存ディベート／音読の参考値に合わせた目安。画面では「参考値」と明示する。
MODEL_CATALOG: list[dict] = [
    {
        "id": "whisper-1",
        "label": "Whisper-1",
        "kind": "transcribe",
        "quality_score": 5,
        "quality_note": "高精度。固有名詞や早口でも比較的安定。",
        "speed_note": "標準。数分の音声で数十秒かかることがある。",
        "last_verified": "2026-10-04",
    },
    {
        "id": "gpt-4o-mini-transcribe",
        "label": "GPT-4o-mini-transcribe",
        "kind": "transcribe",
        "quality_score": 3,
        "quality_note": "軽量。短い発話向き。長いスピーチは精度が落ちることがある。",
        "speed_note": "速い。",
        "last_verified": "2026-10-04",
    },
    {
        "id": "gpt-4o-transcribe",
        "label": "GPT-4o-transcribe",
        "kind": "transcribe",
        "quality_score": 4,
        "quality_note": "標準〜上位。価格未確認のため選択不可。",
        "speed_note": "標準。",
        "last_verified": "2026-10-04",
    },
    {
        "id": "gpt-4o-mini",
        "label": "gpt-4o-mini",
        "kind": "generate",
        "quality_score": 3,
        "quality_note": "軽量。短い理解確認問題向き。複雑な推論は弱い。",
        "speed_note": "速い。",
        "last_verified": "2026-10-04",
    },
    {
        "id": "gpt-5.4-nano",
        "label": "gpt-5.4-nano",
        "kind": "generate",
        "quality_score": 2,
        "quality_note": "最軽量。単純な事実問題向き。",
        "speed_note": "速い。",
        "last_verified": "2026-10-04",
    },
    {
        "id": "gpt-5.4-mini",
        "label": "gpt-5.4-mini",
        "kind": "generate",
        "quality_score": 4,
        "quality_note": "標準。語彙調整と時系列の整理が安定しやすい。",
        "speed_note": "標準。",
        "last_verified": "2026-10-04",
    },
    {
        "id": "gpt-5.6-luna",
        "label": "gpt-5.6-luna",
        "kind": "generate",
        "quality_score": 4,
        "quality_note": "標準〜上位。授業用途のコスパが良い目安。",
        "speed_note": "標準。",
        "last_verified": "2026-10-04",
    },
    {
        "id": "gpt-5.6-terra",
        "label": "gpt-5.6-terra",
        "kind": "generate",
        "quality_score": 4,
        "quality_note": "上位寄り。長い文字起こしでも崩れにくい目安。",
        "speed_note": "やや遅い。",
        "last_verified": "2026-10-04",
    },
    {
        "id": "gpt-5.6-sol",
        "label": "gpt-5.6-sol",
        "kind": "generate",
        "quality_score": 5,
        "quality_note": "上位。推論問題を含むとき向き。費用は高め。",
        "speed_note": "遅いことがある。",
        "last_verified": "2026-10-04",
    },
    {
        "id": "text-embedding-3-small",
        "label": "text-embedding-3-small",
        "kind": "embed",
        "quality_score": 4,
        "quality_note": "1分スピーチのお題検索用。短い検索語をベクトル化する。",
        "speed_note": "速い。全件のインデックス作成は件数分かかる。",
        "last_verified": "2026-10-07",
    },
]


def _base_entry(model_id: str) -> dict | None:
    for entry in MODEL_CATALOG:
        if entry["id"] == model_id:
            return deepcopy(entry)
    return None


def resolved_catalog(kind: str | None = None) -> list[dict]:
    overrides = load_app_settings().get("model_overrides") or {}
    rows = []
    for entry in MODEL_CATALOG:
        if kind and entry["kind"] != kind:
            continue
        row = deepcopy(entry)
        extra = overrides.get(row["id"]) or {}
        if isinstance(extra, dict):
            if extra.get("quality_score") is not None:
                try:
                    score = int(extra["quality_score"])
                    if 1 <= score <= 5:
                        row["quality_score"] = score
                except (TypeError, ValueError):
                    pass
            if extra.get("quality_note"):
                row["quality_note"] = str(extra["quality_note"])
            if extra.get("speed_note"):
                row["speed_note"] = str(extra["speed_note"])
            if extra.get("last_verified"):
                row["last_verified"] = str(extra["last_verified"])
        row["priced"] = has_price(row["kind"], row["id"])
        if row["kind"] == "transcribe":
            price = TRANSCRIBE_PRICES.get(row["id"]) or {}
            row["price"] = {"per_min": price.get("per_min")}
        elif row["kind"] == "embed":
            price = EMBED_PRICES.get(row["id"]) or {}
            row["price"] = {"input_per_1m": price.get("input_per_1m")}
        else:
            price = GENERATE_PRICES.get(row["id"]) or {}
            row["price"] = {
                "input_per_1m": price.get("input_per_1m"),
                "output_per_1m": price.get("output_per_1m"),
            }
        rows.append(row)
    return rows


def get_model(model_id: str) -> dict | None:
    for row in resolved_catalog():
        if row["id"] == model_id:
            return row
    return _base_entry(model_id)
