import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    """アプリケーション設定"""
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "your-secret-key-here")

    TEMPLATE_FOLDER = BASE_DIR / "templates"
    STATIC_FOLDER = BASE_DIR / "static"

    UPLOAD_FOLDER = str(BASE_DIR / "uploads")
    AUDIO_CACHE_DIR = BASE_DIR / "static" / "audio"
    ALLOWED_EXTENSIONS = {"webm", "wav", "mp3", "ogg", "m4a"}
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    GATE_SECRET = os.environ.get("GATE_SECRET", "")

    HISTORY_DIR = BASE_DIR / "learning_history"
    MAX_HISTORY_ITEMS = 100

    MODEL_ECONOMY = "gpt-4o-mini"
    OCR_MODEL = MODEL_ECONOMY
    DEFAULT_AI_MODE = "4o-mini"
    PREMIUM_MAX_COMPLETION_TOKENS = 4096
    PREMIUM_REASONING_EFFORT = "low"

    TTS_MODEL = "tts-1"
    TTS_DEFAULT_LANG = "en-US"

    OCR_ALLOWED_MIME = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }
    OCR_MIME_BY_EXT = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    OCR_MAX_BYTES = 10 * 1024 * 1024
    GRAMMAR_TIPS_MAX = 8

    @staticmethod
    def init_app(app):
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.HISTORY_DIR, exist_ok=True)
        Config.AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
