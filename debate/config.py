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

# 仕様書「2. パート別役割遂行チェックリスト」より（表示用の参考情報。ジャッジ判定には使用しない）
PART_ROLES = {
    "PM": "論題の定義／2つの論点（Point 1, Point 2）の提示（新規論点：可）",
    "LO": "Govの論点を正確に再構築（reconstruct）した上で反駁／自陣の2論点提示（新規論点：可）",
    "MG": "LOの反駁への応答／Govの Point 2 の詳細展開・強化（新規論点：可、Point追加程度）",
    "MO": "MGへの反駁／Oppの Point 2 の詳細展開・深化（新規論点：可、Point追加程度）",
    "LOR": "両陣営の対立点を整理／Opp優位性を主張／総括（新規論点：不可）",
    "PMR": "試合全体の総括／Gov優位性を主張（新規論点：不可）",
}

# 仕様書「4. Cursorへの初回プロンプト」より、各パート開始時に常時表示する定型表現ガイド文
PART_GUIDES = {
    "PM": "Today's topic is ___. We define the motion as follows... "
    "We have two points. The first point is... The second point is...",
    "LO": "We believe that ___ should not... Let me reconstruct the Government's 1st point... "
    "They said, however, Therefore... Then let me explain our 1st point... "
    "Next, let me explain our 2nd point...",
    "MG": "We believe that ___ should... First, let me rebut Opposition's 1st point... "
    "They said, however, Therefore... Next, let me reconstruct Opposition's 1st point... "
    "As for Government's 2nd point...",
    "MO": "We believe that ___ should not... Let me rebut Government's 1st point... "
    "They said, however, Therefore... Next, let me reconstruct Opposition's 1st point... "
    "Then let me explain our 2nd point...",
    "LOR": "On this point, their idea is... On this point, our argument is superior because... "
    "Let me summarize today's debate. The most important point is...",
    "PMR": "Let me summarize today's debate. The most important point is... "
    "First, I will rebut Opposition's 2nd point...",
}

DEFAULT_MOTIONS = [
    "This House believes that after-school club activities in schools should be abolished",
    "This House believes that homework should be abolished",
    "This House would ban smartphones for students under 16",
    "This House believes that school uniforms should be abolished",
    "This House would make English classes optional in Japanese high schools",
    "This House believes that students should be allowed to choose their own teachers",
    "This House would ban part-time jobs for high school students",
    "This House believes that public high schools should be free of charge",
    "This House would introduce a four-day school week",
    "This House believes that competitive examinations for university entrance should be abolished",
    "This House would require all students to study abroad for at least one month",
    "This House believes that social media does more harm than good for teenagers",
    "This House would ban junk food in school cafeterias",
    "This House believes that AI tools should be banned in school assignments",
    "This House would lower the voting age to 16",
    "This House believes that nuclear energy is necessary for Japan's future",
    "This House would make community service mandatory for high school graduation",
    "This House believes that professional athletes are paid too much",
    "This House would prioritize environmental protection over economic growth",
    "This House believes that online learning is better than classroom learning",
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
