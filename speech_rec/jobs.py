"""文字起こしの待ち行列。評価 AI はまだ呼ばない。音声は処理の直後に消す。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from speech_rec.assignments import get_assignment, now, records_dir
from speech_rec.config import audio_tmp_dir
from speech_rec.metrics import measure, wpm_points
from speech_rec.openai_client import SpeechRecAIError, transcribe_words
from speech_rec.pricing import WHISPER_MODEL, estimate_whisper_usd
from speech_rec.settings import get_settings
from speech_rec.store import read_json, write_json
from speech_rec.submissions import sweep_audio
from speech_rec.usage import record_cost

logger = logging.getLogger(__name__)

WORKERS = 6
STALL_SEC = 120
NOISY_SNR_DB = 15
MAX_WHISPER_SEC = 75
# ヒント文は、実音声で「フィラーが残るか / 無音を創作するか」を比べるまで付けない。
WHISPER_PROMPT = ""

enabled = True
_pool: ThreadPoolExecutor | None = None
_recovered = False
_transcribe = transcribe_words


def start() -> None:
    global _pool, _recovered
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="speech_rec")
    sweep_audio()
    sweep_views()
    if not _recovered:
        _recovered = True
        recover_stalled()


def enqueue(assignment_id: str, record_id: str) -> None:
    if not enabled:
        return
    start()
    assert _pool is not None
    _pool.submit(_safe_process, assignment_id, record_id)


def _safe_process(assignment_id: str, record_id: str) -> None:
    try:
        process(assignment_id, record_id)
    except Exception:
        logger.exception("speech_rec job crashed id=%s", record_id)
        _fail(assignment_id, record_id, "whisper_failed")


def process(assignment_id: str, record_id: str) -> None:
    record = _load(assignment_id, record_id)
    if not record or record.get("status") in {"done", "error"}:
        return
    assignment = get_assignment(assignment_id) or {}
    settings = get_settings()
    audio = _find_audio(record_id)
    record["status"] = "processing"
    record["processing_started"] = now().isoformat(timespec="seconds")
    _save(record)
    if audio is None:
        _fail(assignment_id, record_id, "whisper_failed")
        return
    try:
        result = _transcribe(audio, language="en", prompt=WHISPER_PROMPT)
        text, words, duration = _parse(result)
        if duration is not None and float(duration) > MAX_WHISPER_SEC:
            _fail(assignment_id, record_id, "too_long")
            return
        score_config = settings["score_config"]
        metrics = measure(
            words,
            speak_sec=float(assignment.get("speak_sec") or 60),
            grace_sec=float(score_config.get("grace_sec") or 0),
            pause_gap_sec=float(settings.get("pause_gap_sec") or 0.8),
            exclude_fillers=bool(score_config.get("exclude_nonlexical_fillers", True)),
        )
        client = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
        for key in ("rms_p10", "rms_p90", "snr_db", "duration_ms"):
            if key in client:
                metrics[key] = client[key]
        billed = float(duration if duration is not None else (metrics.get("duration_ms") or 0) / 1000.0)
        cost = estimate_whisper_usd(billed or 1)
        record_cost(cost, kind="whisper", model=WHISPER_MODEL)
        if billed and billed < 8:
            _fail(assignment_id, record_id, "silent", metrics=metrics, cost=cost)
            return
        if metrics["words_counted"] < 5:
            _fail(assignment_id, record_id, "too_short", metrics=metrics, cost=cost)
            return
        _write_view(record_id, text, words, settings)
        flags = []
        snr = metrics.get("snr_db")
        if isinstance(snr, (int, float)) and snr < NOISY_SNR_DB:
            flags.append("noisy")
        if metrics["words_counted"] < 30:
            flags.append("short_speech")
        fresh = _load(assignment_id, record_id) or record
        fresh["status"] = "done"
        fresh["error_code"] = None
        fresh["metrics"] = metrics
        fresh["scores"] = {
            "wpm_points": wpm_points(metrics["words_counted"], score_config),
            "config_version": score_config.get("version"),
        }
        fresh["flags"] = flags
        fresh["cost_usd"] = round(cost, 6)
        fresh.pop("transcript", None)
        _save(fresh)
    except SpeechRecAIError as exc:
        _fail(assignment_id, record_id, "whisper_failed" if exc.code != "no_api_key" else "whisper_failed")
    finally:
        if not settings.get("calibration_mode"):
            _delete_audio(record_id)


def recover_stalled() -> None:
    root = records_dir("")
    parent = root.parent
    if not parent.is_dir():
        return
    cutoff = now() - timedelta(seconds=STALL_SEC)
    for folder in parent.iterdir():
        if not folder.is_dir():
            continue
        for path in folder.glob("*.json"):
            record = read_json(path)
            if not isinstance(record, dict) or record.get("status") != "processing":
                continue
            started = _parse_time(str(record.get("processing_started") or ""))
            if started is None or started > cutoff:
                continue
            if int(record.get("stall_requeues") or 0) >= 1:
                record["status"] = "error"
                record["error_code"] = "whisper_failed"
                write_json(path, record)
                continue
            record["stall_requeues"] = int(record.get("stall_requeues") or 0) + 1
            record["status"] = "queued"
            write_json(path, record)
            enqueue(str(record.get("assignment_id") or folder.name), str(record.get("id") or path.stem))


def sweep_views() -> None:
    root = audio_tmp_dir()
    if not root.is_dir():
        return
    ttl = int(get_settings().get("transcript_ttl_min") or 30) * 60
    import time

    cutoff = time.time() - ttl
    for path in root.glob("*.view.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def load_view(record_id: str) -> dict | None:
    path = audio_tmp_dir() / f"{record_id}.view.json"
    row = read_json(path)
    if not isinstance(row, dict):
        return None
    expires = _parse_time(str(row.get("expires_at") or ""))
    if expires is not None and expires <= now():
        try:
            path.unlink()
        except OSError:
            pass
        return None
    return row


def _write_view(record_id: str, text: str, words: list, settings: dict) -> None:
    ttl = int(settings.get("transcript_ttl_min") or 30)
    payload = {
        "transcript": text,
        "words": [[word, start, end] for word, start, end in words],
        "expires_at": (now() + timedelta(minutes=ttl)).isoformat(timespec="seconds"),
    }
    write_json(audio_tmp_dir() / f"{record_id}.view.json", payload)


def _parse(result):
    if isinstance(result, dict):
        raw_words = result.get("words") or []
        text = str(result.get("text") or "")
        duration = result.get("duration")
    else:
        raw_words = getattr(result, "words", None) or []
        text = str(getattr(result, "text", "") or "")
        duration = getattr(result, "duration", None)
    words = []
    for item in raw_words:
        if isinstance(item, dict):
            words.append((str(item.get("word") or ""), float(item.get("start") or 0), float(item.get("end") or 0)))
        else:
            words.append((str(getattr(item, "word", "") or ""), float(getattr(item, "start", 0) or 0), float(getattr(item, "end", 0) or 0)))
    return text, words, duration


def _find_audio(record_id: str) -> Path | None:
    root = audio_tmp_dir()
    if not root.is_dir():
        return None
    for path in root.glob(f"{record_id}.*"):
        if path.name.endswith(".view.json") or path.name == ".lock":
            continue
        if path.is_file():
            return path
    return None


def _delete_audio(record_id: str) -> None:
    path = _find_audio(record_id)
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        logger.warning("speech_rec audio delete failed id=%s", record_id)


def _load(assignment_id: str, record_id: str) -> dict | None:
    row = read_json(records_dir(assignment_id) / f"{record_id}.json")
    return row if isinstance(row, dict) else None


def _save(record: dict) -> None:
    write_json(records_dir(record["assignment_id"]) / f"{record['id']}.json", record)


def _fail(assignment_id: str, record_id: str, code: str, *, metrics: dict | None = None, cost: float | None = None) -> None:
    record = _load(assignment_id, record_id)
    if not record:
        return
    record["status"] = "error"
    record["error_code"] = code
    if metrics is not None:
        record["metrics"] = metrics
    if cost is not None:
        record["cost_usd"] = round(cost, 6)
    record.pop("transcript", None)
    _save(record)


def _parse_time(value: str) -> datetime | None:
    from speech_rec.assignments import parse_time

    return parse_time(value)
