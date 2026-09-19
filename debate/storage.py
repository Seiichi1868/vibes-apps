"""セッションデータの永続化（JSONファイル、data/debate/sessions/<session_id>.json）。

ブラウザのリロードや通信断でもデータが失われないよう、各操作の完了時点で
逐次ディスクへ保存する（仕様書「エラーハンドリング」節に対応）。
"""
import json
import shutil
import threading
import uuid
from copy import deepcopy
from pathlib import Path

from debate.config import AUDIO_DIR, SESSIONS_DIR, ensure_dirs

_lock = threading.Lock()
MAX_ADMIN_NOTES_LEN = 200

# パートごとの非同期文字起こし（バックグラウンドスレッド）と、通常のリクエスト処理
# （録音開始・確定・リセット等）が同じセッションJSONを並行して読み書きしても
# 更新内容を失わないよう、セッションIDごとに排他ロックを提供する。
_session_locks: dict[str, threading.Lock] = {}
_session_locks_guard = threading.Lock()


def _safe_id(session_id: str) -> str:
    return "".join(c for c in session_id if c.isalnum() or c == "-")


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{_safe_id(session_id)}.json"


def get_session_lock(session_id: str) -> threading.Lock:
    """「読み込み→一部更新→書き込み」を一連の操作として直列化するためのロック。"""
    safe_id = _safe_id(session_id)
    with _session_locks_guard:
        lock = _session_locks.get(safe_id)
        if lock is None:
            lock = threading.Lock()
            _session_locks[safe_id] = lock
        return lock


def save_session(session: dict) -> dict:
    from debate.models import now_iso

    session["updated_at"] = now_iso()
    ensure_dirs()
    path = _session_path(session["session_id"])
    with _lock:
        tmp_path = path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(session, handle, ensure_ascii=False, indent=2)
        tmp_path.replace(path)
    return session


def load_session(session_id: str) -> dict | None:
    ensure_dirs()
    path = _session_path(session_id)
    if not path.is_file():
        return None
    with _lock:
        try:
            with path.open(encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return None


def get_part(session: dict, part: str) -> dict | None:
    for part_data in session.get("parts", []):
        if part_data.get("part") == part:
            return part_data
    return None


def delete_session(session_id: str) -> bool:
    """セッションのJSONと音声ファイル一式を削除する（管理画面からの削除用）。"""
    ensure_dirs()
    safe_id = _safe_id(session_id)
    path = SESSIONS_DIR / f"{safe_id}.json"
    with _lock:
        existed = path.is_file()
        path.unlink(missing_ok=True)
    shutil.rmtree(AUDIO_DIR / safe_id, ignore_errors=True)
    return existed


def _normalize_admin_notes(notes: str) -> str:
    return str(notes or "").strip()[:MAX_ADMIN_NOTES_LEN]


def summarize_transcription_mode(session: dict) -> str:
    """各パートの transcription_mode が一致していれば batch/realtime、混在なら mixed。"""
    modes = {
        part_data.get("transcription_mode")
        for part_data in session.get("parts", [])
        if part_data.get("transcription_mode")
    }
    if len(modes) == 1:
        return str(next(iter(modes)))
    if len(modes) > 1:
        return "mixed"
    return ""


def _rewrite_audio_urls(session: dict, old_id: str, new_id: str) -> None:
    old_token = _safe_id(old_id)
    new_token = _safe_id(new_id)
    for part in session.get("parts", []):
        audio_url = str(part.get("audio_url") or "")
        if not audio_url:
            continue
        if old_id in audio_url:
            part["audio_url"] = audio_url.replace(old_id, new_id)
        elif old_token in audio_url:
            part["audio_url"] = audio_url.replace(old_token, new_token)


def copy_session(session_id: str, notes: str = "") -> dict | None:
    """セッションJSONと音声ファイルを複製する（ジャッジ結果はリセット）。"""
    original = load_session(session_id)
    if not original:
        return None

    from debate.models import new_judge_result, now_iso

    new_id = str(uuid.uuid4())
    copied = deepcopy(original)
    copied["session_id"] = new_id
    copied["created_at"] = now_iso()
    copied["updated_at"] = now_iso()
    copied["copied_from_session_id"] = session_id
    copied["admin_notes"] = _normalize_admin_notes(notes) or f"コピー（元: {session_id[:8]}）"
    copied["judge_result"] = new_judge_result()

    old_safe = _safe_id(session_id)
    new_safe = _safe_id(new_id)
    old_dir = AUDIO_DIR / old_safe
    new_dir = AUDIO_DIR / new_safe
    if old_dir.is_dir():
        shutil.copytree(old_dir, new_dir, dirs_exist_ok=True)

    _rewrite_audio_urls(copied, session_id, new_id)
    return save_session(copied)


def update_session_notes(session_id: str, notes: str) -> dict | None:
    """管理画面用: セッション備考を更新する。"""
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return None
        session["admin_notes"] = _normalize_admin_notes(notes)
        return save_session(session)


def session_summary(data: dict, *, mtime: float | None = None, include_notes: bool = False) -> dict:
    """セッション1件の一覧用サマリー。"""
    parts = data.get("parts", [])
    confirmed = sum(1 for part in parts if part.get("status") == "confirmed")
    in_progress = sum(
        1
        for part in parts
        if part.get("status") in ("recording", "transcribing", "needs_review")
    )
    updated_at = data.get("updated_at") or data.get("created_at") or ""
    if not updated_at and mtime:
        from datetime import datetime, timedelta, timezone

        jst = timezone(timedelta(hours=9))
        updated_at = datetime.fromtimestamp(mtime, tz=jst).isoformat(timespec="seconds")

    judge_result = data.get("judge_result") or {}
    judge_model_info = judge_result.get("judge_model") or {}
    judge_model_label = ""
    if isinstance(judge_model_info, dict):
        judge_model_label = judge_model_info.get("model") or ""
    if not judge_model_label:
        judge_model_label = judge_result.get("model", "")
    summary = {
        "session_id": data.get("session_id"),
        "motion": data.get("motion"),
        "created_at": data.get("created_at"),
        "updated_at": updated_at,
        "confirmed_parts": confirmed,
        "in_progress_parts": in_progress,
        "total_parts": len(parts),
        "judge_status": judge_result.get("status", "idle"),
        "judge_winner": judge_result.get("winner"),
        "judge_model": judge_model_label,
        "judge_transcription_mode": judge_result.get("transcription_mode", ""),
        "transcription_mode": summarize_transcription_mode(data),
    }
    if include_notes:
        summary["admin_notes"] = str(data.get("admin_notes") or "")
        summary["copied_from_session_id"] = str(data.get("copied_from_session_id") or "")
    return summary


def lookup_sessions(session_ids: list[str], *, limit: int = 20) -> list[dict]:
    """指定IDのうち存在するセッションだけを、渡された順で返す（生徒端末の再開一覧用）。"""
    summaries = []
    seen: set[str] = set()
    for raw_id in session_ids:
        safe_id = _safe_id(str(raw_id or ""))
        if not safe_id or safe_id in seen:
            continue
        seen.add(safe_id)
        data = load_session(safe_id)
        if not data:
            continue
        summaries.append(session_summary(data))
        if len(summaries) >= limit:
            break
    return summaries


def list_sessions(limit: int = 10, *, include_notes: bool = False) -> list[dict]:
    """保存済みセッション一覧（管理画面用）。"""
    ensure_dirs()
    files = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    summaries = []
    for path in files[:limit]:
        try:
            mtime = path.stat().st_mtime
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError):
            continue
        summaries.append(session_summary(data, mtime=mtime, include_notes=include_notes))
    return summaries
