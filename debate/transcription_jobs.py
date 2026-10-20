"""Whisper 文字起こしのバックグラウンド実行。

gevent ワーカー（monkey.patch 済み）では gevent.threadpool を使う。
gthread では別 OS スレッドから spawn すると InvalidThreadUseError になるため
ThreadPoolExecutor にフォールバックする。
"""
import logging
import threading
from pathlib import Path

from debate.config import TRANSCRIBE_POOL_SIZE
from debate.models import now_iso
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

                _pool = ThreadPool(TRANSCRIBE_POOL_SIZE)
                _use_gevent = True
                logger.info(
                    "debate transcription: using gevent.threadpool.ThreadPool size=%s",
                    TRANSCRIBE_POOL_SIZE,
                )
                return _pool
            except Exception as exc:  # noqa: BLE001
                logger.warning("debate transcription: gevent threadpool unavailable (%s)", exc)
        from concurrent.futures import ThreadPoolExecutor

        _pool = ThreadPoolExecutor(
            max_workers=TRANSCRIBE_POOL_SIZE, thread_name_prefix="debate-transcribe"
        )
        _use_gevent = False
        logger.info("debate transcription: using ThreadPoolExecutor")
        return _pool


def _transcript_is_blank(part_data: dict) -> bool:
    raw = str(part_data.get("transcript_raw") or "").strip()
    edited = str(part_data.get("transcript_edited") or "").strip()
    return not raw and not edited


def _browser_placeholder(part_data: dict) -> bool:
    """ブラウザ下書きのままで、生徒が文章を変えていない。"""
    if part_data.get("transcript_source") != "browser":
        return False
    browser = str(part_data.get("transcript_browser") or "").strip()
    edited = str(part_data.get("transcript_edited") or "").strip()
    raw = str(part_data.get("transcript_raw") or "").strip()
    return bool(browser) and edited == browser and not raw


def may_apply_transcription(part_data: dict | None) -> bool:
    """文字起こし結果を書いてよいか。

    transcribing 中は書く。停滞扱いで needs_review に落ちていても、
    文字起こしが空、またはブラウザ下書きのままなら遅いジョブの結果を書く。
    生徒が下書きを編集したあとは上書きしない。
    """
    if not part_data:
        return False
    status = part_data.get("status")
    if status == "transcribing":
        return True
    if status == "needs_review" and (
        _transcript_is_blank(part_data) or _browser_placeholder(part_data)
    ):
        return True
    return False


def apply_whisper_result(part_data: dict, transcript: str, error_message: str) -> None:
    """Whisper 成功時は本文を置き換える。失敗時はブラウザ下書きを残す。

    生徒がブラウザ下書きを編集済みなら transcript_edited は残し、
    transcript_force_whisper があるときだけ Whisper で置き換える。
    """
    browser = str(part_data.get("transcript_browser") or "").strip()
    edited = str(part_data.get("transcript_edited") or "").strip()
    force = bool(part_data.pop("transcript_force_whisper", None))
    user_edited = (
        not force
        and part_data.get("transcript_source") == "browser"
        and bool(edited)
        and edited != browser
    )
    text = str(transcript or "").strip()
    if error_message or not text:
        if not error_message:
            error_message = (
                "文字起こし結果が空です。「文字起こしを再試行」するか、下書きを直してください。"
            )
        part_data["transcript_error"] = error_message
        if user_edited:
            part_data["transcript_source"] = "edited"
        elif browser:
            part_data["transcript_edited"] = browser
            part_data["transcript_source"] = "browser"
        part_data["status"] = "needs_review"
        return

    part_data["transcript_raw"] = text
    part_data["transcript_error"] = ""
    if user_edited:
        part_data["transcript_source"] = "edited"
    else:
        part_data["transcript_edited"] = text
        part_data["transcript_source"] = "whisper"
    part_data["status"] = "needs_review"


def run_transcription_job(session_id: str, part: str, file_path: Path) -> None:
    """Whisper で文字起こしし、完了後にセッション JSON へ反映する。"""
    with get_session_lock(session_id):
        session = load_session(session_id)
        part_data = get_part(session, part) if session else None
        if not may_apply_transcription(part_data):
            return
        part_data["transcribe_started_at"] = now_iso()
        save_session(session)

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
        if not may_apply_transcription(part_data):
            return

        apply_whisper_result(part_data, transcript, error_message)
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
