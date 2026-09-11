"""Whisper 文字起こしのバックグラウンド実行。

gevent ワーカー（monkey.patch 済み）では gevent.threadpool を使う。
gthread では別 OS スレッドから spawn すると InvalidThreadUseError になるため
ThreadPoolExecutor にフォールバックする。
"""
import logging
import threading
from pathlib import Path

from debate.storage import get_part, get_session_lock, load_session, save_session
from debate.transcription import transcribe_audio

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

                _pool = ThreadPool(4)
                _use_gevent = True
                logger.info("debate transcription: using gevent.threadpool.ThreadPool")
                return _pool
            except Exception as exc:  # noqa: BLE001
                logger.warning("debate transcription: gevent threadpool unavailable (%s)", exc)
        from concurrent.futures import ThreadPoolExecutor

        _pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="debate-transcribe")
        _use_gevent = False
        logger.info("debate transcription: using ThreadPoolExecutor")
        return _pool


def run_transcription_job(session_id: str, part: str, file_path: Path) -> None:
    """Whisper で文字起こしし、完了後にセッション JSON へ反映する。"""
    error_message = ""
    transcript = ""
    try:
        if not file_path.is_file():
            raise RuntimeError("音声ファイルが見つかりません。")
        transcript = transcribe_audio(file_path)
    except RuntimeError as exc:
        error_message = str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Whisper failed session=%s part=%s file=%s: %s",
            session_id,
            part,
            file_path.name,
            exc,
        )
        error_message = (
            f"文字起こしに失敗しました（{type(exc).__name__}）。"
            "「文字起こしを確認」から再試行するか、手動入力してください。"
        )

    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return
        part_data = get_part(session, part)
        if not part_data or part_data.get("status") != "transcribing":
            return

        if error_message:
            part_data["transcript_error"] = error_message
        else:
            part_data["transcript_raw"] = transcript
            part_data["transcript_edited"] = transcript
            part_data["transcript_error"] = ""
        part_data["status"] = "needs_review"
        save_session(session)
        logger.info(
            "Transcription finished session=%s part=%s status=needs_review error=%s",
            session_id,
            part,
            bool(error_message),
        )


def start_transcription_job(session_id: str, part: str, file_path: Path) -> None:
    """非ブロッキングで文字起こしジョブを起動する。"""
    pool = _get_pool()
    if _use_gevent:
        try:
            pool.spawn(run_transcription_job, session_id, part, file_path)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("debate transcription: gevent spawn failed (%s); using thread", exc)
    if hasattr(pool, "submit"):
        pool.submit(run_transcription_job, session_id, part, file_path)
        return
    thread = threading.Thread(
        target=run_transcription_job,
        args=(session_id, part, file_path),
        daemon=True,
        name=f"debate-transcribe-{part}",
    )
    thread.start()
