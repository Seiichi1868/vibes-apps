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
SCRIPTS_DIR = DATA_DIR / "scripts"
SCRIPT_AUDIO_DIR = DATA_DIR / "script_audio"

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

# 観戦モードの読み上げ。ソロの TTS_VOICE / tts.py とは別経路。
WATCH_SPEECH_MODEL = "gpt-4o-mini-tts"
WATCH_GOV_VOICE = "sage"
WATCH_OPP_VOICE = "ash"
WATCH_SPEECH_INSTRUCTIONS = (
    "Speak as a clear, calm debate speaker at a steady, natural pace. "
    "Neutral accent. Do not add dramatic emotion."
)
WATCH_SPEECH_MAX_INPUT_CHARS = 6000
WATCH_SPEECH_TIMEOUT_SEC = float(os.environ.get("DEBATE_WATCH_SPEECH_TIMEOUT_SEC", "90"))
WATCH_SPEECH_MAX_RETRIES = int(os.environ.get("DEBATE_WATCH_SPEECH_MAX_RETRIES", "1"))
WATCH_SPEECH_STUCK_SEC = int(os.environ.get("DEBATE_WATCH_SPEECH_STUCK_SEC", "240"))

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
    "They said ... Therefore... We have two points. The first point is... "
    "The second point is... I will explain the 1st point...",
    "MG": "We believe that ___ should... First, let me rebut Opposition's 1st point... "
    "They said ... Therefore... Next, let me reconstruct Government's 1st point... "
    "Then let me explain our 2nd point...",
    "MO": "We believe that ___ should not... First, let me rebut the reconstruction of Government's 1st point... "
    "They said ... Therefore... Next, let me rebut Government's 2nd point... "
    "They said ... Therefore... Then, let me reconstruct Opposition's 1st point... "
    "Finally, let me explain our 2nd point...",
    "LOR": "Let me summarize today's debate. The most important point is... "
    "On this point, their idea is... However, our argument is superior because...",
    "PMR": "First, I will rebut Opposition's 2nd point... They said ... Therefore... "
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

# 論点の状態。画面ラベル・色・勝敗の重みはここだけを見る。
# extended は状態ではなく history の action。
ARGUMENT_STATUS = {
    "intact": {"label_en": "Intact", "gloss_ja": "維持", "weight": 1.0, "color": "green"},
    "weakened": {"label_en": "Weakened", "gloss_ja": "弱体化", "weight": 0.5, "color": "amber"},
    "collapsed": {"label_en": "Collapsed", "gloss_ja": "崩れた", "weight": 0.0, "color": "gray"},
}
HISTORY_ACTION = {
    "raised": {"label_en": "Raised"},
    "rebutted": {"label_en": "Rebutted"},
    "defended": {"label_en": "Defended"},
    "extended": {"label_en": "Extended"},
}
SHOW_STATUS_GLOSS_JA = True

# 表示時だけ使う。保存済みJSONは書き換えない。
LEGACY_ARGUMENT_STATUS = {
    "standing": "intact",
    "knocked_down": "collapsed",
    "extended": "intact",
}

# 観戦スクリプトの語数目安（音声を聞いてから調整する。今回は値を変えない）。
SCRIPT_WORDS_PER_MINUTE = 140
SCRIPT_WINNER_MARGIN_MIN = 0.5
SCRIPT_WINNER_MARGIN_MAX = 1.0
SCRIPT_LEVEL_WORD_RANGES = {
    "easy": {"constructive": (220, 280), "reply": (150, 190)},
    "normal": {"constructive": (330, 400), "reply": (220, 270)},
    "hard": {"constructive": (430, 480), "reply": (300, 340)},
}

# 生成プロンプトとジャッジプロンプトが同じ文面を埋め込む。
ARGUMENT_JUDGMENT_PROCEDURE = """各論点について、次の2つを順に判断する。
- Q1 相手の反論は、その論点の核心（なぜそうなるかの理由）に届いたか: reached（届いた）/ partial（範囲・程度への指摘のみ）/ none（届かない・反論なし）
- Q2 その後の再反論・防御で回復したか: full（十分）/ partial（部分的）/ none（なし）

Q1 と Q2 から最終状態を決める。
- Q1 が none → intact
- Q1 が partial かつ Q2 が full → intact
- Q1 が partial かつ Q2 が partial または none → weakened
- Q1 が reached かつ Q2 が full → intact
- Q1 が reached かつ Q2 が partial → weakened
- Q1 が reached かつ Q2 が none → collapsed

- collapsed は「核心に届いた反論に答えがなかった」場合に限る。迷ったら weakened。
- LOR / PMR で新規に出された論点は、判定対象に含めない。
- 各論点に reason_ja（判定理由、日本語1文、60字以内）を付ける。Q1・Q2 の結果が分かる書き方にする。
- 各陣営の合計は、その陣営の論点（最大2つ）の weight の和。合計が多い側を勝者とする。同点は内容ルーブリック（Content）で決める。"""


def argument_status_rules_text() -> str:
    """生成とジャッジが共有する状態定義と判定手順。"""
    lines = ["# 論点の状態（保存する内部値は次の3つのみ）"]
    for key, meta in ARGUMENT_STATUS.items():
        lines.append(f'- "{key}": weight {meta["weight"]}')
    lines.append("- extended は状態ではない。補強は history の action として記録する。")
    lines.append("- history の action は raised / rebutted / defended / extended の4種。")
    lines.append("")
    lines.append(ARGUMENT_JUDGMENT_PROCEDURE)
    return "\n".join(lines)


def canonical_argument_status(status: str) -> str:
    """内部値へ揃える。未知の値は intact（迷ったら崩さない）。"""
    raw = str(status or "").strip()
    if raw in ARGUMENT_STATUS:
        return raw
    mapped = LEGACY_ARGUMENT_STATUS.get(raw)
    if mapped:
        return mapped
    return "intact"


def argument_weight(status: str) -> float:
    key = canonical_argument_status(status)
    return float(ARGUMENT_STATUS[key]["weight"])


def side_score_totals(items) -> dict:
    """陣営ごとに最大2論点の weight を足す。"""
    buckets = {"Gov": [], "Opp": []}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        side = str(item.get("side") or "").strip()
        if side not in buckets:
            continue
        buckets[side].append(argument_weight(item.get("status")))
    return {
        "gov": round(sum(buckets["Gov"][:2]) + 1e-9, 1),
        "opp": round(sum(buckets["Opp"][:2]) + 1e-9, 1),
    }


def format_score_total(totals: dict | None) -> str:
    if not isinstance(totals, dict):
        return ""
    try:
        gov = float(totals.get("gov") or 0)
        opp = float(totals.get("opp") or 0)
    except (TypeError, ValueError):
        return ""
    return f"Gov {gov:.1f} / Opp {opp:.1f}"


def argument_rows_for_display(items) -> list:
    """保存値は変えず、画面用の行だけ作る。旧状態名はここで変換する。"""
    rows = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        raw_status = str(item.get("status") or "").strip()
        status = canonical_argument_status(raw_status)
        meta = ARGUMENT_STATUS[status]
        history = []
        saw_extended = False
        for entry in item.get("history") or []:
            if not isinstance(entry, dict):
                continue
            part = str(entry.get("part") or "").strip()
            action = str(entry.get("action") or "").strip()
            if action == "reinforced":
                action = "extended"
            if action not in HISTORY_ACTION or not part:
                continue
            if action == "extended":
                saw_extended = True
            history.append(
                {
                    "part": part,
                    "action": action,
                    "label_en": HISTORY_ACTION[action]["label_en"],
                }
            )
        if raw_status == "extended" and not saw_extended:
            part = str(item.get("raised_in") or item.get("raised_in_part") or "").strip()
            if part:
                history.append(
                    {
                        "part": part,
                        "action": "extended",
                        "label_en": HISTORY_ACTION["extended"]["label_en"],
                    }
                )
        summary_en = str(item.get("summary_en") or "").strip()
        summary_ja = str(item.get("summary_ja") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not summary_en:
            summary_en = summary or summary_ja
        if summary_ja and summary_ja == summary_en:
            summary_ja = ""
        elif not summary_ja and summary and summary != summary_en:
            summary_ja = summary
        rows.append(
            {
                "id": str(item.get("argument_id") or item.get("id") or ""),
                "side": str(item.get("side") or ""),
                "raised_in": str(item.get("raised_in") or item.get("raised_in_part") or ""),
                "summary_en": summary_en,
                "summary_ja": summary_ja,
                "status": status,
                "label_en": meta["label_en"],
                "gloss_ja": meta["gloss_ja"],
                "color": meta["color"],
                "reason_ja": str(item.get("reason_ja") or "").strip(),
                "history": history,
            }
        )
    return rows


def argument_template_context() -> dict:
    return {
        "argument_status": ARGUMENT_STATUS,
        "history_action": HISTORY_ACTION,
        "show_status_gloss_ja": SHOW_STATUS_GLOSS_JA,
        "argument_status_client": {
            "statuses": ARGUMENT_STATUS,
            "actions": HISTORY_ACTION,
            "showGlossJa": SHOW_STATUS_GLOSS_JA,
        },
    }


def ensure_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    SCRIPT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
