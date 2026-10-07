"""Toolbox 設定。他アプリは import しない。

データは data/toolbox/ 配下の JSON に永続化する（既存アプリと同じ方式。
Render のディスクマウント `/opt/render/project/src/data` を想定）。
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(
    os.environ.get("TOOLBOX_DATA_DIR", str(PROJECT_ROOT / "data" / "toolbox"))
).expanduser()

USERS_FILE = DATA_DIR / "users.json"
LOGIN_ATTEMPTS_FILE = DATA_DIR / "login_attempts.json"
TOOL_SETTINGS_FILE = DATA_DIR / "tool_settings.json"
FAVORITES_FILE = DATA_DIR / "user_favorites.json"
RECENT_TOOLS_FILE = DATA_DIR / "user_recent_tools.json"
CLASSES_FILE = DATA_DIR / "classes.json"
APP_SETTINGS_FILE = DATA_DIR / "app_settings.json"
USAGE_LOG_FILE = DATA_DIR / "usage_log.json"
TALK_SESSIONS_DIR = DATA_DIR / "talk_sessions"
AUDIO_TMP_DIR = DATA_DIR / "audio_tmp"
TALK_AUDIO_DIR = DATA_DIR / "talk_audio"
MINUTE_SPEECH_OVERLAY_FILE = DATA_DIR / "minute_speech_overlay.json"
MINUTE_SPEECH_EMBEDDINGS_FILE = DATA_DIR / "minute_speech_embeddings.json"
MINUTE_SPEECH_SEED_FILE = Path(__file__).resolve().parent / "data" / "minute_speech_topics_seed.json"

COOKIE_NAME = "toolbox_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 14
ADMIN_REAUTH_SEC = 15 * 60
LOCK_WINDOW_SEC = 15 * 60
LOCK_MAX_FAILURES = 5
LOCK_DURATION_SEC = 15 * 60
MIN_PASSWORD_LEN = 4

SESSION_SALT = "toolbox-session-v1"

MAX_AUDIO_BYTES = 25 * 1024 * 1024
ALLOWED_AUDIO_EXTENSIONS = {"webm", "wav", "mp3", "m4a", "ogg", "mp4", "mpeg", "mpga"}
WHISPER_TIMEOUT_SEC = float(os.environ.get("TOOLBOX_WHISPER_TIMEOUT_SEC", "90"))
WHISPER_MAX_RETRIES = int(os.environ.get("TOOLBOX_WHISPER_MAX_RETRIES", "1"))
GENERATE_TIMEOUT_SEC = float(os.environ.get("TOOLBOX_GENERATE_TIMEOUT_SEC", "90"))
GENERATE_MAX_RETRIES = int(os.environ.get("TOOLBOX_GENERATE_MAX_RETRIES", "0"))

DEFAULT_DAILY_LIMIT_USD = 3.0
DEFAULT_ASSUME_TRANSCRIBE_SEC = 180
DEFAULT_ASSUME_INPUT_TOKENS = 1500
DEFAULT_ASSUME_OUTPUT_TOKENS = 800

DEFAULT_TRANSCRIBE_MODEL = "whisper-1"
DEFAULT_GENERATE_MODEL = "gpt-4o-mini"
DEFAULT_EMBED_MODEL = "text-embedding-3-small"
DEFAULT_PARALLEL_BROWSER_STT = True
DEFAULT_LOGIN_REQUIRED = False

# 管理画面の入口（他アプリの 2479 と同じ運用）。環境変数で上書き可。
ADMIN_PANEL_PASSWORD = os.environ.get("TOOLBOX_ADMIN_PASSWORD", "2479")


def get_openai_api_key() -> str:
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def get_secret_key() -> str:
    return (os.environ.get("FLASK_SECRET_KEY") or "").strip()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TALK_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_TMP_DIR.mkdir(parents=True, exist_ok=True)
    TALK_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
