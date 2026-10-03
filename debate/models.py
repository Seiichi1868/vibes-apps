"""データスキーマ（PDA_debate_app_spec.md 「1. データスキーマ」）に準拠したデータ生成処理。"""
import uuid
from datetime import datetime, timedelta, timezone

from debate.config import (
    DEFAULT_AI_DIFFICULTY,
    PART_DEFS,
    PART_ORDER,
    POI_DURATION_SEC,
    POI_STATUSES,
)

JST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def new_part(part: str, *, speaker: str = "human") -> dict:
    defaults = PART_DEFS[part]
    is_ai = speaker == "ai"
    return {
        "part": part,
        "side": defaults["side"],
        "part_order": defaults["part_order"],
        "speaker_name": "",
        "speaker": "ai" if is_ai else "human",
        "included": True,
        "audio_url": "",
        "transcript_raw": "",
        "transcript_edited": "",
        "transcript_error": "",
        "transcription_mode": "",
        "transcribe_retry_at": None,
        "start_time": None,
        "end_time": None,
        "time_limit_sec": defaults["time_limit_sec"],
        "elapsed_sec": None,
        "pois": [],
        "status": "not_started",
        "generation_status": "idle" if is_ai else None,
        "generation_error": None,
        "generation_started_at": None,
        "generation_retry_at": None,
        "generation_id": None,
        "tts_status": "idle" if is_ai else None,
        "tts_error": None,
        "tts_audio_file": None,
        "tts_started_at": None,
        "tts_retry_at": None,
        "tts_id": None,
    }


def new_judge_result() -> dict:
    """ジャッジ結果の空の器（status: idle→judging→done/error）。"""
    return {
        "status": "idle",
        "error": "",
        "model": "",
        "judge_model": None,
        "transcription_mode": "",
        "started_at": None,
        "judged_at": None,
        "argument_flow": [],
        "winner": None,
        "standing_point_count": {"gov": 0, "opp": 0},
        "scores": {
            "content": {"reasoning": None, "examples": None, "relevance": None},
            "method": {
                "rebuttal_accuracy": None,
                "flow_consistency": None,
                "role_fulfillment": None,
            },
        },
        "overall_feedback": "",
        "part_feedback": [{"part": part, "comment": ""} for part in PART_ORDER],
    }


def new_omitted_part(part: str) -> dict:
    data = new_part(part, speaker="human")
    data["speaker"] = "none"
    data["included"] = False
    data["status"] = "omitted"
    data["generation_status"] = None
    data["generation_error"] = None
    data["tts_status"] = None
    data["tts_error"] = None
    data["tts_audio_file"] = None
    return data


def new_session(
    motion: str,
    speaker_name: str = "",
    *,
    mode: str = "duo",
    user_side: str | None = None,
    ai_difficulty: str | None = None,
    practice_roles: list[tuple[str, str]] | None = None,
) -> dict:
    raw_mode = str(mode or "").strip().lower()
    if raw_mode == "solo":
        session_mode = "solo"
    elif raw_mode == "practice":
        session_mode = "practice"
    else:
        session_mode = "duo"
    side = user_side if session_mode in ("solo", "practice") else None
    difficulty = ai_difficulty if session_mode in ("solo", "practice") else None
    if session_mode == "solo":
        from debate.solo import speaker_for_part

        parts = [new_part(part, speaker=speaker_for_part(side or "Gov", part)) for part in PART_ORDER]
    elif session_mode == "practice":
        assigned = {part: speaker for part, speaker in (practice_roles or [])}
        parts = []
        for part in PART_ORDER:
            if part in assigned:
                parts.append(new_part(part, speaker=assigned[part]))
            else:
                parts.append(new_omitted_part(part))
    else:
        parts = [new_part(part) for part in PART_ORDER]
    if speaker_name:
        for part in parts:
            part["speaker_name"] = speaker_name

    return {
        "session_id": str(uuid.uuid4()),
        "motion": motion.strip(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "admin_notes": "",
        "copied_from_session_id": "",
        "mode": session_mode,
        "user_side": side,
        "ai_difficulty": difficulty if session_mode in ("solo", "practice") else None,
        "parts": parts,
        "judge_result": new_judge_result(),
    }


def normalize_session(session: dict | None) -> dict | None:
    """欠けている mode 等を duo 互換で補う。読み込み時のみ。ファイルは書き換えない。"""
    if not isinstance(session, dict):
        return session
    raw_mode = str(session.get("mode") or "").strip().lower()
    if raw_mode == "solo":
        session["mode"] = "solo"
        if session.get("ai_difficulty") not in ("easy", "normal", "hard"):
            session["ai_difficulty"] = DEFAULT_AI_DIFFICULTY
        if session.get("user_side") not in ("Gov", "Opp"):
            session["user_side"] = "Gov"
    elif raw_mode == "practice":
        session["mode"] = "practice"
        session.setdefault("user_side", None)
        if session.get("ai_difficulty") not in ("easy", "normal", "hard", None):
            session["ai_difficulty"] = DEFAULT_AI_DIFFICULTY
    else:
        from debate.solo import part_is_omitted

        parts = session.get("parts") or []
        has_omitted = any(isinstance(p, dict) and part_is_omitted(p) for p in parts)
        if has_omitted:
            session["mode"] = "practice"
            session.setdefault("user_side", None)
            if session.get("ai_difficulty") not in ("easy", "normal", "hard", None):
                session["ai_difficulty"] = DEFAULT_AI_DIFFICULTY
        else:
            session["mode"] = "duo"
            session.setdefault("user_side", None)
            session.setdefault("ai_difficulty", None)

    from debate.solo import part_is_omitted, speaker_for_part

    user_side = session.get("user_side") if session["mode"] == "solo" else None
    for part_data in session.get("parts") or []:
        if not isinstance(part_data, dict):
            continue
        part_name = part_data.get("part")
        if session["mode"] == "practice" and part_is_omitted(part_data):
            part_data["speaker"] = "none"
            part_data["included"] = False
            if part_data.get("status") in (None, "", "not_started"):
                part_data["status"] = "omitted"
            part_data.setdefault("generation_status", None)
            part_data.setdefault("generation_error", None)
            part_data.setdefault("tts_status", None)
            part_data.setdefault("tts_audio_file", None)
            part_data["pois"] = normalize_pois(part_data.get("pois"))
            continue
        if "speaker" not in part_data:
            if session["mode"] == "solo" and user_side and part_name:
                part_data["speaker"] = speaker_for_part(user_side, part_name)
            else:
                part_data["speaker"] = "human"
        if part_data.get("speaker") == "ai":
            part_data.setdefault("generation_status", "idle")
            part_data.setdefault("generation_error", None)
            part_data.setdefault("tts_status", "idle")
            part_data.setdefault("tts_audio_file", None)
            part_data.setdefault("tts_error", None)
        else:
            part_data.setdefault("generation_status", None)
            part_data.setdefault("generation_error", None)
            part_data.setdefault("tts_status", None)
            part_data.setdefault("tts_audio_file", None)
        part_data["pois"] = normalize_pois(part_data.get("pois"))
    return session


def normalize_pois(raw) -> list:
    """POI記録を安全なリストに正規化する。文字列JSONも受け付ける。"""
    if isinstance(raw, str):
        import json

        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return []
    if not isinstance(raw, list):
        return []

    out = []
    for item in raw[:20]:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip()
        if status not in POI_STATUSES:
            continue
        try:
            offered_at = int(item.get("offered_at_sec", 0) or 0)
        except (TypeError, ValueError):
            continue
        try:
            duration = int(item.get("duration_sec", 0) or 0)
        except (TypeError, ValueError):
            duration = 0
        try:
            ended_at = int(item.get("ended_at_sec", offered_at) or offered_at)
        except (TypeError, ValueError):
            ended_at = offered_at
        out.append(
            {
                "offered_at_sec": max(0, offered_at),
                "status": status,
                "duration_sec": max(0, min(duration, POI_DURATION_SEC + 5)),
                "ended_at_sec": max(0, ended_at),
            }
        )
    return out
