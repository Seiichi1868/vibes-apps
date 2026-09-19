"""ジャッジ用AIモデルの単価・性能スコア定義（1箇所で管理）。

価格改定時はこのファイルのみ更新する。画面のバー表示・コスト計算は
debate/judge_models.py がここを参照して動的に算出する。
"""

JUDGE_MODEL_PRICING: dict[str, dict] = {
    "5.6-luna": {
        "label": "gpt-5.6-luna",
        "model": "gpt-5.6-luna",
        "input_price_per_1m": 0.20,
        "output_price_per_1m": 1.20,
        "performance_score": 4,
    },
    "5.6-terra": {
        "label": "gpt-5.6-terra",
        "model": "gpt-5.6-terra",
        "input_price_per_1m": 2.00,
        "output_price_per_1m": 12.00,
        "performance_score": 4,
    },
    "5.6-sol": {
        "label": "gpt-5.6-sol",
        "model": "gpt-5.6-sol",
        "input_price_per_1m": 5.00,
        "output_price_per_1m": 30.00,
        "performance_score": 5,
    },
    "4o-mini": {
        "label": "gpt-4o-mini",
        "model": "gpt-4o-mini",
        "input_price_per_1m": 0.15,
        "output_price_per_1m": 0.60,
        "performance_score": 3,
    },
    "5.4-mini": {
        "label": "gpt-5.4-mini",
        "model": "gpt-5.4-mini",
        "input_price_per_1m": 0.40,
        "output_price_per_1m": 1.60,
        "performance_score": 4,
    },
    "5.4-nano": {
        "label": "gpt-5.4-nano",
        "model": "gpt-5.4-nano",
        "input_price_per_1m": 0.10,
        "output_price_per_1m": 0.40,
        "performance_score": 2,
    },
}

# TTS 単価（Solo Practice の音声生成。二重管理しないこと）
# gpt-4o-mini-tts はトークン課金。tts-1 / tts-1-hd は文字数課金。
TTS_MODEL_PRICING: dict[str, dict] = {
    "gpt-4o-mini-tts": {
        "label": "gpt-4o-mini-tts",
        "model": "gpt-4o-mini-tts",
        "input_price_per_1m": 0.60,
        "output_price_per_1m": 12.00,
        "price_per_1m_chars": None,
        "approx_usd_per_1k_chars": 0.018,
        "notes": "入力トークン + 音声トークン。2100文字・約2分の発話で概算 $0.03–0.05",
    },
    "tts-1": {
        "label": "tts-1",
        "model": "tts-1",
        "input_price_per_1m": None,
        "output_price_per_1m": None,
        "price_per_1m_chars": 15.00,
        "approx_usd_per_1k_chars": 0.015,
        "notes": "1M文字 $15。2100文字で約 $0.032",
    },
    "tts-1-hd": {
        "label": "tts-1-hd",
        "model": "tts-1-hd",
        "input_price_per_1m": None,
        "output_price_per_1m": None,
        "price_per_1m_chars": 30.00,
        "approx_usd_per_1k_chars": 0.030,
        "notes": "1M文字 $30。2100文字で約 $0.063",
    },
}
