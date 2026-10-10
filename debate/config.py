"""Debate app 設定。

セッション／音声データは data/debate/ 配下に JSON・音声ファイルとして永続化する
（PDA_debate_app_spec.md 「1. データスキーマ」準拠）。
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(
    os.environ.get("DEBATE_DATA_DIR", str(PROJECT_ROOT / "data" / "debate"))
).expanduser()
SESSIONS_DIR = DATA_DIR / "sessions"
AUDIO_DIR = DATA_DIR / "audio"

WHISPER_MODEL = os.environ.get("DEBATE_WHISPER_MODEL", "whisper-1")

# OpenAI SDKの既定タイムアウトは10分（かつ既定で2回リトライ＝最悪30分待ち）と長すぎるため、
# ここで明示的に短いタイムアウトとリトライ回数を設定し、詰まった場合も数分以内に
# エラーとして返せるようにする。
WHISPER_TIMEOUT_SEC = float(os.environ.get("DEBATE_WHISPER_TIMEOUT_SEC", "45"))
WHISPER_MAX_RETRIES = int(os.environ.get("DEBATE_WHISPER_MAX_RETRIES", "1"))

# ジャッジモデル（単価・性能スコアは debate/judge_model_pricing.py、バー算出は judge_models.py）
from debate.judge_models import DEFAULT_JUDGE_MODEL_MODE, get_judge_model_options

JUDGE_MODEL_OPTIONS = get_judge_model_options()
# 環境変数でモデルIDを直接指定する場合（管理画面設定より優先）
JUDGE_MODEL_OVERRIDE = os.environ.get("DEBATE_JUDGE_MODEL", "").strip()
JUDGE_TIMEOUT_SEC = float(os.environ.get("DEBATE_JUDGE_TIMEOUT_SEC", "90"))
JUDGE_MAX_RETRIES = int(os.environ.get("DEBATE_JUDGE_MAX_RETRIES", "1"))
# ジャッジが "judging" のまま長時間止まっている場合にエラー扱いへ復旧するまでの秒数
JUDGE_STUCK_SEC = int(os.environ.get("DEBATE_JUDGE_STUCK_SEC", "180"))

# Solo Practice: 対戦AI（ジャッジとは別系統。既定モデルはジャッジと同じ luna）
OPPONENT_TIMEOUT_SEC = float(os.environ.get("DEBATE_OPPONENT_TIMEOUT_SEC", "90"))
OPPONENT_MAX_RETRIES = int(os.environ.get("DEBATE_OPPONENT_MAX_RETRIES", "1"))
GENERATION_STUCK_SEC = int(os.environ.get("DEBATE_GENERATION_STUCK_SEC", "60"))

# Solo Practice: サーバーTTS（ブラウザ speechSynthesis は使わない）
TTS_MODEL = os.environ.get("DEBATE_TTS_MODEL", "gpt-4o-mini-tts").strip() or "gpt-4o-mini-tts"
TTS_VOICE = os.environ.get("DEBATE_TTS_VOICE", "coral").strip() or "coral"
TTS_INSTRUCTIONS = (
    "Speak in clear, calm, natural English at a measured parliamentary debate pace. "
    "Do not rush, and do not sound flat or monotonic."
)
TTS_FORMAT = "mp3"
TTS_MAX_INPUT_CHARS = 4000
TTS_TIMEOUT_SEC = float(os.environ.get("DEBATE_TTS_TIMEOUT_SEC", "90"))
TTS_MAX_RETRIES = int(os.environ.get("DEBATE_TTS_MAX_RETRIES", "1"))
TTS_STUCK_SEC = int(os.environ.get("DEBATE_TTS_STUCK_SEC", "60"))

# AIスピーチ本文の表示既定（運用で切り替えられるよう1箇所に置く）
AI_TEXT_VISIBLE_DEFAULT = True

VALID_SESSION_MODES = ("duo", "solo")
VALID_SIDES = ("Gov", "Opp")
VALID_DIFFICULTIES = ("easy", "normal", "hard")
DEFAULT_AI_DIFFICULTY = "normal"
GOV_PARTS = ("PM", "MG", "PMR")
OPP_PARTS = ("LO", "MO", "LOR")

# POI（Point of Information）: 建設的スピーチのみ。Reply（LOR/PMR）は不可。
# 保護時間の既定は開始側・終了側とも1分。管理画面で別々に 0（無し）〜90秒へ変更できる。
# POI中もスピーカーの持ち時間は止まらない。
POI_ALLOWED_PARTS = ("PM", "LO", "MG", "MO")
POI_PROTECTED_SEC = 60
POI_PROTECTED_SEC_MIN = 0
POI_PROTECTED_SEC_MAX = 90
POI_PROTECTED_SEC_STEP = 5
POI_DURATION_SEC = 15
POI_OFFER_TIMEOUT_SEC = 8
POI_STATUSES = ("accepted", "declined", "timeout")

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # Whisper API の上限に合わせる
ALLOWED_AUDIO_EXTENSIONS = {"webm", "wav", "mp3", "m4a", "ogg", "mp4", "mpeg", "mpga"}

# 6パートの進行順（スキーマの part_order と一致）
PART_ORDER = ["PM", "LO", "MG", "MO", "LOR", "PMR"]

PART_DEFS = {
    "PM": {"side": "Gov", "part_order": 1, "time_limit_sec": 210},
    "LO": {"side": "Opp", "part_order": 2, "time_limit_sec": 210},
    "MG": {"side": "Gov", "part_order": 3, "time_limit_sec": 210},
    "MO": {"side": "Opp", "part_order": 4, "time_limit_sec": 210},
    "LOR": {"side": "Opp", "part_order": 5, "time_limit_sec": 150},
    "PMR": {"side": "Gov", "part_order": 6, "time_limit_sec": 150},
}

PART_LABELS = {
    "PM": "Prime Minister（首相）",
    "LO": "Leader of Opposition（野党党首）",
    "MG": "Member of Government（与党議員）",
    "MO": "Member of Opposition（野党議員）",
    "LOR": "Leader of Opposition Reply（野党党首・最終弁論）",
    "PMR": "Prime Minister Reply（首相・最終弁論）",
}

# 授業フロー準拠のパート役割（進行画面表示＋ジャッジ判定の共通ソース）
PART_ROLES = {
    "PM": "論題の定義／2論点の提示（Point 1は詳しく、Point 2は概要でよい）",
    "LO": "Gov Point 1の再構築・反駁（PMがPoint 2をタイトルだけにしたことは攻撃しない。詳細はMG）／自陣2論点の提示（Point 1は詳しく、Point 2は概要でよい）",
    "MG": "Opp Point 1への反駁／Gov Point 1の再構築・防御／Gov Point 2の詳細展開",
    "MO": "MGによるGov Point 1再構築への反駁／その直後にGov Point 2への反駁／Opp Point 1の再構築・防御／Opp Point 2の詳細展開",
    "LOR": "対立点の整理／Opp優位の総括（Gov Point 2への反論はここでは行わない。それはMO。新規論点不可）",
    "PMR": "Opp Point 2への反駁のうえ総括／Gov優位の主張（新規論点不可）",
}

# 授業フロー準拠の定型表現ガイド（各パート開始時に常時表示）
PART_GUIDES = {
    "PM": "Today's topic is ___. We define the motion as follows... "
    "We have two points. The first point is... The second point is... "
    "I will explain the 1st point...",
    "LO": "We believe that ___ should not... Let me rebut what the Government team said... "
    "They said, however, Therefore... We have two points. The first point is... "
    "The second point is... I will explain the 1st point...",
    "MG": "We believe that ___ should... First, let me rebut Opposition's 1st point... "
    "They said, however, Therefore... Next, let me reconstruct Government's 1st point... "
    "Then let me explain our 2nd point...",
    "MO": "We believe that ___ should not... First, let me rebut the reconstruction of Government's 1st point... "
    "They said, however, Therefore... Next, let me rebut Government's 2nd point... "
    "They said, however, Therefore... Then, let me reconstruct Opposition's 1st point... "
    "Finally, let me explain our 2nd point...",
    "LOR": "Let me summarize today's debate. The most important point is... "
    "On this point, their idea is... However, our argument is superior because...",
    "PMR": "First, I will rebut Opposition's 2nd point... They said, however, Therefore... "
    "Then I will summarize today's debate. The most important point is... "
    "On this point, their idea is... However, our argument is superior because...",
}

DEFAULT_MOTIONS = [
    "After-school club activities in schools should be abolished",
    "Homework should be abolished",
    "Smartphones should be banned for students under 16",
    "School uniforms should be abolished",
    "English classes should be optional in Japanese high schools",
    "Students should be allowed to choose their own teachers",
    "Part-time jobs should be banned for high school students",
    "Public high schools should be free of charge",
    "A four-day school week should be introduced",
    "Competitive examinations for university entrance should be abolished",
    "All students should study abroad for at least one month",
    "Social media does more harm than good for teenagers",
    "Junk food should be banned in school cafeterias",
    "AI tools should be banned in school assignments",
    "The voting age should be lowered to 16",
    "Nuclear energy is necessary for Japan's future",
    "Community service should be mandatory for high school graduation",
    "Professional athletes are paid too much",
    "Environmental protection should be prioritized over economic growth",
    "Online learning is better than classroom learning",
]

STATUS_LABELS = {
    "not_started": "未実施",
    "recording": "録音中",
    "transcribing": "文字起こし中",
    "needs_review": "確認待ち",
    "confirmed": "確定済み",
}


def ensure_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
