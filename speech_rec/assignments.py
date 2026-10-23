"""出題の作成、期限、件数。件数はディレクトリを数える。"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from speech_rec.config import data_dir
from speech_rec.store import list_json_files, read_json, write_json

JST = ZoneInfo("Asia/Tokyo")
TTL_HOURS = (3, 24, 168)
COUNTING_STATUSES = {"received", "queued", "processing", "done"}
PENDING_STATUSES = {"received", "queued", "processing"}


def now() -> datetime:
    return datetime.now(JST)


def school_year(moment: datetime | None = None) -> int:
    moment = moment or now()
    return moment.year if moment.month >= 4 else moment.year - 1


def assignments_dir():
    return data_dir() / "assignments"


def records_dir(assignment_id: str):
    return data_dir() / "records" / assignment_id


def reads_dir():
    return data_dir() / "reads"


def _new_id() -> str:
    return secrets.token_hex(6)


def create_assignment(payload: dict) -> dict:
    text = str(payload.get("text") or "").strip()
    if not text:
        raise ValueError("topic")
    if len(text) > 2000:
        raise ValueError("topic")
    hours = int(payload.get("ttl_hours") or 24)
    if hours not in TTL_HOURS:
        raise ValueError("ttl")
    prep = 60 if payload.get("prep_sec") is None else int(payload.get("prep_sec"))
    speak = int(payload.get("speak_sec") or 60)
    if not (0 <= prep <= 180 and 10 <= speak <= 180):
        raise ValueError("seconds")
    limit = int(payload.get("max_submissions") or 40)
    if not (1 <= limit <= 200):
        raise ValueError("limit")
    created = now()
    row = {
        "id": _new_id(),
        "token": secrets.token_urlsafe(16),
        "created_at": created.isoformat(timespec="seconds"),
        "expires_at": (created + timedelta(hours=hours)).isoformat(timespec="seconds"),
        "status": "open",
        "topic": {"text": text, "source_id": str(payload.get("source_id") or "")},
        "label": str(payload.get("label") or "").strip()[:80],
        "prep_sec": prep,
        "speak_sec": speak,
        "grace_sec": 3,
        "max_submissions": limit,
        "attempts_per_device": 5,
        "show_points": bool(payload.get("show_points", True)),
        "rubric_version": "s5-sem2-v1",
    }
    write_json(assignments_dir() / f"{row['id']}.json", row)
    return row


def get_assignment(assignment_id: str) -> dict | None:
    row = read_json(assignments_dir() / f"{assignment_id}.json")
    return row if isinstance(row, dict) else None


def find_by_token(token: str) -> dict | None:
    if not token or "/" in token or len(token) > 80:
        return None
    for path in list_json_files(assignments_dir()):
        row = read_json(path)
        if isinstance(row, dict) and row.get("token") == token:
            return row
    return None


def list_assignments() -> list[dict]:
    rows = []
    for path in list_json_files(assignments_dir()):
        row = read_json(path)
        if isinstance(row, dict):
            rows.append(row)
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return rows


def parse_time(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=JST)
    return moment


def availability(row: dict, *, student_enabled: bool) -> str | None:
    """入れない理由。入れるなら None。"""
    if not student_enabled:
        return "preparing"
    if row.get("status") != "open":
        return "closed"
    expires = parse_time(str(row.get("expires_at") or ""))
    if expires is None or expires <= now():
        return "expired"
    if submission_count(row["id"]) >= int(row.get("max_submissions") or 0):
        return "full"
    return None


def submission_count(assignment_id: str) -> int:
    total = 0
    for path in list_json_files(records_dir(assignment_id)):
        row = read_json(path)
        if isinstance(row, dict) and row.get("status") in COUNTING_STATUSES:
            total += 1
    return total


def live_counts(assignment_id: str) -> dict:
    buckets = {"received": 0, "processing": 0, "done": 0, "error": 0}
    for path in list_json_files(records_dir(assignment_id)):
        row = read_json(path)
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "")
        if status in {"received", "queued"}:
            buckets["received"] += 1
        elif status == "processing":
            buckets["processing"] += 1
        elif status == "done":
            buckets["done"] += 1
        elif status == "error":
            buckets["error"] += 1
    return buckets


def close_assignment(assignment_id: str) -> dict | None:
    row = get_assignment(assignment_id)
    if not row:
        return None
    row["status"] = "closed"
    write_json(assignments_dir() / f"{assignment_id}.json", row)
    return row


def public_view(row: dict, *, student_enabled: bool, id_fields: dict, calibration_mode: bool = False) -> dict:
    reason = availability(row, student_enabled=student_enabled)
    return {
        "ok": reason is None,
        "reason": reason,
        "topic": (row.get("topic") or {}).get("text") or "",
        "prep_sec": row.get("prep_sec"),
        "speak_sec": row.get("speak_sec"),
        "show_points": bool(row.get("show_points", True)),
        "attempts_per_device": int(row.get("attempts_per_device") or 5),
        "id_fields": id_fields,
        "school_year": school_year(),
        "calibration_mode": calibration_mode,
        "remaining": max(0, int(row.get("max_submissions") or 0) - submission_count(row["id"])),
    }


def pending_count() -> int:
    root = data_dir() / "records"
    if not root.is_dir():
        return 0
    total = 0
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        for path in list_json_files(folder):
            row = read_json(path)
            if isinstance(row, dict) and row.get("status") in PENDING_STATUSES:
                total += 1
    return total


def device_error_count(assignment_id: str, device_id: str) -> int:
    total = 0
    for path in list_json_files(records_dir(assignment_id)):
        row = read_json(path)
        if isinstance(row, dict) and row.get("device_id") == device_id and row.get("status") == "error":
            total += 1
    return total


def device_attempt_count(assignment_id: str, device_id: str) -> int:
    total = 0
    for path in list_json_files(records_dir(assignment_id)):
        row = read_json(path)
        if not isinstance(row, dict) or row.get("device_id") != device_id:
            continue
        if row.get("status") in COUNTING_STATUSES:
            total += 1
    return total
