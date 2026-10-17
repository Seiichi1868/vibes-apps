"""Vibe Speak Trigger 設定。

news_app / flask_app / level_check / conjugate とは完全に独立させ、
他モジュールを import しない。データ（テーマ・名簿・セッション・音声）は
data/trigger/ 配下に JSON ファイル・音声ファイルとして永続化する
（Render のディスクマウントを想定）。
"""
import hmac
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("TRIGGER_DATA_DIR", str(PROJECT_ROOT / "data" / "trigger"))).expanduser()
AUDIO_DIR = DATA_DIR / "audio"
PROMPT_AUDIO_DIR = AUDIO_DIR / "prompts"
SESSIONS_DIR = DATA_DIR / "sessions"

SETTINGS_FILE = DATA_DIR / "trigger_settings.json"
THEMES_FILE = DATA_DIR / "trigger_themes.json"
STUDENTS_FILE = DATA_DIR / "trigger_students.json"
SUBMISSIONS_FILE = DATA_DIR / "trigger_submissions.json"

def get_admin_password() -> str:
    per_app = (os.environ.get("TRIGGER_ADMIN_PASSWORD") or "").strip()
    if per_app:
        return per_app
    return (os.environ.get("ADMIN_PASSWORD") or "").strip()


def admin_password_matches(provided) -> bool:
    expected = get_admin_password()
    if not expected:
        return False
    return hmac.compare_digest(str(provided or ""), expected)

# ── 処理単位ごとの AI（GPT）モデル選択キー ─────────────────────
# 管理画面でこの単位ごとに個別にプルダウン選択できる（コスト管理目的）。
TASK_KEYS = (
    "script_translate",     # ステップ1: 翻訳／校正
    "pronunciation_eval",   # ステップ3: 発音評価
    "qa_generate",          # ステップ4: Q&A質問生成
    "qa_evaluate",          # ステップ4: Q&A回答評価
    "speech_topic",         # ステップ5: 即興スピーチトピック生成
    "speech_evaluate",      # ステップ5: 即興スピーチ評価
    "report_final",         # ステップ6: 総合評価レポート生成
)

TASK_LABELS = {
    "script_translate": "台本 翻訳／校正（ステップ1）",
    "pronunciation_eval": "発音評価（ステップ3）",
    "qa_generate": "Q&A 質問生成（ステップ4）",
    "qa_evaluate": "Q&A 回答評価（ステップ4）",
    "speech_topic": "即興スピーチ トピック生成（ステップ5）",
    "speech_evaluate": "即興スピーチ評価（ステップ5）",
    "report_final": "総合評価レポート生成（ステップ6）",
}

DEFAULT_TASK_MODEL_MODE = "4o-mini"
DEFAULT_TASK_MODEL_MODES = {key: DEFAULT_TASK_MODEL_MODE for key in TASK_KEYS}

# ── Whisper（音声文字起こし） ───────────────────────────────
DEFAULT_WHISPER_MODEL = os.environ.get("TRIGGER_WHISPER_MODEL", "whisper-1")
WHISPER_TIMEOUT_SEC = float(os.environ.get("TRIGGER_WHISPER_TIMEOUT_SEC", "45"))
WHISPER_MAX_RETRIES = int(os.environ.get("TRIGGER_WHISPER_MAX_RETRIES", "1"))

# ── TTS（音声合成） ─────────────────────────────────────────
TTS_MODEL = os.environ.get("TRIGGER_TTS_MODEL", "tts-1")
TTS_VOICE = os.environ.get("TRIGGER_TTS_VOICE", "nova")
TTS_SPEED = float(os.environ.get("TRIGGER_TTS_SPEED", "0.95"))

EVAL_TIMEOUT_SEC = float(os.environ.get("TRIGGER_EVAL_TIMEOUT_SEC", "60"))
EVAL_MAX_RETRIES = int(os.environ.get("TRIGGER_EVAL_MAX_RETRIES", "1"))

MAX_AUDIO_BYTES = 15 * 1024 * 1024
ALLOWED_AUDIO_EXTENSIONS = {"webm", "wav", "mp3", "m4a", "ogg", "mp4", "mpeg", "mpga"}

# ── 問題数設定（互いに独立。連動しない） ────────────────────
DEFAULT_QA_QUESTION_COUNT = 3
QA_QUESTION_COUNT_RANGE = (1, 5)
DEFAULT_SPEECH_TOPIC_COUNT = 1
SPEECH_TOPIC_COUNT_RANGE = (1, 3)

DEFAULT_SPEECH_TOPIC_TTS_ENABLED = False

# 生徒情報（クラス・番号・名前）の入力を必須にするか。
# 練習用途（自分の実力確認など）では不要な場合が多いため、管理画面でOFFにできる。
DEFAULT_STUDENT_INFO_REQUIRED = True

SCRIPT_MODES = ("translate", "correct")

# Versant 相当5カテゴリの加重（総合スコア算出用。管理画面で調整可能）
DEFAULT_VERSANT_WEIGHTS = {
    "sentence_mastery": 0.2,
    "vocabulary": 0.2,
    "fluency": 0.2,
    "pronunciation": 0.2,
    "comprehension": 0.2,
}


def get_openai_api_key() -> str:
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    PROMPT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
