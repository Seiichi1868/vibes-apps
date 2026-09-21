"""表示用の背景・オープニング・ナビ情報。Flaskのurl_forだけを使い、他アプリには依存しない。"""
from datetime import datetime, timedelta, timezone

from flask import request, url_for

from conjugate.config import (
    BACKGROUND_PRESETS,
    BACKGROUND_STYLE_LABELS,
    BACKGROUND_STYLE_ORDER,
    DEFAULT_BACKGROUND_OPACITY,
    DEFAULT_OPENING_ENABLED,
    DEFAULT_OPENING_MS,
    resolve_background,
)
from conjugate.storage import load_settings

JST = timezone(timedelta(hours=9))


def appearance_context(settings: dict | None = None) -> dict:
    data = settings if isinstance(settings, dict) else load_settings()
    bg = resolve_background(data.get("background_id"))
    return {
        "appearance": {
            **bg,
            "background_image_url": url_for("conjugate.static", filename=bg["background_image"]),
            "background_opacity": data.get("background_opacity", DEFAULT_BACKGROUND_OPACITY),
            "opening_enabled": bool(data.get("opening_enabled", DEFAULT_OPENING_ENABLED)),
            "opening_ms": int(data.get("opening_ms", DEFAULT_OPENING_MS)),
        },
        "background_presets": {
            key: {**meta, "url": url_for("conjugate.static", filename=meta["image"])}
            for key, meta in BACKGROUND_PRESETS.items()
        },
        "background_style_order": BACKGROUND_STYLE_ORDER,
        "background_style_labels": BACKGROUND_STYLE_LABELS,
        **student_ui_context(),
    }


def student_ui_context() -> dict:
    try:
        path = request.path or ""
    except RuntimeError:
        path = ""
    if "/conjugate/admin" in path:
        nav = "profile"
        show_bottom_nav = False
    elif "/tenses" in path or path.rstrip("/").endswith("/verbs"):
        nav = "verbs"
        show_bottom_nav = True
    elif path.rstrip("/").endswith("/profile") or path.rstrip("/").endswith("/shop"):
        nav = "profile"
        show_bottom_nav = True
    elif "/vocab" in path or "/session/" in path:
        nav = "practice"
        show_bottom_nav = True
    else:
        nav = "home"
        show_bottom_nav = True

    hour = datetime.now(JST).hour
    if 5 <= hour < 11:
        greeting = "おはよう"
    elif 11 <= hour < 18:
        greeting = "こんにちは"
    else:
        greeting = "こんばんは"

    return {
        "nav_active": nav,
        "show_bottom_nav": show_bottom_nav,
        "greeting": greeting,
    }
