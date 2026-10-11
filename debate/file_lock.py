"""ワーカーをまたぐ排他。

gunicorn はプロセスが複数ある。threading.Lock はそのプロセスの中でしか効かない。
同じプロセスのスレッドには RLock、別プロセスには flock を使う。
flock を同じプロセスで重ねて取ると解除が壊れるので、ネストは深さで数える。
"""
from __future__ import annotations

import fcntl
import threading
from pathlib import Path

_guard = threading.Lock()
_locks: dict[str, "ProcessFileLock"] = {}


class ProcessFileLock:
    def __init__(self, path: Path):
        self._path = path
        self._thread = threading.RLock()
        self._fh = None
        self._depth = 0

    def __enter__(self):
        self._thread.acquire()
        try:
            if self._depth == 0:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._fh = self._path.open("a+")
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
            self._depth += 1
        except Exception:
            self._thread.release()
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self._depth -= 1
            if self._depth <= 0:
                self._depth = 0
                handle = self._fh
                self._fh = None
                if handle is not None:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    finally:
                        handle.close()
        finally:
            self._thread.release()
        return False


def get_named_lock(path: Path) -> ProcessFileLock:
    key = str(path)
    with _guard:
        lock = _locks.get(key)
        if lock is None:
            lock = ProcessFileLock(path)
            _locks[key] = lock
        return lock
