"""News と同じ segno 設定で QR の PNG data URI を作る。"""
from __future__ import annotations

from urllib.parse import urlsplit

import segno

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_SCHEMES = {
    "javascript",
    "data",
    "vbscript",
    "file",
    "about",
    "blob",
    "mailto",
    "ftp",
}
MAX_URL_LEN = 2048


def _declared_scheme(text: str) -> str | None:
    """`javascript:…` は拒否し、`localhost:5001/…` のようなホスト:ポートはスキームと見なさない。"""
    if "://" in text:
        return text.split("://", 1)[0].lower()
    head, sep, rest = text.partition(":")
    if not sep or not rest or "/" in head:
        return None
    scheme = head.lower()
    if scheme in ALLOWED_SCHEMES or scheme in BLOCKED_SCHEMES:
        return scheme
    return None


def normalize_url(raw: str) -> tuple[str | None, str | None]:
    """貼り付けやすいよう前後の空白・引用符を落とし、スキームが無ければ https を付ける。"""
    text = (raw or "").replace("\u200b", "").replace("\ufeff", "").strip()
    if text:
        text = text.splitlines()[0].strip()
    text = text.strip("<>\"' \t")
    if not text:
        return None, "URLを入力してください。"
    scheme = _declared_scheme(text)
    if scheme and scheme not in ALLOWED_SCHEMES:
        return None, "http または https のURLだけ使えます。"
    if scheme not in ALLOWED_SCHEMES:
        text = "https://" + text
    if len(text) > MAX_URL_LEN:
        return None, "URLが長すぎます。"
    try:
        parsed = urlsplit(text)
    except ValueError:
        return None, "URLの形式が正しくありません。"
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return None, "http または https のURLだけ使えます。"
    if not parsed.netloc:
        return None, "URLの形式が正しくありません。"
    return text, None


def png_data_uri(link: str) -> str:
    """News の教室スクリーン QR と同じ error=m / scale=10 / border=3。"""
    return segno.make(link, error="m").png_data_uri(scale=10, border=3)
