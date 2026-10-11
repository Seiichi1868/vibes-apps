"""観戦用 TTS の単価。

OpenAI 公式（gpt-4o-mini-tts）:
- テキスト入力 $0.60 / 1M tokens
- 音声出力 $12 / 1M tokens
実務上の目安は約 $0.015 / 分（2026年の公式料金ページ）。
応答に usage が無いときは、この分単価で概算する。
"""

SPEECH_INPUT_USD_PER_1M = 0.60
SPEECH_OUTPUT_USD_PER_1M = 12.00
SPEECH_USD_PER_MINUTE = 0.015
SPEECH_WORDS_PER_MINUTE = 140


def cost_from_usage(input_tokens: int, output_tokens: int) -> float:
    return round(
        (max(input_tokens, 0) * SPEECH_INPUT_USD_PER_1M / 1_000_000)
        + (max(output_tokens, 0) * SPEECH_OUTPUT_USD_PER_1M / 1_000_000),
        6,
    )


def estimate_cost_usd(text: str) -> float:
    words = len([w for w in (text or "").split() if w])
    minutes = max(words, 1) / SPEECH_WORDS_PER_MINUTE
    return round(minutes * SPEECH_USD_PER_MINUTE, 6)
