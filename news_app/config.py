import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = Path(os.environ.get("NEWS_DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser()
STATE_FILE = DATA_DIR / "app_state.json"
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"


def ensure_env_file() -> None:
    if not ENV_FILE.exists() and ENV_EXAMPLE.exists():
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")


def load_environment() -> None:
    ensure_env_file()
    load_dotenv(ENV_FILE, override=False)


load_environment()

DEFAULT_AI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
DEFAULT_TRANSCRIPT_AI_MODEL = os.environ.get("NEWS_TRANSCRIPT_AI_MODEL", "gpt-5.6-sol")

CEFR_LEVELS = ("A1", "A2", "B1", "B2")
DEFAULT_CEFR_LEVEL = "A2"
VOCAB_CEFR_LEVELS = ("C2", "C1", "B2", "B1")
VOCAB_EXTRACTION_TARGET = 30
VOCAB_EXTRACTION_MIN = 25
VOCAB_EXTRACTION_MAX = 30
VOCAB_STORAGE_MAX = 50
VOCABULARY_EXTRACTION_MODEL = "gpt-5.6-luna"
DISPLAY_LANGUAGES = ("ja", "en", "es")
_DISPLAY_LANGUAGE_ALIASES = {
    "ja": "ja",
    "jp": "ja",
    "japanese": "ja",
    "日本語": "ja",
    "en": "en",
    "english": "en",
    "es": "es",
    "spanish": "es",
    "español": "es",
    "espanol": "es",
}


def resolve_display_language(value: str | None = None, *, fallback: str = "ja") -> str:
    """管理設定の表示言語。未対応値は fallback（既定は日本語）へ寄せる。"""
    raw = str(value or "").strip().lower()
    lang = _DISPLAY_LANGUAGE_ALIASES.get(raw)
    if lang in DISPLAY_LANGUAGES:
        return lang
    fb = _DISPLAY_LANGUAGE_ALIASES.get(str(fallback or "").strip().lower(), "ja")
    return fb if fb in DISPLAY_LANGUAGES else "ja"


AI_MODELS = (
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-5.4-mini",
    "gpt-4o-mini",
    "gpt-5.4-nano",
)

WHISPER_MODEL = os.environ.get("NEWS_WHISPER_MODEL", "whisper-1")
WHISPER_TIMEOUT_SEC = float(os.environ.get("NEWS_WHISPER_TIMEOUT_SEC", "60"))
WHISPER_MAX_RETRIES = int(os.environ.get("NEWS_WHISPER_MAX_RETRIES", "1"))
TRANSCRIBE_MAX_BYTES = 60 * 1024 * 1024
TRANSCRIBE_MAX_SECONDS = 180
ALLOWED_MEDIA_EXTENSIONS = {
    "webm",
    "wav",
    "mp3",
    "ogg",
    "oga",
    "m4a",
    "aac",
    "mp4",
    "m4v",
    "mov",
    "mpeg",
    "mpg",
    "mpga",
    "3gp",
    "caf",
}


def resolve_ai_model(model: str | None = None, *, fallback: str | None = None) -> str:
    """未対応・旧モデル名は fallback（未指定時は Luna）へ寄せる。"""
    name = (model or "").strip()
    if name in AI_MODELS:
        return name
    fb = (fallback or "").strip()
    if fb in AI_MODELS:
        return fb
    return DEFAULT_AI_MODEL


def resolve_transcript_ai_model(model: str | None = None) -> str:
    """CNN10 のタイトル→文字起こし区間推定用。未設定は Sol。"""
    return resolve_ai_model(model, fallback=DEFAULT_TRANSCRIPT_AI_MODEL)


def resolve_cefr_level(level: str | None = None, *, fallback: str | None = None) -> str:
    """未対応レベルは fallback（未指定時は DEFAULT_CEFR_LEVEL）へ寄せる。"""
    name = (level or "").strip().upper()
    if name in CEFR_LEVELS:
        return name
    fb = (fallback or "").strip().upper()
    if fb in CEFR_LEVELS:
        return fb
    return DEFAULT_CEFR_LEVEL


def get_openai_api_key() -> str:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if key and not key.startswith("sk-your-"):
        return key

    try:
        from news_app.services.storage import load_state

        stored = (load_state().get("openai_api_key") or "").strip()
        if stored:
            return stored
    except Exception:
        pass

    return ""


def save_openai_api_key(key: str) -> None:
    key = key.strip()
    lines: list[str] = []
    found = False

    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    new_lines: list[str] = []
    for line in lines:
        if line.startswith("OPENAI_API_KEY="):
            if key:
                new_lines.append(f"OPENAI_API_KEY={key}")
            found = True
        else:
            new_lines.append(line)

    if key and not found:
        new_lines.append(f"OPENAI_API_KEY={key}")

    if not new_lines and key:
        new_lines = [f"OPENAI_API_KEY={key}"]

    ENV_FILE.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
    os.environ["OPENAI_API_KEY"] = key


def mask_api_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "••••••••"
    return key[:7] + "…" + key[-4:]
