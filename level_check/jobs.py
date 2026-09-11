"""録音アップロード後のバックグラウンド処理（文字起こし→採点）。

gevent ワーカー（monkey.patch 済み）では gevent.threadpool を使う。
gthread では別 OS スレッドから spawn すると InvalidThreadUseError になるため
ThreadPoolExecutor にフォールバックする。
"""
import logging
import threading
from pathlib import Path

from level_check.audio_convert import normalize_audio_file
from level_check.config import CATEGORIES, LISTENING_CATEGORIES, SPEAKING_CATEGORIES, resolve_ai_model_id
from level_check.models import empty_overall, now_iso
from level_check.scoring.evaluator import evaluate_response
from level_check.scoring.rubric import (
    LISTENING_AXES,
    SPEAKING_AXES,
    band_for_score_90,
    combine_overall_score,
    score_1to5_to_90,
)
from level_check.storage import get_part, get_session_lock, load_session, load_settings, save_session, save_submission
from level_check.transcription import transcribe_audio

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
                logger.info("level_check jobs: using gevent.threadpool.ThreadPool")
                return _pool
            except Exception as exc:  # noqa: BLE001
                logger.warning("level_check jobs: gevent threadpool unavailable (%s)", exc)
        from concurrent.futures import ThreadPoolExecutor

        _pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="level-check-jobs")
        _use_gevent = False
        logger.info("level_check jobs: using ThreadPoolExecutor")
        return _pool


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _axis_averages(parts: list[dict], axes: tuple[str, ...]) -> dict:
    result = {}
    for axis in axes:
        values = []
        for part in parts:
            scores = part.get("scores") or {}
            if axis in scores and scores[axis] is not None:
                try:
                    values.append(float(scores[axis]))
                except (TypeError, ValueError):
                    pass
        avg = _average(values)
        if avg is not None:
            result[axis] = avg
    return result


def _finalize_session_if_complete(session: dict) -> None:
    parts = session.get("parts", [])
    if not parts or any(p.get("status") not in ("done", "error") for p in parts):
        return

    settings = load_settings()
    scored_parts = [p for p in parts if p.get("weighted_total") is not None]

    speaking_parts = [p for p in scored_parts if p.get("score_track") == "speaking" or p.get("task_type") in SPEAKING_CATEGORIES]
    listening_parts = [
        p for p in scored_parts if p.get("score_track") == "listening" or p.get("task_type") in LISTENING_CATEGORIES
    ]

    speaking_avg = _average([p["weighted_total"] for p in speaking_parts])
    listening_avg = _average([p["weighted_total"] for p in listening_parts])
    speaking_90 = score_1to5_to_90(speaking_avg)
    listening_90 = score_1to5_to_90(listening_avg)
    overall_90 = combine_overall_score(speaking_90, listening_90, settings.get("overall_weights"))

    category_scores = {}
    for cat in CATEGORIES:
        values = [p["weighted_total"] for p in scored_parts if p.get("task_type") == cat]
        avg = _average(values)
        if avg is not None:
            # 表示は小数第1位まで
            category_scores[cat] = round(avg, 1)

    overall = empty_overall()
    overall.update(
        {
            "speaking_level_score": overall_90,
            "cefr_band": band_for_score_90(overall_90),
            "speaking_subscore": speaking_90,
            "listening_subscore": listening_90,
            "speaking_axes": _axis_averages(speaking_parts, SPEAKING_AXES),
            "listening_axes": _axis_averages(listening_parts, LISTENING_AXES),
            "category_scores": category_scores,
        }
    )
    session["overall"] = overall
    session["status"] = "done"
    save_session(session)

    save_submission(
        {
            "session_id": session["session_id"],
            "info_level": session.get("info_level"),
            "student_info": session.get("student_info"),
            "ai_model_mode": session.get("ai_model_mode"),
            "overall": session["overall"],
            "task_results": [
                {
                    "task_type": p.get("task_type"),
                    "category": p.get("category") or p.get("task_type"),
                    "score_track": p.get("score_track"),
                    "question_id": p.get("question_id"),
                    "question_text": p.get("question_text"),
                    "prompt_text": p.get("prompt_text"),
                    "stimulus_text": p.get("stimulus_text"),
                    "target_text": p.get("target_text"),
                    "expected_answer": p.get("expected_answer"),
                    "transcript": p.get("transcript"),
                    "response_latency_ms": p.get("response_latency_ms"),
                    "scores": p.get("scores"),
                    "comments": p.get("comments"),
                    "weighted_total": p.get("weighted_total"),
                    "score_90": p.get("score_90"),
                    "cefr_band": p.get("cefr_band"),
                    "status": p.get("status"),
                    "transcript_error": p.get("transcript_error"),
                }
                for p in parts
            ],
        }
    )


def run_process_part_job(session_id: str, part_id: str, file_path: Path) -> None:
    error_message = ""
    transcript = ""
    eval_result = None

    try:
        if not file_path.is_file():
            raise RuntimeError("音声ファイルが見つかりません。")
        normalized_path = normalize_audio_file(file_path)
        transcript = transcribe_audio(normalized_path)
        if not transcript.strip():
            raise RuntimeError("文字起こし結果が空でした。発話が録音できているかご確認ください。")
    except RuntimeError as exc:
        error_message = str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Transcription failed session=%s part=%s: %s", session_id, part_id, exc)
        error_message = f"文字起こしに失敗しました（{type(exc).__name__}）。もう一度録音してください。"

    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return
        part = get_part(session, part_id)
        if not part or part.get("status") != "transcribing":
            return

        if error_message:
            part["transcript_error"] = error_message
            part["status"] = "error"
            save_session(session)
            _finalize_session_if_complete(session)
            return

        part["transcript"] = transcript
        part["status"] = "scoring"
        save_session(session)

    settings = load_settings()
    model_mode = session.get("ai_model_mode") or settings.get("ai_model_mode")
    try:
        from level_check.config import get_openai_api_key

        eval_result = evaluate_response(
            task_type=part["task_type"],
            question_text=part.get("question_text", ""),
            target_text=part.get("target_text", ""),
            stimulus_text=part.get("stimulus_text", ""),
            expected_answer=part.get("expected_answer", ""),
            transcript=transcript,
            response_latency_ms=part.get("response_latency_ms"),
            model=resolve_ai_model_id(model_mode),
            api_key=get_openai_api_key(),
            score_track=part.get("score_track"),
            speaking_weights=settings.get("speaking_rubric_weights"),
            listening_weights=settings.get("listening_rubric_weights"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scoring failed session=%s part=%s: %s", session_id, part_id, exc)
        error_message = f"採点に失敗しました（{type(exc).__name__}）。"

    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return
        part = get_part(session, part_id)
        if not part or part.get("status") != "scoring":
            return

        if error_message:
            part["transcript_error"] = error_message
            part["status"] = "error"
        else:
            part["scores"] = eval_result["scores"]
            part["comments"] = eval_result["comments"]
            part["weighted_total"] = eval_result["weighted_total"]
            part["score_90"] = eval_result.get("score_90")
            part["cefr_band"] = eval_result["cefr_band"]
            part["score_track"] = eval_result.get("score_track") or part.get("score_track")
            part["status"] = "done"
        part["end_time"] = part.get("end_time") or now_iso()
        save_session(session)
        logger.info(
            "level_check part finished session=%s part=%s status=%s",
            session_id,
            part_id,
            part["status"],
        )
        _finalize_session_if_complete(session)


def start_process_part_job(session_id: str, part_id: str, file_path: Path) -> None:
    pool = _get_pool()
    if _use_gevent:
        try:
            pool.spawn(run_process_part_job, session_id, part_id, file_path)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("level_check jobs: gevent spawn failed (%s); using thread", exc)
    if hasattr(pool, "submit"):
        pool.submit(run_process_part_job, session_id, part_id, file_path)
        return
    thread = threading.Thread(
        target=run_process_part_job,
        args=(session_id, part_id, file_path),
        daemon=True,
        name=f"level-check-process-{part_id}",
    )
    thread.start()
