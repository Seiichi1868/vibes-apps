"""Solo Practice 用のセッション操作。

デュオの進行ロジックに `if mode == "solo"` を散らかさず、ガードと担当割り当てをここに集約する。
既存セッションに `mode` が無い場合は duo とみなす（マイグレーションはしない）。
"""
from __future__ import annotations

import random

from debate.config import (
    DEFAULT_AI_DIFFICULTY,
    GOV_PARTS,
    OPP_PARTS,
    PART_ORDER,
    VALID_DIFFICULTIES,
    VALID_SIDES,
)

CONFLICT = 409


def session_mode(session: dict | None) -> str:
    mode = str((session or {}).get("mode") or "").strip().lower()
    return "solo" if mode == "solo" else "duo"


def is_solo(session: dict | None) -> bool:
    return session_mode(session) == "solo"


def normalize_user_side(value, *, allow_random: bool = False) -> str | None:
    raw = str(value or "").strip()
    if allow_random and raw in ("random", "ランダム"):
        return random.choice(VALID_SIDES)
    if raw in VALID_SIDES:
        return raw
    return None


def normalize_difficulty(value) -> str:
    raw = str(value or "").strip().lower()
    if raw in VALID_DIFFICULTIES:
        return raw
    return DEFAULT_AI_DIFFICULTY


def human_parts_for_side(user_side: str) -> tuple[str, ...]:
    return GOV_PARTS if user_side == "Gov" else OPP_PARTS


def ai_parts_for_side(user_side: str) -> tuple[str, ...]:
    return OPP_PARTS if user_side == "Gov" else GOV_PARTS


def speaker_for_part(user_side: str, part: str) -> str:
    return "human" if part in human_parts_for_side(user_side) else "ai"


def preceding_parts(part: str) -> list[str]:
    if part not in PART_ORDER:
        return []
    return PART_ORDER[: PART_ORDER.index(part)]


def part_is_ai(part_data: dict | None) -> bool:
    return str((part_data or {}).get("speaker") or "human") == "ai"


def all_preceding_confirmed(session: dict, part: str) -> bool:
    from debate.storage import get_part

    for name in preceding_parts(part):
        prior = get_part(session, name)
        if not prior:
            return False
        if prior.get("status") != "confirmed":
            return False
        if not str(prior.get("transcript_edited") or "").strip():
            return False
    return True


def recording_guard(session: dict, part: str) -> tuple[bool, str]:
    """録音開始・音声保存・リアルタイム文字起こしの共通ガード。duo なら常に許可。"""
    if not is_solo(session):
        return True, ""

    from debate.storage import get_part

    part_data = get_part(session, part)
    if not part_data:
        return False, f"不明なパート: {part}"
    if part_is_ai(part_data):
        return False, "このパートは相手AIの担当です。"
    if not all_preceding_confirmed(session, part):
        return False, "前のパートを確定すると解禁されます。"
    return True, ""


def generation_guard(session: dict, part: str) -> tuple[bool, str]:
    """AI生成開始のガード。対象が AI かつ先行パートが全て confirmed のときのみ。"""
    if not is_solo(session):
        return False, "Solo Practice のセッションではありません。"

    from debate.storage import get_part

    part_data = get_part(session, part)
    if not part_data:
        return False, f"不明なパート: {part}"
    if not part_is_ai(part_data):
        return False, "このパートは生徒の担当です。"
    if not all_preceding_confirmed(session, part):
        return False, "先行パートが全て確定してから生成できます。"
    return True, ""


def chain_successor(session: dict, part: str) -> str | None:
    """連続AIパート（Gov側生徒のとき MO→LOR）。既に生成中/完了ならチェーンしない。"""
    if part != "MO":
        return None
    from debate.storage import get_part

    successor = get_part(session, "LOR")
    if not part_is_ai(successor):
        return None
    status = str((successor or {}).get("generation_status") or "idle")
    if status in ("generating", "done"):
        return None
    return "LOR"


def initial_generation_part(session: dict) -> str | None:
    """セッション作成直後に生成してよいAIパート（Opp生徒の PM のみ）。"""
    if not is_solo(session):
        return None
    if session.get("user_side") != "Opp":
        return None
    from debate.storage import get_part

    pm = get_part(session, "PM")
    if not part_is_ai(pm):
        return None
    status = str((pm or {}).get("generation_status") or "idle")
    if status in ("generating", "done"):
        return None
    return "PM"


def next_generation_targets(session: dict, confirmed_part: str) -> list[str]:
    """生徒パート確定後に開始すべきAIパート（チェーン先頭のみ返す）。"""
    if not is_solo(session):
        return []
    from debate.storage import get_part

    confirmed_index = PART_ORDER.index(confirmed_part) if confirmed_part in PART_ORDER else -1
    if confirmed_index < 0:
        return []

    for name in PART_ORDER[confirmed_index + 1 :]:
        part_data = get_part(session, name)
        if not part_data:
            continue
        if not part_is_ai(part_data):
            return []
        status = str(part_data.get("generation_status") or "idle")
        if status == "done" and part_data.get("status") == "confirmed":
            continue
        if status == "generating":
            return []
        return [name]
    return []


def generation_view(part_data: dict | None) -> dict:
    data = part_data or {}
    return {
        "part": data.get("part"),
        "speaker": data.get("speaker") or "human",
        "status": data.get("status"),
        "generation_status": data.get("generation_status"),
        "generation_error": data.get("generation_error"),
        "tts_status": data.get("tts_status"),
        "tts_audio_file": data.get("tts_audio_file"),
        "transcript_edited": data.get("transcript_edited") or "",
        "elapsed_sec": data.get("elapsed_sec"),
    }


def tts_filename(part: str) -> str:
    return f"ai_{part}.mp3"
