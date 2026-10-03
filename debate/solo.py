"""Solo Practice / パート練習用のセッション操作。

デュオの進行ロジックにモード分岐を散らかさず、ガードと担当割り当てをここに集約する。
既存セッションに `mode` が無い場合は duo とみなす（マイグレーションはしない）。
"""
from __future__ import annotations

import random

from debate.config import (
    DEFAULT_AI_DIFFICULTY,
    GOV_PARTS,
    OPP_PARTS,
    PART_DEFS,
    PART_ORDER,
    VALID_DIFFICULTIES,
    VALID_SIDES,
)

CONFLICT = 409


def session_mode(session: dict | None) -> str:
    mode = str((session or {}).get("mode") or "").strip().lower()
    if mode in ("solo", "practice"):
        return mode
    return "duo"


def is_solo(session: dict | None) -> bool:
    return session_mode(session) == "solo"


def is_practice(session: dict | None) -> bool:
    return session_mode(session) == "practice"


def uses_partner_flow(session: dict | None) -> bool:
    """前のパート確定後に次が解禁される進行（ソロとパート練習）。"""
    return session_mode(session) in ("solo", "practice")


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


def _normalize_role(value) -> str:
    raw = str(value or "").strip()
    lowered = raw.lower()
    if lowered in ("human", "self") or raw == "自分":
        return "human"
    if lowered == "ai":
        return "ai"
    return "none"


def parse_practice_roles(raw) -> tuple[list[tuple[str, str]] | None, str]:
    """パート練習の担当。PMから連続した human/ai だけを採用し、最初の未選択以降は範囲外。

    未選択のあとで human/ai が来たらエラー（途中飛ばしは不可）。
    自分が話すパートが1つ以上必要。
    """
    if not isinstance(raw, dict):
        return None, "各パートを、自分・AI・やらない から選んでください。"

    assignments: list[tuple[str, str]] = []
    stopped_at: str | None = None
    for part in PART_ORDER:
        role = _normalize_role(raw.get(part))
        if role == "none":
            if stopped_at is None:
                stopped_at = part
            continue
        if stopped_at:
            return None, (
                f"{stopped_at}を飛ばして{part}は選べません。"
                f"{stopped_at}を自分かAIにしてください。"
            )
        assignments.append((part, role))

    if not assignments:
        return None, "PMから練習する範囲を選んでください。"
    if not any(role == "human" for _, role in assignments):
        return None, "自分が練習するパートを1つ以上選んでください。"
    return assignments, ""


def practice_focus_side(assignments: list[tuple[str, str]]) -> str:
    """生徒パートが片方の陣営だけならその陣営、混在なら Both。"""
    sides = {PART_DEFS[part]["side"] for part, role in assignments if role == "human"}
    if sides == {"Gov"}:
        return "Gov"
    if sides == {"Opp"}:
        return "Opp"
    return "Both"


def part_is_omitted(part_data: dict | None) -> bool:
    if not isinstance(part_data, dict):
        return False
    if part_data.get("included") is False:
        return True
    if str(part_data.get("speaker") or "") == "none":
        return True
    return str(part_data.get("status") or "") == "omitted"


def included_part_names(session: dict | None) -> list[str]:
    if not is_practice(session):
        return list(PART_ORDER)
    from debate.storage import get_part

    names = []
    for name in PART_ORDER:
        if part_is_omitted(get_part(session, name)):
            continue
        names.append(name)
    return names


def practice_scope_label(session: dict | None) -> str:
    from debate.storage import get_part

    bits = []
    for name in included_part_names(session):
        who = "AI" if part_is_ai(get_part(session, name)) else "自分"
        bits.append(f"{name}（{who}）")
    return " → ".join(bits)


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
        if part_is_omitted(prior):
            continue
        if prior.get("status") != "confirmed":
            return False
        if not str(prior.get("transcript_edited") or "").strip():
            return False
    return True


def recording_guard(session: dict, part: str) -> tuple[bool, str]:
    """録音開始・音声保存・リアルタイム文字起こしの共通ガード。duo なら常に許可。"""
    if not uses_partner_flow(session):
        return True, ""

    from debate.storage import get_part

    part_data = get_part(session, part)
    if not part_data:
        return False, f"不明なパート: {part}"
    if part_is_omitted(part_data):
        return False, "このパートは練習範囲に含まれていません。"
    if part_is_ai(part_data):
        return False, "このパートは相手AIの担当です。"
    if not all_preceding_confirmed(session, part):
        return False, "前のパートを確定すると解禁されます。"
    return True, ""


def generation_guard(session: dict, part: str) -> tuple[bool, str]:
    """AI生成開始のガード。対象が AI かつ先行パートが全て confirmed のときのみ。"""
    if not uses_partner_flow(session):
        return False, "AIパートのないセッションです。"

    from debate.storage import get_part

    part_data = get_part(session, part)
    if not part_data:
        return False, f"不明なパート: {part}"
    if part_is_omitted(part_data):
        return False, "このパートは練習範囲に含まれていません。"
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
    """セッション作成直後に生成してよい先頭AIパート。

    ソロは Opp 生徒の PM のみ。パート練習は範囲の先頭が AI のとき（例: LO練習の PM）。
    """
    from debate.storage import get_part

    if is_practice(session):
        names = included_part_names(session)
        if not names:
            return None
        first = get_part(session, names[0])
        if not part_is_ai(first):
            return None
        status = str((first or {}).get("generation_status") or "idle")
        if status in ("generating", "done"):
            return None
        return names[0]

    if not is_solo(session):
        return None
    if session.get("user_side") != "Opp":
        return None

    pm = get_part(session, "PM")
    if not part_is_ai(pm):
        return None
    status = str((pm or {}).get("generation_status") or "idle")
    if status in ("generating", "done"):
        return None
    return "PM"


def next_generation_targets(session: dict, confirmed_part: str) -> list[str]:
    """生徒パート確定後に開始すべきAIパート（チェーン先頭のみ返す）。"""
    if not uses_partner_flow(session):
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
