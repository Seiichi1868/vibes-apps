import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_INSECURE_SECRET_KEYS = {
    "",
    "your-secret-key-here",
    "toolbox-dev-secret",
    "speech-rec-dev-secret",
    "local-dev-flask-secret",
}
LOCAL_DEV_SECRET_KEY = "local-dev-flask-secret"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_production_runtime() -> bool:
    if _truthy(os.environ.get("RENDER")):
        return True
    env = (os.environ.get("FLASK_ENV") or os.environ.get("ENV") or "").strip().lower()
    return env == "production"


def resolve_flask_secret_key() -> str:
    """FLASK_SECRET_KEY を返す。本番で未設定・既知の固定値なら起動できない。"""
    key = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
    if is_production_runtime():
        if not key or key in _INSECURE_SECRET_KEYS:
            raise RuntimeError("FLASK_SECRET_KEY が未設定です。本番では起動できません。")
        return key
    if key and key not in {"your-secret-key-here"}:
        return key
    return LOCAL_DEV_SECRET_KEY


class Config:
    """アプリケーション設定"""
    BASE_DIR = BASE_DIR
    SECRET_KEY = LOCAL_DEV_SECRET_KEY

    TEMPLATE_FOLDER = BASE_DIR / "templates"
    STATIC_FOLDER = BASE_DIR / "static"

    UPLOAD_FOLDER = str(BASE_DIR / "uploads")
    AUDIO_CACHE_DIR = BASE_DIR / "static" / "audio"
    ALLOWED_EXTENSIONS = {"webm", "wav", "mp3", "ogg", "m4a"}
    MAX_CONTENT_LENGTH = 150 * 1024 * 1024

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
    OCR_MAX_BYTES = 25 * 1024 * 1024
    GRAMMAR_TIPS_MAX = 8

    @staticmethod
    def init_app(app):
        app.config["SECRET_KEY"] = resolve_flask_secret_key()
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.HISTORY_DIR, exist_ok=True)
        Config.AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
