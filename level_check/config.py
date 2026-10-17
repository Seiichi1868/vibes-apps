"""Speaking Level Check Test 設定。

news_app / debate とは完全に独立させ、他モジュールを import しない。
データ（名簿・問題バンク・提出結果・音声）は data/level_check/ 配下に
JSON ファイル・音声ファイルとして永続化する（Render のディスクマウントを想定）。
"""
import hmac
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(
    os.environ.get("LEVEL_CHECK_DATA_DIR", str(PROJECT_ROOT / "data" / "level_check"))
).expanduser()
AUDIO_DIR = DATA_DIR / "audio"
PROMPT_AUDIO_DIR = AUDIO_DIR / "prompts"
SESSIONS_DIR = DATA_DIR / "sessions"

STUDENTS_FILE = DATA_DIR / "level_check_students.json"
SUBMISSIONS_FILE = DATA_DIR / "level_check_submissions.json"
QUESTIONS_FILE = DATA_DIR / "level_check_questions.json"
SETTINGS_FILE = DATA_DIR / "level_check_settings.json"

def get_admin_password() -> str:
    per_app = (os.environ.get("LEVEL_CHECK_ADMIN_PASSWORD") or "").strip()
    if per_app:
        return per_app
    return (os.environ.get("ADMIN_PASSWORD") or "").strip()


def admin_password_matches(provided) -> bool:
    expected = get_admin_password()
    if not expected:
        return False
    return hmac.compare_digest(str(provided or ""), expected)

TRANSCRIBE_MODEL = os.environ.get("LEVEL_CHECK_WHISPER_MODEL", "whisper-1")
WHISPER_TIMEOUT_SEC = float(os.environ.get("LEVEL_CHECK_WHISPER_TIMEOUT_SEC", "45"))
WHISPER_MAX_RETRIES = int(os.environ.get("LEVEL_CHECK_WHISPER_MAX_RETRIES", "1"))
EVAL_TIMEOUT_SEC = float(os.environ.get("LEVEL_CHECK_EVAL_TIMEOUT_SEC", "60"))
EVAL_MAX_RETRIES = int(os.environ.get("LEVEL_CHECK_EVAL_MAX_RETRIES", "1"))

MAX_AUDIO_BYTES = 15 * 1024 * 1024
ALLOWED_AUDIO_EXTENSIONS = {"webm", "wav", "mp3", "m4a", "ogg", "mp4", "mpeg", "mpga"}

# ── 6カテゴリ（A〜F） ───────────────────────────────────────
CATEGORIES = ("A", "B", "C", "D", "E", "F")

CATEGORY_LABELS = {
    "A": "A. 質問応答",
    "B": "B. 復唱",
    "C": "C. 会話理解質問",
    "D": "D. 文章理解質問",
    "E": "E. 要約リテリング",
    "F": "F. 自由回答",
}

CATEGORY_DESCRIPTIONS = {
    "A": "短い質問を聞き、短く即答する（リスニング＋即応性）",
    "B": "聞いた英文をそのまま繰り返す（リスニング＋発話正確性）",
    "C": "短い会話を聞き、内容に関する質問に答える（リスニング理解）",
    "D": "やや長めの文章を聞き、内容に関する質問に答える（リスニング理解・応用）",
    "E": "短いストーリーを聞き、制限時間内に自分の言葉で言い換えて話す",
    "F": "簡単なテーマについて自分の意見を自由に述べる",
}

# スピーキング採点対象 / リスニング採点対象
SPEAKING_CATEGORIES = ("B", "E", "F")
LISTENING_CATEGORIES = ("A", "C", "D")

# 事前TTS（プロンプト音声）が必要なカテゴリ
AUDIO_PROMPT_CATEGORIES = ("A", "B", "C", "D", "E")

# 週次実施での出題数目安（設定値として上書き可能）
DEFAULT_QUESTIONS_PER_CATEGORY = {
    "A": 3,
    "B": 4,
    "C": 2,
    "D": 2,
    "E": 1,
    "F": 1,
}

DEFAULT_TIME_LIMIT_SEC = {
    "A": 15,
    "E": 30,
    "F": 30,
}

# TTS（OpenAI）— 教育現場での聞き取りやすさ優先
TTS_MODEL = os.environ.get("LEVEL_CHECK_TTS_MODEL", "tts-1")
TTS_VOICE = os.environ.get("LEVEL_CHECK_TTS_VOICE", "nova")
TTS_SPEED = float(os.environ.get("LEVEL_CHECK_TTS_SPEED", "0.95"))

# ── 生徒への情報要求レベル（3段階） ─────────────────────────
INFO_LEVELS = ("full", "partial", "none")
DEFAULT_INFO_LEVEL = "partial"

INFO_LEVEL_LABELS = {
    "full": "氏名・クラス・番号",
    "partial": "クラス・番号のみ",
    "none": "情報要求なし",
}

# ── 評価に使う AI モデル（管理画面で切替可能。既定は Luna） ──────
AI_MODEL_MODES = {
    "luna": {"label": "Luna（GPT-5.6）", "model": "gpt-5.6-luna"},
    "terra": {"label": "Terra（GPT-5.6）", "model": "gpt-5.6-terra"},
    "gpt-4o-mini": {"label": "GPT-4o-mini", "model": "gpt-4o-mini"},
}
DEFAULT_AI_MODEL_MODE = "luna"

# 総合スコア合成の初期重み（スピーキング／リスニング各50%）
DEFAULT_OVERALL_WEIGHTS = {"speaking": 0.5, "listening": 0.5}

# ── 背景画像（news/ の自然画像を共有 static 経由でそのまま利用） ──────
BACKGROUND_IMAGE_STATIC_PATH = "news/images/nature-bg.jpg"
DEFAULT_BACKGROUND_OPACITY = 0.35


def resolve_ai_model_mode(mode: str | None = None) -> str:
    if mode in AI_MODEL_MODES:
        return mode
    return DEFAULT_AI_MODEL_MODE


def resolve_ai_model_id(mode: str | None = None) -> str:
    return AI_MODEL_MODES[resolve_ai_model_mode(mode)]["model"]


def resolve_info_level(level: str | None = None) -> str:
    if level in INFO_LEVELS:
        return level
    return DEFAULT_INFO_LEVEL


def score_track_for_category(category: str) -> str:
    if category in SPEAKING_CATEGORIES:
        return "speaking"
    if category in LISTENING_CATEGORIES:
        return "listening"
    return "speaking"


def get_openai_api_key() -> str:
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    PROMPT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
