"""Solo Practice の非同期生成ジョブ（judge_jobs.py と同じ起動方式）。

テキスト生成 → TTS の2段。Gov生徒のときは同一チェーンで MO → LOR。
TTS失敗でテキスト成功を巻き戻さない。同じパートのTTSは再生成しない。
"""
from __future__ import annotations

import logging
import threading
import uuid

from debate.config import GENERATION_STUCK_SEC, TTS_STUCK_SEC
from debate.models import now_iso
from debate.opponent import generate_speech
from debate.solo import chain_successor, generation_guard, part_is_ai, tts_filename
from debate.storage import get_part, get_session_lock, load_session, save_session
from debate.tts import save_part_tts, synthesize_speech, tts_path

logger = logging.getLogger(__name__)

_pool = None
_pool_lock = threading.Lock()
_use_gevent = False


def _socket_is_patched() -> bool:
    try:
        from gevent import monkey

        return bool(monkey.is_module_patched("socket"))
    except Exception:
        return False


def _get_pool():
    global _pool, _use_gevent
    with _pool_lock:
        if _pool is not None:
            return _pool
        if _socket_is_patched():
            try:
                from gevent.threadpool import ThreadPool

                _pool = ThreadPool(3)
                _use_gevent = True
                logger.info("debate solo: using gevent.threadpool.ThreadPool")
                return _pool
            except Exception as exc:  # noqa: BLE001
                logger.warning("debate solo: gevent threadpool unavailable (%s)", exc)
        from concurrent.futures import ThreadPoolExecutor

        _pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="debate-solo")
        _use_gevent = False
        logger.info("debate solo: using ThreadPoolExecutor")
        return _pool


def _spawn(func, *args) -> None:
    pool = _get_pool()
    if _use_gevent:
        try:
            pool.spawn(func, *args)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("debate solo: gevent spawn failed (%s); using thread", exc)
    if hasattr(pool, "submit"):
        pool.submit(func, *args)
        return
    thread = threading.Thread(target=func, args=args, daemon=True, name="debate-solo")
    thread.start()


def _mark_text_generating(session_id: str, part: str, *, is_retry: bool) -> str | None:
    """生成中なら既存IDを返す。新規なら generation_id を返す。"""
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return None
        ok, _ = generation_guard(session, part)
        if not ok:
            return None
        part_data = get_part(session, part)
        if not part_data:
            return None
        status = str(part_data.get("generation_status") or "idle")
        if status == "generating" and part_data.get("generation_id") and not is_retry:
            return str(part_data["generation_id"])
        if status == "done" and str(part_data.get("transcript_edited") or "").strip() and not is_retry:
            return None
        job_id = uuid.uuid4().hex
        part_data["generation_status"] = "generating"
        part_data["generation_error"] = None
        part_data["generation_started_at"] = now_iso()
        part_data["generation_id"] = job_id
        if is_retry:
            part_data["generation_retry_at"] = now_iso()
        save_session(session)
        return job_id


def _save_text_success(session_id: str, part: str, job_id: str, text: str) -> bool:
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return False
        part_data = get_part(session, part)
        if not part_data or part_data.get("generation_id") != job_id:
            return False
        if part_data.get("generation_status") != "generating":
            return False
        part_data["transcript_raw"] = text
        part_data["transcript_edited"] = text
        part_data["transcript_error"] = ""
        part_data["elapsed_sec"] = None
        part_data["status"] = "confirmed"
        part_data["generation_status"] = "done"
        part_data["generation_error"] = None
        if part_data.get("tts_status") not in ("done", "generating"):
            part_data["tts_status"] = "idle"
        save_session(session)
        return True


def _save_text_error(session_id: str, part: str, job_id: str, message: str) -> None:
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return
        part_data = get_part(session, part)
        if not part_data or part_data.get("generation_id") != job_id:
            return
        if part_data.get("generation_status") != "generating":
            return
        part_data["generation_status"] = "error"
        part_data["generation_error"] = message
        save_session(session)


def _mark_tts_generating(session_id: str, part: str, *, is_retry: bool) -> str | None:
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return None
        part_data = get_part(session, part)
        if not part_data or not part_is_ai(part_data):
            return None
        if part_data.get("generation_status") != "done":
            return None
        if not str(part_data.get("transcript_edited") or "").strip():
            return None
        existing = tts_path(session_id, part_data.get("tts_audio_file") or tts_filename(part))
        if existing and part_data.get("tts_status") == "done" and not is_retry:
            return None
        if part_data.get("tts_status") == "generating" and part_data.get("tts_id") and not is_retry:
            return str(part_data["tts_id"])
        job_id = uuid.uuid4().hex
        part_data["tts_status"] = "generating"
        part_data["tts_error"] = None
        part_data["tts_started_at"] = now_iso()
        part_data["tts_id"] = job_id
        if is_retry:
            part_data["tts_retry_at"] = now_iso()
        save_session(session)
        return job_id


def _save_tts_success(session_id: str, part: str, job_id: str, filename: str) -> None:
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return
        part_data = get_part(session, part)
        if not part_data or part_data.get("tts_id") != job_id:
            return
        part_data["tts_status"] = "done"
        part_data["tts_audio_file"] = filename
        part_data["tts_error"] = None
        save_session(session)


def _save_tts_error(session_id: str, part: str, job_id: str, message: str) -> None:
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return
        part_data = get_part(session, part)
        if not part_data or part_data.get("tts_id") != job_id:
            return
        part_data["tts_status"] = "error"
        part_data["tts_error"] = message
        save_session(session)


def run_tts_job(session_id: str, part: str, job_id: str) -> None:
    session = load_session(session_id)
    if not session:
        return
    part_data = get_part(session, part)
    if not part_data:
        return
    text = str(part_data.get("transcript_edited") or "").strip()
    error_message = ""
    filename = ""
    try:
        audio_bytes = synthesize_speech(text)
        filename = save_part_tts(session_id, part, audio_bytes)
    except RuntimeError as exc:
        error_message = str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("TTS failed session=%s part=%s: %s", session_id, part, exc)
        error_message = f"音声の生成に失敗しました（{type(exc).__name__}）。"

    if error_message:
        _save_tts_error(session_id, part, job_id, error_message)
        return
    _save_tts_success(session_id, part, job_id, filename)
    logger.info("TTS finished session=%s part=%s file=%s", session_id, part, filename)


def start_tts_job(session_id: str, part: str, *, force: bool = False) -> dict | None:
    job_id = _mark_tts_generating(session_id, part, is_retry=force)
    if not job_id:
        session = load_session(session_id)
        return get_part(session, part) if session else None
    _spawn(run_tts_job, session_id, part, job_id)
    session = load_session(session_id)
    return get_part(session, part) if session else None


def run_generation_job(session_id: str, part: str, job_id: str) -> None:
    session = load_session(session_id)
    if not session:
        return
    error_message = ""
    text = ""
    try:
        text = generate_speech(session, part)
    except RuntimeError as exc:
        error_message = str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Opponent failed session=%s part=%s: %s", session_id, part, exc)
        error_message = f"相手の発話生成に失敗しました（{type(exc).__name__}）。"

    if error_message:
        _save_text_error(session_id, part, job_id, error_message)
        return

    if not _save_text_success(session_id, part, job_id, text):
        return

    start_tts_job(session_id, part)

    session = load_session(session_id)
    if not session:
        return
    successor = chain_successor(session, part)
    if successor:
        start_generation_job(session_id, successor)


def start_generation_job(session_id: str, part: str, *, force: bool = False) -> dict | None:
    session = load_session(session_id)
    if not session:
        return None
    part_data = get_part(session, part)
    if not part_data:
        return None
    status = str(part_data.get("generation_status") or "idle")
    if status == "generating" and not force:
        return part_data
    if status == "done" and str(part_data.get("transcript_edited") or "").strip() and not force:
        if part_data.get("tts_status") in (None, "idle", "error"):
            start_tts_job(session_id, part)
        return get_part(load_session(session_id), part)

    job_id = _mark_text_generating(session_id, part, is_retry=force)
    if not job_id:
        session = load_session(session_id)
        return get_part(session, part) if session else None
    _spawn(run_generation_job, session_id, part, job_id)
    session = load_session(session_id)
    return get_part(session, part) if session else None


def _seconds_since(iso_timestamp: str | None) -> float | None:
    from datetime import datetime, timedelta, timezone

    if not iso_timestamp:
        return None
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=9)))
        return (datetime.now(timezone(timedelta(hours=9))) - dt).total_seconds()
    except ValueError:
        return None


def recover_stuck_generation(session_id: str, part: str, part_data: dict) -> dict:
    """テキスト生成が60秒停滞したら1回リトライ、だめなら error。TTSも同様。"""

    if part_data.get("generation_status") == "generating":
        elapsed = _seconds_since(part_data.get("generation_started_at"))
        if elapsed is not None and elapsed >= GENERATION_STUCK_SEC:
            if not part_data.get("generation_retry_at"):
                start_generation_job(session_id, part, force=True)
            else:
                with get_session_lock(session_id):
                    session = load_session(session_id)
                    current = get_part(session, part) if session else None
                    if current and current.get("generation_status") == "generating":
                        still = _seconds_since(current.get("generation_started_at")) or 0
                        if still >= GENERATION_STUCK_SEC:
                            current["generation_status"] = "error"
                            current["generation_error"] = (
                                "相手の準備が完了しませんでした。再試行してください。"
                            )
                            save_session(session)
                session = load_session(session_id)
                part_data = get_part(session, part) if session else part_data

    if part_data and part_data.get("tts_status") == "generating":
        elapsed = _seconds_since(part_data.get("tts_started_at"))
        if elapsed is not None and elapsed >= TTS_STUCK_SEC:
            if not part_data.get("tts_retry_at"):
                start_tts_job(session_id, part, force=True)
            else:
                with get_session_lock(session_id):
                    session = load_session(session_id)
                    current = get_part(session, part) if session else None
                    if current and current.get("tts_status") == "generating":
                        still = _seconds_since(current.get("tts_started_at")) or 0
                        if still >= TTS_STUCK_SEC:
                            current["tts_status"] = "error"
                            current["tts_error"] = "音声の準備が完了しませんでした。再試行してください。"
                            save_session(session)
                session = load_session(session_id)
                part_data = get_part(session, part) if session else part_data

    return part_data
