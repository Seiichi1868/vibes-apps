"""音声は一時領域だけに書く。永続側は数値の受付記録。"""
from __future__ import annotations

import fcntl
import secrets
from pathlib import Path

import hashlib
import hmac

from speech_rec.assignments import (
    device_attempt_count,
    device_error_count,
    now,
    pending_count,
    reads_dir,
    records_dir,
    submission_count,
)
from speech_rec.config import DEVICE_SALT, QUEUE_LIMIT, audio_tmp_dir
from speech_rec.store import read_json, write_json

MAX_BYTES = 3 * 1024 * 1024
MAX_DURATION_MS = 75_000
MIN_BYTES = 5 * 1024
MIN_DURATION_MS = 8_000
AUDIO_TTL_SEC = 2 * 60 * 60
COUNTING = {"received", "queued", "processing", "done"}
VERIFY_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def device_hash(raw: str) -> str:
    """署名鍵と専用 salt から HMAC を作る。記録にはこの値だけを残す。"""
    from flask import current_app

    secret = str(current_app.config.get("SECRET_KEY") or "speech-rec-dev-secret")
    return hmac.new(secret.encode(), f"{DEVICE_SALT}:{raw}".encode(), hashlib.sha256).hexdigest()


def verify_code() -> str:
    raw = "".join(secrets.choice(VERIFY_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def read_token() -> str:
    return secrets.token_urlsafe(18)


def _ext(mime: str) -> str:
    mime = (mime or "").lower()
    if "mp4" in mime or "aac" in mime or "m4a" in mime:
        return "m4a"
    if "webm" in mime:
        return "webm"
    if "wav" in mime:
        return "wav"
    return "bin"


def sweep_audio(now_ts: float | None = None) -> None:
    import time

    root = audio_tmp_dir()
    if not root.is_dir():
        return
    cutoff = (now_ts if now_ts is not None else time.time()) - AUDIO_TTL_SEC
    for path in root.iterdir():
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def audio_bytes_used() -> int:
    root = audio_tmp_dir()
    if not root.is_dir():
        return 0
    total = 0
    for path in root.iterdir():
        if path.is_file() and path.name != ".lock" and not path.name.endswith(".view.json"):
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


def _lock():
    root = audio_tmp_dir()
    root.mkdir(parents=True, exist_ok=True)
    handle = (root / ".lock").open("a+")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _id_fields(form, settings: dict) -> dict | None:
    spec = settings.get("id_fields") or {}
    if not spec.get("enabled"):
        return None
    from speech_rec.assignments import school_year

    try:
        year = int(form.get("year"))
        grade = int(form.get("grade"))
        klass = int(form.get("class"))
        number = int(form.get("number"))
    except (TypeError, ValueError):
        raise ValueError("id_fields") from None
    if year != school_year() or grade not in (1, 2, 3):
        raise ValueError("id_fields")
    if not (1 <= klass <= int(spec.get("class_max") or 10)):
        raise ValueError("id_fields")
    if not (1 <= number <= int(spec.get("number_max") or 45)):
        raise ValueError("id_fields")
    return {"year": year, "grade": grade, "class": klass, "number": number}


def _client_metrics(raw: str) -> dict:
    import json

    try:
        stats = json.loads(raw or "{}")
    except json.JSONDecodeError:
        stats = {}
    if not isinstance(stats, dict):
        stats = {}
    out = {}
    for key in ("rms_p10", "rms_p90", "snr_db"):
        try:
            out[key] = round(float(stats.get(key)), 4)
        except (TypeError, ValueError):
            out[key] = None
    return out


def accept_audio(assignment: dict, *, file_bytes: bytes, mime: str, form, settings: dict) -> dict:
    """受付できれば記録。できなければ {'error': code}。音声は data/ に書かない。"""
    sweep_audio()
    raw_device = str(form.get("device_id") or "").strip()
    if len(raw_device) < 8 or len(raw_device) > 80:
        return {"error": "device"}
    device_id = device_hash(raw_device)
    try:
        duration_ms = int(form.get("duration_ms") or 0)
    except ValueError:
        return {"error": "duration"}
    if duration_ms > MAX_DURATION_MS or len(file_bytes) > MAX_BYTES:
        return {"error": "too_long"}
    if duration_ms < MIN_DURATION_MS or len(file_bytes) < MIN_BYTES:
        return {"error": "too_short"}

    try:
        fields = _id_fields(form, settings)
    except ValueError:
        return {"error": "id_fields"}

    retry_of = str(form.get("retry_of") or "").strip()
    cap = int(float(settings.get("audio_cap_mb") or 100) * 1024 * 1024)
    lock = _lock()
    try:
        if pending_count() >= QUEUE_LIMIT:
            return {"error": "busy"}
        if audio_bytes_used() + len(file_bytes) > cap:
            return {"error": "busy"}
        if retry_of:
            return _retry(assignment, retry_of, device_id, file_bytes, mime, duration_ms, form)
        error_cap = int(assignment.get("attempts_per_device") or 5) * 2
        if device_error_count(assignment["id"], device_id) >= error_cap:
            return {"error": "attempts"}
        if submission_count(assignment["id"]) >= int(assignment.get("max_submissions") or 0):
            return {"error": "full"}
        used = device_attempt_count(assignment["id"], device_id)
        if used >= int(assignment.get("attempts_per_device") or 5):
            return {"error": "attempts"}
        record_id = secrets.token_hex(6)
        token = read_token()
        path = _write_audio(record_id, file_bytes, mime)
        record = _base_record(assignment, record_id, device_id, token, duration_ms, form, fields, attempt=used + 1)
        write_json(records_dir(assignment["id"]) / f"{record_id}.json", record)
        write_json(reads_dir() / f"{token}.json", {"assignment_id": assignment["id"], "record_id": record_id})
        _queue(assignment["id"], record_id)
        return {"read_token": token, "attempt": record["attempt"], "record_id": record_id}
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def _write_audio(record_id: str, file_bytes: bytes, mime: str) -> Path:
    path = audio_tmp_dir() / f"{record_id}.{_ext(mime)}"
    path.write_bytes(file_bytes)
    return path


def _base_record(assignment, record_id, device_id, token, duration_ms, form, fields, *, attempt: int) -> dict:
    metrics = _client_metrics(str(form.get("client_stats") or ""))
    metrics["duration_ms"] = duration_ms
    return {
        "id": record_id,
        "assignment_id": assignment["id"],
        "created_at": now().isoformat(timespec="seconds"),
        "attempt": attempt,
        "retry_count": 0,
        "status": "received",
        "error_code": None,
        "device_id": device_id,
        "id_fields": fields,
        "verify_code": verify_code(),
        "read_token": token,
        "metrics": metrics,
    }


def _retry(assignment, retry_of, device_id, file_bytes, mime, duration_ms, form) -> dict:
    record = read_json(records_dir(assignment["id"]) / f"{retry_of}.json")
    if not isinstance(record, dict) or record.get("device_id") != device_id:
        return {"error": "retry"}
    if record.get("status") != "error":
        return {"error": "retry"}
    if int(record.get("retry_count") or 0) >= 3:
        return {"error": "retry"}
    _write_audio(record["id"], file_bytes, mime)
    record["retry_count"] = int(record.get("retry_count") or 0) + 1
    record["status"] = "received"
    record["error_code"] = None
    record["metrics"] = _base_record(
        assignment, record["id"], device_id, record["read_token"], duration_ms, form, record.get("id_fields"), attempt=record["attempt"]
    )["metrics"]
    write_json(records_dir(assignment["id"]) / f"{record['id']}.json", record)
    _queue(assignment["id"], record["id"])
    return {"read_token": record["read_token"], "attempt": record["attempt"], "retry": True}


def history_rows(tokens: list[str]) -> list[dict]:
    """端末が持つ read_token の数値だけを返す。本文は含めない。"""
    from speech_rec.assignments import get_assignment

    rows = []
    for token in tokens[:30]:
        record = load_by_read_token(token)
        if not isinstance(record, dict):
            rows.append({"read_token": token, "state": "expired"})
            continue
        scores = record.get("scores") if isinstance(record.get("scores"), dict) else {}
        assignment = get_assignment(str(record.get("assignment_id") or "")) or {}
        rows.append({
            "read_token": token,
            "state": record.get("status"),
            "created_at": record.get("created_at"),
            "topic": (assignment.get("topic") or {}).get("text") or "",
            "attempt": record.get("attempt"),
            "total": scores.get("total"),
            "points": scores.get("points") or {},
            "levels": record.get("levels") or {},
            "wpm_points": scores.get("wpm_points"),
            "verify_code": record.get("verify_code"),
            "show_points": bool(assignment.get("show_points", True)),
        })
    return rows


def load_by_read_token(token: str) -> dict | None:
    pointer = read_json(reads_dir() / f"{token}.json")
    if not isinstance(pointer, dict):
        return None
    record = read_json(records_dir(pointer["assignment_id"]) / f"{pointer['record_id']}.json")
    return record if isinstance(record, dict) else None


def _queue(assignment_id: str, record_id: str) -> None:
    from speech_rec.jobs import enqueue

    enqueue(assignment_id, record_id)


def public_status(record: dict, *, detail: bool = False) -> dict:
    from speech_rec.assignments import get_assignment
    from speech_rec.jobs import load_view
    from speech_rec.metrics import FILLERS, normalize_word

    metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
    scores = record.get("scores") if isinstance(record.get("scores"), dict) else {}
    assignment = get_assignment(str(record.get("assignment_id") or "")) or {}
    view = load_view(str(record.get("id") or "")) if record.get("status") == "done" or detail else None
    feedback = (view or {}).get("student_feedback") if isinstance((view or {}).get("student_feedback"), dict) else {}
    body = {
        "ok": True,
        "status": record.get("status"),
        "error_code": record.get("error_code"),
        "id": record.get("id"),
        "attempt": record.get("attempt"),
        "attempts_per_device": int(assignment.get("attempts_per_device") or 5),
        "verify_code": record.get("verify_code"),
        "created_at": record.get("created_at"),
        "topic": (assignment.get("topic") or {}).get("text") or "",
        "show_points": bool(assignment.get("show_points", True)),
        "words_counted": metrics.get("words_counted"),
        "wpm_points": scores.get("wpm_points"),
        "levels": record.get("levels") or {},
        "scores": scores,
        "oreo": record.get("oreo") or {},
        "flags": record.get("flags") or [],
        "next_step": feedback.get("next_step") or "",
    }
    from speech_rec.delivery import delivery_reason
    from speech_rec.settings import get_settings

    settings = get_settings()
    reason = delivery_reason(
        metrics,
        settings.get("delivery_rules") or [],
        int((record.get("levels") or {}).get("delivery") or 0),
        noisy="noisy" in (record.get("flags") or []),
    )
    body["delivery_text"] = reason["text"]
    body["delivery_hint"] = reason["hint"]
    if detail:
        if view:
            words = view.get("words") or []
            fillers = [row[0] for row in words if isinstance(row, (list, tuple)) and normalize_word(row[0]) in FILLERS]
            body["transcript"] = view.get("transcript") or ""
            body["comments"] = view.get("comments") or {}
            body["evidence"] = view.get("evidence") or {}
            body["fillers"] = fillers
            body["detail_expired"] = False
        else:
            body["transcript"] = None
            body["detail_expired"] = True
    return body
