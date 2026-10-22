"""QR の PNG data URI。リンクは常に https://vibes-lab.com。"""
from __future__ import annotations

import segno

PUBLIC_ORIGIN = "https://vibes-lab.com"


def student_url(token: str) -> str:
    return f"{PUBLIC_ORIGIN}/rec/{token}"


def qr_data_uri(url: str) -> str:
    return segno.make(url, error="m").png_data_uri(scale=10, border=3)
