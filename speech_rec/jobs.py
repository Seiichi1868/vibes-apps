"""文字起こしの待ち行列。評価 AI はまだ呼ばない。音声は処理の直後に消す。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from speech_rec.assignments import get_assignment, now, records_dir
from speech_rec.config import audio_tmp_dir
from speech_rec.delivery import SOURCE as DELIVERY_SOURCE, delivery_level, delivery_reason
from speech_rec.evaluate import run_eval
from speech_rec.metrics import measure
from speech_rec.openai_client import SpeechRecAIError, transcribe_words
from speech_rec.rubric import PROMPT_VERSION, RUBRIC_VERSION
from speech_rec.scoring import cap_delivery_level, score as score_levels, speaking_wpm
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
WHISPER_HINT = "Um, uh, so, well, I think, you know, like... Okay."

enabled = True
_pool: ThreadPoolExecutor | None = None
_transcribe = transcribe_words
_evaluate = run_eval


def start() -> None:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="speech_rec")
    sweep_audio()
    sweep_views()
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
        prompt = WHISPER_HINT if settings.get("whisper_hint") else ""
        result = _transcribe(audio, language="en", prompt=prompt)
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
            text=text,
            sentence_gap_min=float(settings.get("sentence_gap_min") or 2),
            clause_gap_min=float(settings.get("clause_gap_min") or 1.2),
            mid_gap_min=float(settings.get("mid_gap_min") or 0.5),
            unknown_gap_min=float(settings.get("unknown_gap_min") or 1),
        )
        metrics.pop("boundaries", None)
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
        try:
            _finish_scores(assignment, record_id, metrics, text, cost, settings)
        except SpeechRecAIError:
            _fail(assignment_id, record_id, "eval_failed", metrics=metrics, cost=cost)
    except SpeechRecAIError:
        _fail(assignment_id, record_id, "whisper_failed")
    finally:
        if not settings.get("calibration_mode"):
            _delete_audio(record_id)


def reevaluate(assignment_id: str, record_id: str) -> None:
    """文字起こしが残っていれば Whisper を呼ばずに評価だけやり直す。"""
    record = _load(assignment_id, record_id)
    view = load_view(record_id)
    if not record or not view or not str(view.get("transcript") or "").strip():
        _fail(assignment_id, record_id, "eval_failed")
        return
    settings = get_settings()
    assignment = get_assignment(assignment_id) or {}
    metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
    try:
        _finish_scores(assignment, record_id, metrics, str(view.get("transcript")), float(record.get("cost_usd") or 0), settings)
    except SpeechRecAIError:
        _fail(assignment_id, record_id, "eval_failed", metrics=metrics, cost=record.get("cost_usd"))


def enqueue_eval(assignment_id: str, record_id: str) -> None:
    if not enabled:
        reevaluate(assignment_id, record_id)
        return
    start()
    assert _pool is not None
    _pool.submit(reevaluate, assignment_id, record_id)


def _finish_scores(assignment: dict, record_id: str, metrics: dict, transcript: str, whisper_cost: float, settings: dict) -> None:
    topic = (assignment.get("topic") or {}).get("text") or ""
    model = str(settings.get("eval_model") or "gpt-4o-mini")
    parsed = _evaluate(
        topic,
        transcript,
        int(assignment.get("speak_sec") or 60),
        model,
        words_counted=int(metrics.get("words_counted") or 0),
    )
    levels = dict(parsed["levels"])
    levels["delivery"] = delivery_level(metrics, settings.get("delivery_rules") or [])
    pause_level = int(levels["delivery"])
    speak_sec = float(assignment.get("speak_sec") or 60)
    scored = score_levels(
        levels,
        int(metrics.get("words_counted") or 0),
        bool(parsed["on_topic"]),
        settings["score_config"],
        speak_sec=speak_sec,
    )
    levels["delivery"] = cap_delivery_level(pause_level, speaking_wpm(int(metrics.get("words_counted") or 0), speak_sec))
    flags = list(parsed["flags"])
    snr = metrics.get("snr_db")
    if isinstance(snr, (int, float)) and snr < NOISY_SNR_DB and "noisy" not in flags:
        flags.append("noisy")
    fresh = _load(assignment["id"], record_id) or {"id": record_id, "assignment_id": assignment.get("id")}
    fresh["status"] = "done"
    fresh["error_code"] = None
    fresh["metrics"] = metrics
    fresh["levels"] = levels
    fresh["oreo"] = parsed["oreo"]
    fresh["scores"] = scored
    fresh["flags"] = flags
    reason = delivery_reason(metrics, settings.get("delivery_rules") or [], pause_level, noisy="noisy" in flags)
    fresh["delivery_pause_level"] = pause_level
    fresh["wpm"] = scored.get("wpm")
    fresh["delivery_limiting"] = reason["limiting"]
    fresh["delivery_source"] = DELIVERY_SOURCE
    fresh["eval"] = {"model": parsed["model"], "prompt_version": parsed.get("prompt_version") or PROMPT_VERSION}
    fresh["rubric_version"] = RUBRIC_VERSION
    fresh["cost_usd"] = round(float(whisper_cost) + float(parsed["cost_usd"]), 6)
    for banned in ("transcript", "evidence", "comment", "sentences", "student_feedback"):
        fresh.pop(banned, None)
    _save(fresh)
    _merge_view(record_id, parsed["view"], settings)


def _merge_view(record_id: str, extra: dict, settings: dict) -> None:
    path = audio_tmp_dir() / f"{record_id}.view.json"
    current = read_json(path, {})
    if not isinstance(current, dict):
        current = {}
    current.update(extra)
    if "expires_at" not in current:
        current["expires_at"] = (now() + timedelta(minutes=int(settings.get("transcript_ttl_min") or 30))).isoformat(timespec="seconds")
    write_json(path, current)


def recover_stalled() -> None:
    """received / queued / processing が120秒を超えたら、音声が残っていれば1回だけ再投入する。"""
    root = records_dir("_").parent
    if not root.is_dir():
        return
    cutoff = now() - timedelta(seconds=STALL_SEC)
    pending = {"received", "queued", "processing"}
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        for path in folder.glob("*.json"):
            record = read_json(path)
            if not isinstance(record, dict) or record.get("status") not in pending:
                continue
            started = _parse_time(str(record.get("processing_started") or record.get("created_at") or ""))
            if started is None or started > cutoff:
                continue
            record_id = str(record.get("id") or path.stem)
            audio_left = _find_audio(record_id) is not None
            if audio_left and int(record.get("stall_requeues") or 0) < 1:
                record["stall_requeues"] = int(record.get("stall_requeues") or 0) + 1
                record["status"] = "queued"
                write_json(path, record)
                enqueue(str(record.get("assignment_id") or folder.name), record_id)
                continue
            record["status"] = "error"
            record["error_code"] = "whisper_failed"
            write_json(path, record)


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
    ttl = 24 * 60 if settings.get("calibration_mode") else int(settings.get("transcript_ttl_min") or 30)
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
