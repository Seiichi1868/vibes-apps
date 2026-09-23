"""Debate app Blueprint。

画面構成（PDA_debate_app_spec.md 「4. Cursorへの初回プロンプト」準拠）:
  1. GET  /debate                                          … ①論題入力画面
  2. GET  /debate/session/<id>                              … ②パート進行画面（録音+タイマー+ガイド文）
  3. GET  /debate/session/<id>/parts/<part>/review          … ③文字起こし確認画面
  4. GET  /debate/session/<id>/judge                        … ④ジャッジ結果画面
"""
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for
from werkzeug.utils import secure_filename

from debate.config import (
    AI_TEXT_VISIBLE_DEFAULT,
    ALLOWED_AUDIO_EXTENSIONS,
    AUDIO_DIR,
    DEFAULT_MOTIONS,
    JUDGE_STUCK_SEC,
    MAX_AUDIO_BYTES,
    PART_GUIDES,
    PART_LABELS,
    PART_ORDER,
    PART_ROLES,
    STATUS_LABELS,
    ensure_dirs,
)
from debate.judge_jobs import start_judge_job
from debate.models import new_judge_result, new_session, now_iso
from debate.settings import load_settings, resolve_background
from debate.solo import (
    CONFLICT,
    generation_guard,
    generation_view,
    initial_generation_part,
    next_generation_targets,
    normalize_difficulty,
    normalize_user_side,
    part_is_ai,
    recording_guard,
    session_mode,
)
from debate.storage import get_part, get_session_lock, load_session, lookup_sessions, save_session, summarize_transcription_mode
from debate.transcription_jobs import start_transcription_job
from debate.tts import tts_path

logger = logging.getLogger(__name__)

debate_bp = Blueprint("debate", __name__, url_prefix="/debate")

JST = timezone(timedelta(hours=9))

# 文字起こしがこの秒数を超えて "transcribing" のままなら、サーバー側で復旧する
TRANSCRIBE_STUCK_SEC = int(os.environ.get("DEBATE_TRANSCRIBE_STUCK_SEC", "90"))


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


def _resolve_elapsed_sec(part_data: dict, requested, end_time: datetime) -> int | None:
    """一時停止を除いた発話時間を優先し、なければ開始〜終了の実時間を使う。"""
    try:
        if requested is not None and str(requested).strip() != "":
            value = int(round(float(requested)))
            limit = int(part_data.get("time_limit_sec") or 210)
            if 0 <= value <= max(limit * 3, 1800):
                return value
    except (TypeError, ValueError):
        pass
    if part_data.get("start_time"):
        try:
            start_dt = datetime.fromisoformat(part_data["start_time"])
            return max(0, round((end_time - start_dt).total_seconds()))
        except ValueError:
            return None
    return None


def _audio_path(session_id: str, audio_url: str) -> Path | None:
    if not audio_url:
        return None
    path = AUDIO_DIR / session_id / Path(audio_url).name
    return path if path.is_file() else None


def _recover_stuck_transcription(session_id: str, part: str, part_data: dict) -> dict:
    """transcribing が長時間止まっているパートを needs_review に落とす（1回だけ再試行）。"""
    elapsed = _seconds_since(part_data.get("end_time"))
    if elapsed is None or elapsed < TRANSCRIBE_STUCK_SEC:
        return part_data

    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return part_data
        current = get_part(session, part)
        if not current or current.get("status") != "transcribing":
            return current or part_data

        retry_at = current.get("transcribe_retry_at")
        file_path = _audio_path(session_id, current.get("audio_url", ""))
        if not retry_at and file_path:
            current["transcribe_retry_at"] = now_iso()
            save_session(session)
            start_transcription_job(session_id, part, file_path)
            logger.warning(
                "Re-queued stuck transcription session=%s part=%s elapsed=%.0fs",
                session_id,
                part,
                elapsed,
            )
            return current

        current["status"] = "needs_review"
        current["transcript_error"] = (
            "文字起こしが完了しませんでした。「文字起こしを確認」から再試行するか、手動で入力してください。"
        )
        save_session(session)
        logger.warning(
            "Recovered stuck transcription session=%s part=%s elapsed=%.0fs",
            session_id,
            part,
            elapsed,
        )
        return current


def _background_context() -> dict:
    settings = load_settings()
    background = resolve_background(settings.get("background_id"))
    return {
        "background": background,
        "background_opacity": settings.get("background_opacity"),
        "transcription_mode": settings.get("transcription_mode", "batch"),
    }


def _part_meta() -> dict:
    return {
        part: {
            "label": PART_LABELS[part],
            "role": PART_ROLES[part],
            "guide": PART_GUIDES[part],
        }
        for part in PART_ORDER
    }


def _transcription_mode_summary(session: dict) -> str:
    return summarize_transcription_mode(session)


def _resolve_extension(filename: str, mimetype: str | None) -> str:
    safe_name = secure_filename(filename or "")
    if "." in safe_name:
        return safe_name.rsplit(".", 1)[-1].lower()
    guessed = mimetypes.guess_extension(mimetype or "") or ""
    return guessed.lstrip(".").lower() or "webm"


# ── ①論題入力画面 ─────────────────────────────────────────────
@debate_bp.route("/manifest.json")
def web_app_manifest():
    """生徒画面用 PWA manifest（scope: /debate/）。"""
    response = send_from_directory(
        Path(current_app.static_folder) / "debate",
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@debate_bp.route("/")
def index():
    ensure_dirs()
    return render_template(
        "debate/index.html",
        default_motions=DEFAULT_MOTIONS,
        **_background_context(),
    )


@debate_bp.route("/api/sessions", methods=["POST"])
def create_session():
    payload = request.get_json(silent=True) or {}
    motion = str(payload.get("motion") or "").strip()
    speaker_name = str(payload.get("speaker_name") or "").strip()
    mode = session_mode({"mode": payload.get("mode")})

    if not motion:
        return jsonify({"error": "論題（motion）を入力してください。"}), 400
    if len(motion) > 500:
        return jsonify({"error": "論題は500文字以内で入力してください。"}), 400

    user_side = None
    ai_difficulty = None
    if mode == "solo":
        user_side = normalize_user_side(payload.get("user_side"), allow_random=True)
        if not user_side:
            return jsonify({"error": "陣営は Gov / Opp / ランダムから選んでください。"}), 400
        ai_difficulty = normalize_difficulty(payload.get("ai_difficulty"))

    session = new_session(
        motion,
        speaker_name=speaker_name,
        mode=mode,
        user_side=user_side,
        ai_difficulty=ai_difficulty,
    )
    save_session(session)

    if mode == "solo":
        from debate.solo_jobs import start_generation_job

        first_ai = initial_generation_part(session)
        if first_ai:
            start_generation_job(session["session_id"], first_ai)

    return jsonify(session), 201


@debate_bp.route("/api/sessions/lookup", methods=["POST"])
def lookup_sessions_api():
    """この端末で保存したセッションIDだけを渡し、再開一覧用のサマリーを返す。"""
    payload = request.get_json(silent=True) or {}
    raw_ids = payload.get("session_ids") if "session_ids" in payload else payload.get("ids")
    if raw_ids is None:
        raw_ids = []
    if not isinstance(raw_ids, list):
        return jsonify({"error": "session_ids は配列で指定してください。"}), 400
    return jsonify({"sessions": lookup_sessions(raw_ids, limit=20)})


@debate_bp.route("/api/sessions/<session_id>", methods=["GET"])
def get_session_api(session_id):
    session = load_session(session_id)
    if not session:
        return jsonify({"error": "セッションが見つかりません。"}), 404
    return jsonify(session)


# ── ②パート進行画面 ────────────────────────────────────────────
@debate_bp.route("/session/<session_id>")
def progress_screen(session_id):
    session = load_session(session_id)
    if not session:
        return render_template(
            "debate/not_found.html", session_id=session_id, **_background_context()
        ), 404
    return render_template(
        "debate/progress.html",
        session=session,
        part_meta=_part_meta(),
        part_order=PART_ORDER,
        status_labels=STATUS_LABELS,
        ai_text_visible_default=AI_TEXT_VISIBLE_DEFAULT,
        **_background_context(),
    )


@debate_bp.route("/api/sessions/<session_id>/parts/<part>/start", methods=["POST"])
def start_part(session_id, part):
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"error": "セッションが見つかりません。"}), 404
        part_data = get_part(session, part)
        if not part_data:
            return jsonify({"error": f"不明なパート: {part}"}), 400
        allowed, message = recording_guard(session, part)
        if not allowed:
            return jsonify({"error": message}), CONFLICT

        part_data["start_time"] = datetime.now(JST).isoformat(timespec="seconds")
        part_data["end_time"] = None
        part_data["elapsed_sec"] = None
        part_data["status"] = "recording"
        save_session(session)
        return jsonify(part_data)


@debate_bp.route("/api/sessions/<session_id>/checkpoint", methods=["POST"])
def checkpoint_session(session_id):
    """進行状況を明示的に保存（自動保存の確認用）。"""
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"error": "セッションが見つかりません。"}), 404
        save_session(session)
        return jsonify(
            {
                "ok": True,
                "session_id": session_id,
                "updated_at": session.get("updated_at"),
                "motion": session.get("motion"),
            }
        )


@debate_bp.route("/api/sessions/<session_id>/parts/<part>/save", methods=["POST"])
def save_part_progress(session_id, part):
    """パート単位で進捗を保存（確定前でも中断・再開できるようにする）。"""
    payload = request.get_json(silent=True) or {}
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"error": "セッションが見つかりません。"}), 404
        part_data = get_part(session, part)
        if not part_data:
            return jsonify({"error": f"不明なパート: {part}"}), 400

        if part_data.get("status") in ("needs_review", "confirmed"):
            if "transcript_edited" in payload:
                part_data["transcript_edited"] = str(payload.get("transcript_edited", ""))

        save_session(session)
        return jsonify({"ok": True, "part": part_data, "updated_at": session.get("updated_at")})


@debate_bp.route("/api/sessions/<session_id>/parts/<part>/audio", methods=["POST"])
def upload_part_audio(session_id, part):
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"error": "セッションが見つかりません。"}), 404
        part_data = get_part(session, part)
        if not part_data:
            return jsonify({"error": f"不明なパート: {part}"}), 400
        allowed, message = recording_guard(session, part)
        if not allowed:
            return jsonify({"error": message}), CONFLICT
        if "audio" not in request.files:
            return jsonify({"error": "音声ファイルがありません。"}), 400

        audio_file = request.files["audio"]
        if not audio_file.filename:
            return jsonify({"error": "音声ファイルが空です。"}), 400

        ext = _resolve_extension(audio_file.filename, audio_file.mimetype)
        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            return jsonify({"error": f"対応していない音声形式です: {ext}"}), 400

        ensure_dirs()
        session_dir = AUDIO_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{part}_{uuid.uuid4().hex[:8]}.{ext}"
        file_path = session_dir / filename
        audio_file.save(file_path)

        if file_path.stat().st_size > MAX_AUDIO_BYTES:
            file_path.unlink(missing_ok=True)
            return jsonify({"error": "音声ファイルが大きすぎます（上限25MB）。"}), 400

        end_time = datetime.now(JST)
        part_data["end_time"] = end_time.isoformat(timespec="seconds")
        part_data["audio_url"] = url_for(
            "debate.serve_audio", session_id=session_id, filename=filename
        )
        part_data["transcript_raw"] = ""
        part_data["transcript_edited"] = ""
        part_data["transcript_error"] = ""
        part_data["transcribe_retry_at"] = None
        part_data["elapsed_sec"] = _resolve_elapsed_sec(
            part_data, request.form.get("elapsed_sec"), end_time
        )

        part_data["status"] = "transcribing"
        part_data["transcription_mode"] = "batch"
        save_session(session)
        response_data = dict(part_data)

    start_transcription_job(session_id, part, file_path)
    return jsonify(response_data), 202


@debate_bp.route("/api/sessions/<session_id>/parts/<part>/transcript", methods=["POST"])
def submit_part_transcript(session_id, part):
    """リアルタイム文字起こしモード: Web Speech API の結果を直接保存する。"""
    payload = request.get_json(silent=True) or {}
    transcript_raw = str(payload.get("transcript_raw") or "").strip()

    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"error": "セッションが見つかりません。"}), 404
        part_data = get_part(session, part)
        if not part_data:
            return jsonify({"error": f"不明なパート: {part}"}), 400
        allowed, message = recording_guard(session, part)
        if not allowed:
            return jsonify({"error": message}), CONFLICT

        end_time = datetime.now(JST)
        part_data["end_time"] = end_time.isoformat(timespec="seconds")
        part_data["transcript_raw"] = transcript_raw
        part_data["transcript_edited"] = transcript_raw
        part_data["transcript_error"] = (
            "" if transcript_raw else "文字起こし結果が空です。やり直すか、確認画面で手動入力してください。"
        )
        part_data["transcription_mode"] = "realtime"
        part_data["transcribe_retry_at"] = None
        part_data["elapsed_sec"] = _resolve_elapsed_sec(
            part_data, payload.get("elapsed_sec"), end_time
        )

        part_data["status"] = "needs_review"
        save_session(session)
        return jsonify(part_data)


@debate_bp.route("/api/sessions/<session_id>/parts/<part>/retranscribe", methods=["POST"])
def retranscribe_part(session_id, part):
    """録音済み音声はそのままに、文字起こしだけをやり直す（失敗時の再試行用）。"""
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"error": "セッションが見つかりません。"}), 404
        part_data = get_part(session, part)
        if not part_data:
            return jsonify({"error": f"不明なパート: {part}"}), 400
        if not part_data.get("audio_url"):
            return jsonify({"error": "音声データがないため再文字起こしできません。録音からやり直してください。"}), 400

        file_path = _audio_path(session_id, part_data["audio_url"])
        if not file_path:
            return jsonify({"error": "音声ファイルが見つかりません。録音からやり直してください。"}), 404

        part_data["status"] = "transcribing"
        part_data["transcript_error"] = ""
        part_data["transcribe_retry_at"] = None
        save_session(session)
        response_data = dict(part_data)

    start_transcription_job(session_id, part, file_path)
    return jsonify(response_data), 202


@debate_bp.route("/api/sessions/<session_id>/parts/<part>", methods=["GET"])
def get_part_api(session_id, part):
    """進行画面／確認画面からのポーリング用の軽量エンドポイント。"""
    session = load_session(session_id)
    if not session:
        return jsonify({"error": "セッションが見つかりません。"}), 404
    part_data = get_part(session, part)
    if not part_data:
        return jsonify({"error": f"不明なパート: {part}"}), 400

    if part_data.get("status") == "transcribing":
        part_data = _recover_stuck_transcription(session_id, part, part_data)

    return jsonify(part_data)


# ── ③文字起こし確認画面 ───────────────────────────────────────
@debate_bp.route("/session/<session_id>/parts/<part>/review")
def review_screen(session_id, part):
    session = load_session(session_id)
    if not session:
        return render_template(
            "debate/not_found.html", session_id=session_id, **_background_context()
        ), 404
    part_data = get_part(session, part)
    if not part_data:
        return render_template(
            "debate/not_found.html", session_id=session_id, **_background_context()
        ), 404
    if part_is_ai(part_data):
        return redirect(url_for("debate.progress_screen", session_id=session_id))
    return render_template(
        "debate/review.html",
        session=session,
        part=part_data,
        meta=_part_meta()[part],
        **_background_context(),
    )


@debate_bp.route("/api/sessions/<session_id>/parts/<part>/confirm", methods=["POST"])
def confirm_part(session_id, part):
    payload = request.get_json(silent=True) or {}
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"error": "セッションが見つかりません。"}), 404
        part_data = get_part(session, part)
        if not part_data:
            return jsonify({"error": f"不明なパート: {part}"}), 400
        if part_is_ai(part_data):
            return jsonify({"error": "相手AIのパートは確認画面から確定できません。"}), CONFLICT

        edited = str(payload.get("transcript_edited", part_data.get("transcript_edited", "")))
        part_data["transcript_edited"] = edited
        part_data["status"] = "confirmed"
        save_session(session)
        targets = next_generation_targets(session, part)
        response_data = dict(part_data)

    if targets:
        from debate.solo_jobs import start_generation_job

        for target in targets:
            start_generation_job(session_id, target)
    return jsonify(response_data)


@debate_bp.route("/api/sessions/<session_id>/parts/<part>/reset", methods=["POST"])
def reset_part(session_id, part):
    """そのパートだけ録音・やり直しができるよう、状態を初期化する。"""
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"error": "セッションが見つかりません。"}), 404
        part_data = get_part(session, part)
        if not part_data:
            return jsonify({"error": f"不明なパート: {part}"}), 400
        if part_is_ai(part_data):
            return jsonify({"error": "相手AIのパートはリセットできません。"}), CONFLICT

        part_data.update(
            {
                "audio_url": "",
                "transcript_raw": "",
                "transcript_edited": "",
                "transcript_error": "",
                "transcription_mode": "",
                "transcribe_retry_at": None,
                "start_time": None,
                "end_time": None,
                "elapsed_sec": None,
                "status": "not_started",
            }
        )
        save_session(session)
        return jsonify(part_data)


@debate_bp.route("/api/sessions/<session_id>/parts/<part>/generate", methods=["POST"])
def start_part_generation(session_id, part):
    session = load_session(session_id)
    if not session:
        return jsonify({"error": "セッションが見つかりません。"}), 404
    allowed, message = generation_guard(session, part)
    if not allowed:
        return jsonify({"error": message}), CONFLICT

    from debate.solo_jobs import start_generation_job

    part_data = start_generation_job(session_id, part)
    if not part_data:
        return jsonify({"error": "生成を開始できませんでした。"}), 400
    return jsonify(generation_view(part_data)), 202


@debate_bp.route("/api/sessions/<session_id>/parts/<part>/generation", methods=["GET"])
def get_part_generation(session_id, part):
    session = load_session(session_id)
    if not session:
        return jsonify({"error": "セッションが見つかりません。"}), 404
    part_data = get_part(session, part)
    if not part_data:
        return jsonify({"error": f"不明なパート: {part}"}), 400
    if part_is_ai(part_data):
        from debate.solo_jobs import recover_stuck_generation, start_followup_generation

        part_data = recover_stuck_generation(session_id, part, part_data)
        if part_data and part_data.get("generation_status") == "done":
            start_followup_generation(session_id, part)
            session = load_session(session_id)
            part_data = get_part(session, part) if session else part_data
    return jsonify(generation_view(part_data))


@debate_bp.route("/api/sessions/<session_id>/parts/<part>/tts", methods=["GET"])
def serve_part_tts(session_id, part):
    session = load_session(session_id)
    if not session:
        return jsonify({"error": "セッションが見つかりません。"}), 404
    part_data = get_part(session, part)
    if not part_data or not part_is_ai(part_data):
        return jsonify({"error": "音声が見つかりません。"}), 404
    filename = part_data.get("tts_audio_file") or ""
    path = tts_path(session_id, filename)
    if not path:
        return jsonify({"error": "音声ファイルがまだありません。"}), 404
    response = send_file(
        path,
        mimetype="audio/mpeg",
        as_attachment=False,
        download_name=path.name,
        conditional=True,
    )
    response.headers["Accept-Ranges"] = "bytes"
    return response


@debate_bp.route("/api/sessions/<session_id>/parts/<part>/tts/retry", methods=["POST"])
def retry_part_tts(session_id, part):
    session = load_session(session_id)
    if not session:
        return jsonify({"error": "セッションが見つかりません。"}), 404
    part_data = get_part(session, part)
    if not part_data or not part_is_ai(part_data):
        return jsonify({"error": "このパートは音声再生成の対象ではありません。"}), CONFLICT
    if part_data.get("generation_status") != "done":
        return jsonify({"error": "テキストの生成が完了してから音声を再試行できます。"}), CONFLICT

    from debate.solo_jobs import start_tts_job

    updated = start_tts_job(session_id, part, force=True)
    return jsonify(generation_view(updated)), 202


# ── ④ジャッジ結果画面 ──────────────────────────────────────
def _unconfirmed_parts(session: dict) -> list[str]:
    return [
        part_data["part"]
        for part_data in session.get("parts", [])
        if part_data.get("status") != "confirmed" or not str(part_data.get("transcript_edited") or "").strip()
    ]


@debate_bp.route("/api/sessions/<session_id>/judge", methods=["POST"])
def start_judge(session_id):
    """6パートすべて確定済みであればジャッジ実行をバックグラウンドで開始する。"""
    with get_session_lock(session_id):
        session = load_session(session_id)
        if not session:
            return jsonify({"error": "セッションが見つかりません。"}), 404

        missing = _unconfirmed_parts(session)
        if missing:
            return (
                jsonify(
                    {
                        "error": f"すべてのパートを確定してから実行してください（未確定: {', '.join(missing)}）。"
                    }
                ),
                400,
            )

        judge_result = new_judge_result()
        judge_result["status"] = "judging"
        judge_result["started_at"] = now_iso()
        judge_result["transcription_mode"] = _transcription_mode_summary(session)
        session["judge_result"] = judge_result
        save_session(session)

    start_judge_job(session_id)
    return jsonify(judge_result), 202


@debate_bp.route("/api/sessions/<session_id>/judge", methods=["GET"])
def get_judge_result(session_id):
    """ジャッジ結果画面からのポーリング用の軽量エンドポイント。"""
    session = load_session(session_id)
    if not session:
        return jsonify({"error": "セッションが見つかりません。"}), 404

    judge_result = session.get("judge_result") or new_judge_result()

    if judge_result.get("status") == "judging":
        elapsed = _seconds_since(judge_result.get("started_at"))
        if elapsed is not None and elapsed > JUDGE_STUCK_SEC:
            with get_session_lock(session_id):
                session = load_session(session_id)
                if session:
                    judge_result = session.get("judge_result") or {}
                    if judge_result.get("status") == "judging":
                        judge_result["status"] = "error"
                        judge_result["error"] = (
                            "ジャッジの処理がタイムアウトしました。もう一度実行してください。"
                        )
                        session["judge_result"] = judge_result
                        save_session(session)

    return jsonify(judge_result)


@debate_bp.route("/session/<session_id>/judge")
def judge_screen(session_id):
    session = load_session(session_id)
    if not session:
        return render_template(
            "debate/not_found.html", session_id=session_id, **_background_context()
        ), 404

    return render_template(
        "debate/judge.html",
        session=session,
        part_meta=_part_meta(),
        part_order=PART_ORDER,
        unconfirmed_parts=_unconfirmed_parts(session),
        **_background_context(),
    )


@debate_bp.route("/audio/<session_id>/<path:filename>")
def serve_audio(session_id, filename):
    safe_session_id = Path(session_id).name
    safe_filename = Path(filename).name
    directory = AUDIO_DIR / safe_session_id
    return send_from_directory(directory, safe_filename)
