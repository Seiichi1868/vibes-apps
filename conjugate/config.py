"""Vibe Speak Conjugate 設定。

news_app / level_check / debate とは完全に独立させ、他モジュールをimportしない。
データ（設定・セッション履歴・弱点動詞集計）は data/conjugate/ 配下に
JSONファイルとして永続化する（Render のディスクマウントを想定）。
"""
import hmac
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(
    os.environ.get("CONJUGATE_DATA_DIR", str(PROJECT_ROOT / "data" / "conjugate"))
).expanduser()
SESSIONS_DIR = DATA_DIR / "sessions"
AUDIO_TMP_DIR = DATA_DIR / "audio_tmp"

SETTINGS_FILE = DATA_DIR / "conjugate_settings.json"
SUBMISSIONS_FILE = DATA_DIR / "conjugate_submissions.json"
WEAK_VERBS_FILE = DATA_DIR / "conjugate_weak_verbs.json"
PROGRESS_FILE = DATA_DIR / "conjugate_progress.json"

def get_admin_password() -> str:
    per_app = (os.environ.get("CONJUGATE_ADMIN_PASSWORD") or "").strip()
    if per_app:
        return per_app
    return (os.environ.get("ADMIN_PASSWORD") or "").strip()


def admin_password_matches(provided) -> bool:
    expected = get_admin_password()
    if not expected:
        return False
    return hmac.compare_digest(str(provided or ""), expected)

# ── ASRエンジン ──────────────────────────────────────────────
ASR_ENGINES = ("whisper", "web_speech")
DEFAULT_ASR_ENGINE = "whisper"

WHISPER_MODELS = {
    "whisper-1": {"label": "Whisper-1（高精度・既定）", "cost_per_min_usd": 0.006},
    "gpt-4o-mini-transcribe": {"label": "GPT-4o-mini-transcribe（低コスト）", "cost_per_min_usd": 0.003},
}
DEFAULT_WHISPER_MODEL = os.environ.get("CONJUGATE_WHISPER_MODEL", "whisper-1")
WHISPER_TIMEOUT_SEC = float(os.environ.get("CONJUGATE_WHISPER_TIMEOUT_SEC", "30"))
WHISPER_MAX_RETRIES = int(os.environ.get("CONJUGATE_WHISPER_MAX_RETRIES", "1"))

# Whisper課金の円換算。レートは環境変数で上書き可能（他アプリには依存しない）。
try:
    USD_JPY = float(os.environ.get("CONJUGATE_USD_JPY", "150"))
except ValueError:
    USD_JPY = 150.0


def whisper_cost_usd(model: str, duration_sec: float) -> float:
    """OpenAI Whisper は1秒単位課金。最低1秒としてUSDコストを返す。"""
    info = WHISPER_MODELS.get(model) or WHISPER_MODELS[DEFAULT_WHISPER_MODEL]
    billed_sec = max(1, int(duration_sec + 0.999999))
    return (billed_sec / 60.0) * float(info["cost_per_min_usd"])


def format_jpy_amount(jpy: float) -> str:
    """結果画面用。通貨記号なしの数字だけ。0.1円なら '0.1'。"""
    if jpy <= 0:
        return "0"
    if jpy < 0.1:
        text = f"{jpy:.2f}".rstrip("0").rstrip(".")
        return text or "0"
    return f"{jpy:.1f}"

MAX_AUDIO_BYTES = 8 * 1024 * 1024
ALLOWED_AUDIO_EXTENSIONS = {"webm", "wav", "mp3", "m4a", "ogg", "mp4", "mpeg", "mpga"}

# ── 判定の厳しさ ─────────────────────────────────────────────
STRICTNESS_MODES = ("lenient", "strict")
DEFAULT_STRICTNESS = "lenient"

# ── 出題カテゴリ・文型 ───────────────────────────────────────
from conjugate.data.verbs import CATEGORY_LABELS, CATEGORY_ORDER  # noqa: E402
from conjugate.data.conjugations import TENSE_LABELS, TENSE_ORDER  # noqa: E402

DEFAULT_ENABLED_CATEGORIES = list(CATEGORY_ORDER)
DEFAULT_ENABLED_TENSES = ["present"]  # 段階的実装: まず現在形のみを既定で有効化

DEFAULT_QUESTIONS_PER_SESSION = 10
DEFAULT_TARGETS_PER_QUESTION = 1  # 1問あたりtú変換させる文型の数（1 or 2）
DEFAULT_GUSTAR_ENABLED = True
DEFAULT_GUSTAR_PER_SESSION = 1
DEFAULT_PRIORITIZE_WEAK_VERBS = True

from conjugate.data.persons import DEFAULT_PERSON_MODE  # noqa: E402

# ── 背景・オープニング（conjugate独自。他アプリの画像・設定は使わない） ─
BACKGROUND_PRESETS = {
    "meadow": {"label": "草原", "image": "images/bg/meadow.jpg", "style": "photo"},
    "forest": {"label": "森", "image": "images/bg/forest.jpg", "style": "photo"},
    "mountain": {"label": "山", "image": "images/bg/mountain.jpg", "style": "photo"},
    "ocean": {"label": "海", "image": "images/bg/ocean.jpg", "style": "photo"},
    "lake": {"label": "湖", "image": "images/bg/lake.jpg", "style": "photo"},
    "anime_mountain": {
        "label": "朝の山",
        "image": "images/backgrounds/bg_anime_mountain_01.png",
        "style": "anime",
    },
    "anime_forest": {
        "label": "霧の森",
        "image": "images/backgrounds/bg_anime_forest_01.png",
        "style": "anime",
    },
    "anime_clouds": {
        "label": "雲海",
        "image": "images/backgrounds/bg_anime_clouds_01.png",
        "style": "anime",
    },
    "anime_hills": {
        "label": "丘と草原",
        "image": "images/backgrounds/bg_anime_hills_01.png",
        "style": "anime",
    },
    "anime_lake": {
        "label": "湖",
        "image": "images/backgrounds/bg_anime_lake_01.png",
        "style": "anime",
    },
    "anime_coast": {
        "label": "夕暮れの海",
        "image": "images/backgrounds/bg_anime_coast_01.png",
        "style": "anime",
    },
}
BACKGROUND_STYLE_LABELS = {
    "photo": "実写",
    "anime": "アニメ風",
}
BACKGROUND_STYLE_ORDER = ["photo", "anime"]
DEFAULT_BACKGROUND_ID = "meadow"
DEFAULT_BACKGROUND_OPACITY = 0.18
DEFAULT_OPENING_ENABLED = True
DEFAULT_OPENING_MS = 2000
DEFAULT_CONJUGATION_MASTERY_THRESHOLD = 5
DEFAULT_VOCAB_MASTERY_THRESHOLD = 5

# ── コイン経済（Guardián） ───────────────────────────────────
DEFAULT_GUARDIAN_PRICE_COINS = 50


def resolve_background(background_id: str | None = None) -> dict:
    preset_id = background_id if background_id in BACKGROUND_PRESETS else DEFAULT_BACKGROUND_ID
    preset = BACKGROUND_PRESETS[preset_id]
    return {
        "background_id": preset_id,
        "background_label": preset["label"],
        "background_image": preset["image"],
        "background_style": preset.get("style", "photo"),
    }


def clamp_opacity(value, default: float = DEFAULT_BACKGROUND_OPACITY) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return round(max(0.0, min(n, 1.0)), 2)


def clamp_opening_ms(value, default: int = DEFAULT_OPENING_MS) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(400, min(8000, n))


def clamp_mastery_threshold(value, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(50, n))


def clamp_guardian_price(value, default: int = DEFAULT_GUARDIAN_PRICE_COINS) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(9999, n))


def clamp_daily_goal(value, default: int = 0) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(100, n))


def get_openai_api_key() -> str:
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_TMP_DIR.mkdir(parents=True, exist_ok=True)
