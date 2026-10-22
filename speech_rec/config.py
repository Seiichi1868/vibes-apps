"""パスと環境変数。永続データは data/speech_rec、音声は後のPRで一時領域。"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent

COOKIE_NAME = "speech_rec_admin"
COOKIE_MAX_AGE = 12 * 60 * 60
SESSION_SALT = "speech-rec-admin-v1"
DEVICE_SALT = "speech-rec-device-v1"
ADMIN_HEADER = "X-Speech-Rec-Request"
MAX_UPLOAD_BYTES = 4 * 1024 * 1024
QUEUE_LIMIT = 60
ERROR_CAP = 6


def data_dir() -> Path:
    raw = (os.environ.get("SPEECH_REC_DATA_DIR") or "").strip()
    if raw:
        return Path(raw)
    return REPO_ROOT / "data" / "speech_rec"


def audio_tmp_dir() -> Path:
    return Path(tempfile.gettempdir()) / "speech_rec_audio"


def openai_api_key() -> str:
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def admin_password() -> str:
    return (os.environ.get("ADMIN_PASSWORD") or "").strip()
