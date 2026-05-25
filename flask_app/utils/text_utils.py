import re
from difflib import SequenceMatcher


def calculate_similarity(text1: str, text2: str) -> float:
    """2つのテキストの類似度を計算（0〜100）"""
    text1 = re.sub(r"\s+", "", text1.lower())
    text2 = re.sub(r"\s+", "", text2.lower())
    similarity = SequenceMatcher(None, text1, text2).ratio()
    return similarity * 100


def clean_ocr_text(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()
