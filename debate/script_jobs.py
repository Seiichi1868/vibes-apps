"""観戦用スクリプト生成の非同期ジョブ（judge_jobs.py と同じ起動方式）。"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime

from debate.ai_script import LEVELS, generate_model_script
from debate.models import JST, now_iso
from debate.script_storage import get_script_lock, load_script, save_script

logger = logging.getLogger(__name__)

SCRIPT_STUCK_SEC = 360

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
                logger.info("debate script: using gevent.threadpool.ThreadPool")
                return _pool
            except Exception as exc:  # noqa: BLE001
                logger.warning("debate script: gevent threadpool unavailable (%s)", exc)
        from concurrent.futures import ThreadPoolExecutor

        _pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="debate-script")
        _use_gevent = False
        logger.info("debate script: using ThreadPoolExecutor")
        return _pool


def _spawn(func, *args) -> None:
    pool = _get_pool()
    if _use_gevent:
        try:
            pool.spawn(func, *args)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("debate script: gevent spawn failed (%s); using thread", exc)
    if hasattr(pool, "submit"):
        pool.submit(func, *args)
        return
    thread = threading.Thread(target=func, args=args, daemon=True, name="debate-script")
    thread.start()


def new_script_stub(motion: str, level: str, intended_winner: str, model_mode: str) -> dict:
    return {
        "script_id": uuid.uuid4().hex[:12],
        "motion": motion.strip(),
        "level": level,
        "intended_winner": intended_winner if intended_winner in ("Gov", "Opp") else "",
        "requested_winner": intended_winner,
        "status": "draft",
        "generation_status": "generating",
        "generation_error": "",
        "warnings": [],
        "created_at": now_iso(),
        "script_model": "",
        "model_mode": model_mode,
        "gen_cost_usd": 0.0,
        "teacher_note": "",
        "summary_ja": "",
        "points": {"Gov": [], "Opp": []},
        "argument_map": [],
        "parts": [],
        "generation_started_at": now_iso(),
    }


def start_script_job(motion: str, level: str, intended_winner: str, model_mode: str) -> dict:
    if level not in LEVELS:
        raise ValueError("レベルは easy / normal / hard から選んでください。")
    if intended_winner not in ("Gov", "Opp", "auto"):
        raise ValueError("優勢側は Gov / Opp / おまかせ から選んでください。")
    stub = new_script_stub(motion, level, intended_winner, model_mode)
    save_script(stub)
    _spawn(run_script_job, stub["script_id"])
    return stub


def run_script_job(script_id: str) -> None:
    with get_script_lock(script_id):
        script = load_script(script_id)
    if not script or script.get("generation_status") != "generating":
        return
    started = time.monotonic()
    try:
        generated = generate_model_script(
            script.get("motion") or "",
            script.get("level") or "normal",
            script.get("requested_winner") or "auto",
            script.get("model_mode") or "5.6-terra",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Script job failed (%s): %s", script_id, exc)
        _save_error(
            script_id,
            str(exc) or "スクリプトを生成できませんでした。",
            seconds=round(time.monotonic() - started, 1),
        )
        return
    generated = dict(generated)
    generated["generation_seconds"] = round(time.monotonic() - started, 1)
    _save_success(script_id, generated)


def _save_success(script_id: str, generated: dict) -> None:
    with get_script_lock(script_id):
        script = load_script(script_id)
        if not script or script.get("generation_status") != "generating":
            return
        script.update(
            {
                "intended_winner": generated.get("intended_winner") or "",
                "points": generated.get("points") or {"Gov": [], "Opp": []},
                "argument_map": generated.get("argument_map") or [],
                "parts": generated.get("parts") or [],
                "summary_ja": generated.get("summary_ja") or "",
                "warnings": generated.get("warnings") or [],
                "script_model": generated.get("script_model") or "",
                "gen_cost_usd": generated.get("gen_cost_usd") or 0,
                "generation_seconds": generated.get("generation_seconds"),
                "generation_status": "draft",
                "generation_error": "",
                "status": "draft",
            }
        )
        save_script(script)


def _save_error(script_id: str, message: str, seconds: float | None = None) -> None:
    with get_script_lock(script_id):
        script = load_script(script_id)
        if not script:
            return
        script["generation_status"] = "error"
        script["generation_error"] = message[:500]
        script["status"] = "draft"
        if seconds is not None:
            script["generation_seconds"] = seconds
        save_script(script)


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


def recover_stuck_scripts() -> None:
    for script in load_script_ids():
        if script.get("generation_status") != "generating":
            continue
        elapsed = _seconds_since(script.get("generation_started_at"))
        if elapsed is None or elapsed < SCRIPT_STUCK_SEC:
            continue
        _save_error(script["script_id"], "生成が途中で止まったため、もう一度実行してください。")


def load_script_ids() -> list[dict]:
    from debate.script_storage import list_scripts

    return list_scripts()
