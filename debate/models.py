"""データスキーマ（PDA_debate_app_spec.md 「1. データスキーマ」）に準拠したデータ生成処理。"""
import uuid
from datetime import datetime, timedelta, timezone

from debate.config import (
    DEFAULT_AI_DIFFICULTY,
    PART_DEFS,
    PART_ORDER,
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


def new_session(
    motion: str,
    speaker_name: str = "",
    *,
    mode: str = "duo",
    user_side: str | None = None,
    ai_difficulty: str | None = None,
) -> dict:
    session_mode = "solo" if str(mode or "").strip().lower() == "solo" else "duo"
    side = user_side if session_mode == "solo" else None
    difficulty = ai_difficulty if session_mode == "solo" else None
    if session_mode == "solo":
        from debate.solo import speaker_for_part

        parts = [new_part(part, speaker=speaker_for_part(side or "Gov", part)) for part in PART_ORDER]
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
        "ai_difficulty": difficulty if session_mode == "solo" else None,
        "parts": parts,
        "judge_result": new_judge_result(),
    }


def normalize_session(session: dict | None) -> dict | None:
    """欠けている mode 等を duo 互換で補う。読み込み時のみ。ファイルは書き換えない。"""
    if not isinstance(session, dict):
        return session
    if str(session.get("mode") or "").strip().lower() != "solo":
        session["mode"] = "duo"
        session.setdefault("user_side", None)
        session.setdefault("ai_difficulty", None)
    else:
        session["mode"] = "solo"
        if session.get("ai_difficulty") not in ("easy", "normal", "hard"):
            session["ai_difficulty"] = DEFAULT_AI_DIFFICULTY
        if session.get("user_side") not in ("Gov", "Opp"):
            session["user_side"] = "Gov"

    from debate.solo import speaker_for_part

    user_side = session.get("user_side") if session["mode"] == "solo" else None
    for part_data in session.get("parts") or []:
        if not isinstance(part_data, dict):
            continue
        part_name = part_data.get("part")
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
    return session
