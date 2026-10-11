"""観戦スクリプトのジャッジ照合。状態は <script_id>.checks.json。セッションには書かない。"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from debate.models import now_iso
from debate.script_checks import compare_design_and_judge, estimate_check_cost, parse_check_request
from debate.script_storage import get_script_lock, load_checks, load_script, save_checks

logger = logging.getLogger(__name__)

CHECK_STUCK_SEC = 20 * 60

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
                logger.info("debate script check: using gevent.threadpool.ThreadPool")
                return _pool
            except Exception as exc:  # noqa: BLE001
                logger.warning("debate script check: gevent threadpool unavailable (%s)", exc)
        _pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="debate-check")
        _use_gevent = False
        logger.info("debate script check: using ThreadPoolExecutor")
        return _pool


def _spawn(func, *args) -> None:
    pool = _get_pool()
    if _use_gevent:
        try:
            pool.spawn(func, *args)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("debate script check: gevent spawn failed (%s); using thread", exc)
    if hasattr(pool, "submit"):
        pool.submit(func, *args)
        return
    thread = threading.Thread(target=func, args=args, daemon=True, name="debate-check")
    thread.start()


def _blank(script_id: str) -> dict:
    return {
        "script_id": script_id,
        "status": "idle",
        "results": [],
        "total_cost_usd": 0.0,
        "error": "",
        "started_at": "",
        "finished_at": "",
    }


def checks_view(script_id: str) -> dict:
    from debate.script_checks import CHECK_NOTE, summarize_results

    _recover_stuck(script_id)
    checks = load_checks(script_id) or _blank(script_id)
    results = checks.get("results") or []
    return {
        "script_id": script_id,
        "status": checks.get("status") or "idle",
        "error": checks.get("error") or "",
        "results": results,
        "summaries": summarize_results(results),
        "total_cost_usd": checks.get("total_cost_usd") or 0,
        "estimate": checks.get("estimate"),
        "started_at": checks.get("started_at") or "",
        "finished_at": checks.get("finished_at") or "",
        "note": CHECK_NOTE,
    }


def _recover_stuck(script_id: str) -> None:
    from debate.models import JST
    from datetime import datetime

    with get_script_lock(script_id):
        checks = load_checks(script_id)
        if not checks or checks.get("status") != "running":
            return
        started = str(checks.get("started_at") or "")
        try:
            dt = datetime.fromisoformat(started)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=JST)
            elapsed = (datetime.now(JST) - dt).total_seconds()
        except ValueError:
            elapsed = CHECK_STUCK_SEC
        if elapsed < CHECK_STUCK_SEC:
            return
        checks["status"] = "error"
        checks["error"] = "照合が途中で止まったため、もう一度実行してください。"
        checks["finished_at"] = now_iso()
        save_checks(script_id, checks)


def start_check_job(script_id: str, payload: dict) -> dict:
    modes, runs = parse_check_request(payload)
    with get_script_lock(script_id):
        script = load_script(script_id)
        if not script:
            raise ValueError("スクリプトが見つかりません。")
        if script.get("generation_status") != "draft" or not script.get("parts"):
            raise ValueError("生成が終わった本文があるスクリプトだけ照合できます。")
        checks = load_checks(script_id) or _blank(script_id)
        if checks.get("status") == "running":
            raise ValueError("照合を実行中です。終わるまで待ってください。")
        estimate = estimate_check_cost(script, modes, runs)
        plan = [{"model_mode": mode, "run": index + 1} for mode in modes for index in range(runs)]
        checks.update(
            {
                "status": "running",
                "error": "",
                "results": [],
                "started_at": now_iso(),
                "finished_at": "",
                "models": modes,
                "runs_per_model": runs,
                "estimate": estimate,
                "plan_calls": len(plan),
            }
        )
        save_checks(script_id, checks)
    _spawn(run_check_job, script_id, plan)
    return checks_view(script_id)


def run_check_job(script_id: str, plan: list[dict]) -> None:
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(_run_one, script_id, item) for item in plan]
            for future in as_completed(futures):
                future.result()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Script check failed (%s)", script_id)
        with get_script_lock(script_id):
            checks = load_checks(script_id) or _blank(script_id)
            checks["status"] = "error"
            checks["error"] = str(exc) or "照合に失敗しました。"
            checks["finished_at"] = now_iso()
            save_checks(script_id, checks)
        return
    with get_script_lock(script_id):
        checks = load_checks(script_id) or _blank(script_id)
        if checks.get("status") != "running":
            return
        checks["status"] = "done"
        checks["finished_at"] = now_iso()
        save_checks(script_id, checks)


def _run_one(script_id: str, item: dict) -> None:
    from debate.judge import build_script_check_session, run_judge

    mode = item["model_mode"]
    run_index = item["run"]
    with get_script_lock(script_id):
        script = load_script(script_id)
    if not script:
        _append_result(script_id, _error_row(mode, run_index, "スクリプトが見つかりません。"))
        return
    session = build_script_check_session(script)
    try:
        judged = run_judge(session, model_mode=mode, include_usage=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Script check call failed (%s %s #%s): %s", script_id, mode, run_index, exc)
        _append_result(script_id, _error_row(mode, run_index, str(exc) or "ジャッジに失敗しました。"))
        return
    usage = judged.get("usage") if isinstance(judged.get("usage"), dict) else {}
    compared = compare_design_and_judge(script, judged)
    row = {
        "status": "done",
        "model_mode": mode,
        "model": judged.get("model") or mode,
        "run": run_index,
        "seconds": usage.get("seconds") or 0,
        "prompt_tokens": usage.get("prompt_tokens") or 0,
        "completion_tokens": usage.get("completion_tokens") or 0,
        "cost_usd": usage.get("cost_usd") or 0,
        "error": "",
        **compared,
    }
    _append_result(script_id, row)


def _error_row(mode: str, run_index: int, message: str) -> dict:
    from debate.judge_model_pricing import JUDGE_MODEL_PRICING

    meta = JUDGE_MODEL_PRICING.get(mode) or {}
    return {
        "status": "error",
        "model_mode": mode,
        "model": meta.get("model") or mode,
        "run": run_index,
        "winner": "",
        "gov": None,
        "opp": None,
        "winner_match": False,
        "point_count_mismatch": False,
        "status_match": None,
        "status_ratio": None,
        "status_key": "",
        "points": [],
        "seconds": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cost_usd": 0,
        "error": message[:300],
    }


def _append_result(script_id: str, row: dict) -> None:
    with get_script_lock(script_id):
        checks = load_checks(script_id) or _blank(script_id)
        results = list(checks.get("results") or [])
        results.append(row)
        results.sort(key=lambda item: (str(item.get("model_mode") or ""), int(item.get("run") or 0)))
        checks["results"] = results
        checks["total_cost_usd"] = round(
            float(checks.get("total_cost_usd") or 0) + float(row.get("cost_usd") or 0),
            6,
        )
        save_checks(script_id, checks)
