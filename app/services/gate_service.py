import datetime
import hashlib
import hmac
import os

from flask import jsonify, request

import app.state as state
from app.config import Config
from app.utils.language_utils import (
    get_default_ui_language,
    get_enabled_study_languages,
    is_tts_enabled,
    languages_response,
)


def _today_date_key() -> str:
    return datetime.date.today().strftime("%Y%m%d")


def is_gate_lock_enabled() -> bool:
    return state.CLASS_CODE_LOCK_ENABLED


def set_gate_lock_enabled(enabled: bool) -> bool:
    state.CLASS_CODE_LOCK_ENABLED = bool(enabled)
    return state.CLASS_CODE_LOCK_ENABLED


def daily_class_code() -> str:
    digest = hashlib.sha256(_today_date_key().encode("utf-8")).hexdigest()
    return str(int(digest[:8], 16) % 10000).zfill(4)


def gate_token_for_today() -> str:
    secret = Config.GATE_SECRET.strip() or os.getenv("OPENAI_API_KEY", "vibespeak-gate")
    digest = hashlib.sha256(f"{secret}:{_today_date_key()}".encode("utf-8")).hexdigest()
    return digest[:24]


def is_valid_gate_token(token: str) -> bool:
    value = (token or "").strip()
    if not value:
        return False
    return hmac.compare_digest(value, gate_token_for_today())


def gate_access_allowed() -> bool:
    if not is_gate_lock_enabled():
        return True
    return is_valid_gate_token(request.headers.get("X-Gate-Token", ""))


def gate_auth_error():
    return jsonify({"error": "class code required", "code": "GATE_REQUIRED"}), 403


def gate_status_payload() -> dict:
    return {
        "lock_enabled": is_gate_lock_enabled(),
        "code": daily_class_code(),
        "tts_enabled": is_tts_enabled(),
        "enabled_languages": get_enabled_study_languages(),
        "languages": languages_response()["languages"],
        "default_ui_language": get_default_ui_language(),
    }
