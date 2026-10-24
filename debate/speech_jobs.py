"""観戦用スクリプトの音声生成ジョブ（script_jobs.py と同じ起動方式）。"""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from debate.config import PART_ORDER, WATCH_SPEECH_STUCK_SEC
from debate.models import JST, now_iso
from debate.script_storage import (
    get_script_lock,
    list_scripts,
    load_script,
    part_audio_ready,
    save_script,
    write_part_audio,
)
from debate.speech import synthesize_watch_speech

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

                _pool = ThreadPool(2)
                _use_gevent = True
                logger.info("debate watch speech: using gevent.threadpool.ThreadPool")
                return _pool
            except Exception as exc:  # noqa: BLE001
                logger.warning("debate watch speech: gevent threadpool unavailable (%s)", exc)
        from concurrent.futures import ThreadPoolExecutor

        _pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="debate-watch-speech")
        _use_gevent = False
        logger.info("debate watch speech: using ThreadPoolExecutor")
        return _pool


def _spawn(func, *args) -> None:
    pool = _get_pool()
    if _use_gevent:
        try:
            pool.spawn(func, *args)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("debate watch speech: gevent spawn failed (%s); using thread", exc)
    if hasattr(pool, "submit"):
        pool.submit(func, *args)
        return
    thread = threading.Thread(target=func, args=args, daemon=True, name="debate-watch-speech")
    thread.start()


def _audio(part: dict) -> dict:
    audio = part.get("audio") if isinstance(part.get("audio"), dict) else {}
    return dict(audio)


def _needs_speech(script_id: str, part: dict) -> bool:
    audio = _audio(part)
    if str(audio.get("status") or "") == "generating":
        return False
    if not str(part.get("text") or "").strip():
        return True
    return not part_audio_ready(script_id, part)


def _speech_targets(script_id: str, only_parts: list[str] | None, force: bool) -> list[str]:
    wanted = None
    if only_parts is not None:
        wanted = []
        for name in only_parts:
            if name not in PART_ORDER:
                raise ValueError("不明なパートです。")
            if name not in wanted:
                wanted.append(name)
    names: list[str] = []
    script = load_script(script_id)
    if not script:
        raise ValueError("スクリプトが見つかりません。")
    if script.get("generation_status") != "draft" or not script.get("parts"):
        raise ValueError("生成が終わった本文があるスクリプトだけ音声を作れます。")
    for part in script.get("parts") or []:
        if not isinstance(part, dict):
            continue
        name = str(part.get("part") or "")
        if name not in PART_ORDER:
            continue
        if wanted is not None and name not in wanted:
            continue
        audio = _audio(part)
        if str(audio.get("status") or "") == "generating":
            continue
        if wanted is None and not _needs_speech(script_id, part):
            continue
        if wanted is not None and not force and not _needs_speech(script_id, part):
            continue
        names.append(name)
    return names


def queue_script_speech(script_id: str, only_parts: list[str] | None = None, *, force: bool = False) -> dict:
    """必要なパートを generating にしてジョブを起動する。force はそのパートを作り直す。"""
    planned = _speech_targets(script_id, only_parts, force)
    if planned:
        from debate.paid_limits import consume

        consume("tts", len(planned))
    wanted = None
    if only_parts is not None:
        wanted = []
        for name in only_parts:
            if name not in PART_ORDER:
                raise ValueError("不明なパートです。")
            if name not in wanted:
                wanted.append(name)
    queued: list[tuple[str, str]] = []
    with get_script_lock(script_id):
        script = load_script(script_id)
        if not script:
            raise ValueError("スクリプトが見つかりません。")
        if script.get("generation_status") != "draft" or not script.get("parts"):
            raise ValueError("生成が終わった本文があるスクリプトだけ音声を作れます。")
        for part in script.get("parts") or []:
            if not isinstance(part, dict):
                continue
            name = str(part.get("part") or "")
            if name not in PART_ORDER:
                continue
            if wanted is not None and name not in wanted:
                continue
            audio = _audio(part)
            if str(audio.get("status") or "") == "generating":
                continue
            if wanted is None and not _needs_speech(script_id, part):
                continue
            if wanted is not None and not force and not _needs_speech(script_id, part):
                continue
            pending_hash = str(part.get("text_hash") or "")
            part["audio"] = {
                "status": "generating",
                "text_hash": str(audio.get("text_hash") or ""),
                "pending_hash": pending_hash,
                "error": "",
                "started_at": now_iso(),
            }
            queued.append((name, pending_hash))
        save_script(script)
    if queued:
        _spawn(run_speech_job, script_id, queued)
    loaded = load_script(script_id)
    return loaded or script


def run_speech_job(script_id: str, queued: list[tuple[str, str]]) -> None:
    for part_name, pending_hash in queued:
        _run_one(script_id, part_name, pending_hash)


def _run_one(script_id: str, part_name: str, pending_hash: str) -> None:
    with get_script_lock(script_id):
        script = load_script(script_id)
        part = _find_part(script, part_name) if script else None
        if not part:
            return
        audio = _audio(part)
        if audio.get("status") != "generating" or audio.get("pending_hash") != pending_hash:
            return
        text = str(part.get("text") or "")
        side = str(part.get("side") or "")
    if not text.strip():
        _mark_error(script_id, part_name, pending_hash, "本文が空です。")
        return
    try:
        audio_bytes, cost = synthesize_watch_speech(text, side)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Watch speech failed (%s %s): %s", script_id, part_name, exc)
        _mark_error(script_id, part_name, pending_hash, str(exc) or "音声を生成できませんでした。")
        return
    with get_script_lock(script_id):
        script = load_script(script_id)
        part = _find_part(script, part_name) if script else None
        if not script or not part:
            return
        audio = _audio(part)
        if audio.get("status") != "generating" or audio.get("pending_hash") != pending_hash:
            return
        if str(part.get("text_hash") or "") != pending_hash:
            part["audio"] = {
                "status": "error",
                "text_hash": str(audio.get("text_hash") or ""),
                "error": "本文が更新されたため、もう一度生成してください。",
            }
            save_script(script)
            return
        try:
            write_part_audio(script_id, part_name, audio_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Watch speech save failed (%s %s)", script_id, part_name)
            part["audio"] = {
                "status": "error",
                "text_hash": str(audio.get("text_hash") or ""),
                "error": str(exc) or "音声ファイルを保存できませんでした。",
            }
            save_script(script)
            return
        part["audio"] = {"status": "ready", "text_hash": pending_hash, "error": ""}
        script["speech_cost_usd"] = round(float(script.get("speech_cost_usd") or 0) + float(cost or 0), 6)
        script["speech_model"] = "gpt-4o-mini-tts"
        save_script(script)


def _mark_error(script_id: str, part_name: str, pending_hash: str, message: str) -> None:
    with get_script_lock(script_id):
        script = load_script(script_id)
        part = _find_part(script, part_name) if script else None
        if not script or not part:
            return
        audio = _audio(part)
        if audio.get("status") != "generating" or audio.get("pending_hash") != pending_hash:
            return
        part["audio"] = {
            "status": "error",
            "text_hash": str(audio.get("text_hash") or ""),
            "error": message[:300],
        }
        save_script(script)


def _find_part(script: dict | None, part_name: str) -> dict | None:
    if not script:
        return None
    for part in script.get("parts") or []:
        if isinstance(part, dict) and part.get("part") == part_name:
            return part
    return None


def _seconds_since(iso_timestamp: str | None) -> float | None:
    if not iso_timestamp:
        return None
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return (datetime.now(JST) - dt).total_seconds()
    except ValueError:
        return None


def recover_stuck_speech() -> None:
    for script in list_scripts():
        script_id = str(script.get("script_id") or "")
        if not script_id:
            continue
        stuck = []
        for part in script.get("parts") or []:
            if not isinstance(part, dict):
                continue
            audio = _audio(part)
            if audio.get("status") != "generating":
                continue
            elapsed = _seconds_since(audio.get("started_at"))
            if elapsed is None or elapsed < WATCH_SPEECH_STUCK_SEC:
                continue
            stuck.append((str(part.get("part") or ""), str(audio.get("pending_hash") or "")))
        for part_name, pending_hash in stuck:
            if part_name:
                _mark_error(script_id, part_name, pending_hash, "音声の生成が途中で止まったため、もう一度実行してください。")
