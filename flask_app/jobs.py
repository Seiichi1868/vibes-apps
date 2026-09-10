"""Speaking Lab の重い OpenAI 処理を OS スレッドで実行する。

debate / level_check の jobs.py と同じ発想。本番は gthread ワーカーのため、
gevent ハブに依存しない ThreadPoolExecutor を優先する。
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

OPENAI_TIMEOUT_SEC = 60.0
EVAL_TIMEOUT_MESSAGE = "評価がタイムアウトしました。もう一度提出してください。"

_pool = None
_pool_lock = threading.Lock()
_use_gevent = False


def _get_pool():
    global _pool, _use_gevent
    with _pool_lock:
        if _pool is not None:
            return _pool
        patched = False
        try:
            from gevent import monkey

            patched = bool(monkey.is_module_patched("socket"))
        except Exception:
            patched = False
        if patched:
            try:
                from gevent.threadpool import ThreadPool

                _pool = ThreadPool(4)
                _use_gevent = True
                logger.info("speaking lab jobs: using gevent.threadpool.ThreadPool")
                return _pool
            except Exception as exc:  # noqa: BLE001
                logger.warning("speaking lab jobs: gevent threadpool unavailable (%s)", exc)
        from concurrent.futures import ThreadPoolExecutor

        _pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="speak-jobs")
        _use_gevent = False
        logger.info("speaking lab jobs: using ThreadPoolExecutor")
        return _pool


def is_timeout_error(exc: BaseException) -> bool:
    try:
        from openai import APITimeoutError
    except ImportError:
        APITimeoutError = ()
    if isinstance(exc, TimeoutError):
        return True
    if APITimeoutError and isinstance(exc, APITimeoutError):
        return True
    text = f"{type(exc).__name__} {exc}".lower()
    return "timeout" in text or "timed out" in text


def run_blocking(func: Callable[..., T], *args, **kwargs) -> T:
    """重い同期処理を OS スレッドで実行し、完了まで待つ。"""
    pool = _get_pool()
    if _use_gevent:
        return pool.spawn(func, *args, **kwargs).get()
    return pool.submit(func, *args, **kwargs).result()
