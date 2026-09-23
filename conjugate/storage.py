"""JSONファイルによる永続化（conjugate独自。他アプリとは別ファイル・別スキーマ）。

- conjugate_settings.json    : 出題カテゴリ・文型・ASR設定・判定の厳しさ等
- conjugate_submissions.json : セッション終了時の結果サマリ（配列）
- conjugate_weak_verbs.json  : 動詞ごとの誤答回数集計（弱点優先出題に利用）
- conjugate_progress.json    : ストリーク・累計練習数・動詞ごとの習得状況
- sessions/<id>.json         : 進行中の出題セッション
"""
import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from conjugate.config import (
    BACKGROUND_PRESETS,
    DEFAULT_ASR_ENGINE,
    DEFAULT_BACKGROUND_ID,
    DEFAULT_BACKGROUND_OPACITY,
    DEFAULT_CONJUGATION_MASTERY_THRESHOLD,
    DEFAULT_ENABLED_CATEGORIES,
    DEFAULT_ENABLED_TENSES,
    DEFAULT_GUARDIAN_PRICE_COINS,
    DEFAULT_GUSTAR_ENABLED,
    DEFAULT_GUSTAR_PER_SESSION,
    DEFAULT_OPENING_ENABLED,
    DEFAULT_OPENING_MS,
    DEFAULT_PERSON_MODE,
    DEFAULT_PRIORITIZE_WEAK_VERBS,
    DEFAULT_QUESTIONS_PER_SESSION,
    DEFAULT_STRICTNESS,
    DEFAULT_TARGETS_PER_QUESTION,
    DEFAULT_VOCAB_MASTERY_THRESHOLD,
    DEFAULT_WHISPER_MODEL,
    PROGRESS_FILE,
    SESSIONS_DIR,
    SETTINGS_FILE,
    SUBMISSIONS_FILE,
    WEAK_VERBS_FILE,
    clamp_daily_goal,
    clamp_guardian_price,
    clamp_mastery_threshold,
    clamp_opening_ms,
    clamp_opacity,
    ensure_dirs,
)
from conjugate.data.conjugations import TENSE_ORDER
from conjugate.data.persons import PERSON_MODES
from conjugate.data.verbs import CATEGORY_ORDER
from conjugate.progress import (
    apply_attempt,
    apply_guardian_purchase,
    normalize_progress,
    progress_view,
    verb_progress_list,
    vocab_progress_list,
)

_lock = threading.Lock()
_session_locks: dict[str, threading.Lock] = {}
_session_locks_guard = threading.Lock()

JST = timezone(timedelta(hours=9))


def _now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _read_json(path, default):
    if not path.is_file():
        return deepcopy(default)
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return deepcopy(default)


def _write_json(path, data) -> None:
    ensure_dirs()
    tmp_path = path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


# ── 設定 ────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "enabled_categories": list(DEFAULT_ENABLED_CATEGORIES),
    "enabled_tenses": list(DEFAULT_ENABLED_TENSES),
    "asr_engine": DEFAULT_ASR_ENGINE,
    "whisper_model": DEFAULT_WHISPER_MODEL,
    "strictness": DEFAULT_STRICTNESS,
    "questions_per_session": DEFAULT_QUESTIONS_PER_SESSION,
    "targets_per_question": DEFAULT_TARGETS_PER_QUESTION,
    "gustar_enabled": DEFAULT_GUSTAR_ENABLED,
    "gustar_per_session": DEFAULT_GUSTAR_PER_SESSION,
    "prioritize_weak_verbs": DEFAULT_PRIORITIZE_WEAK_VERBS,
    "person_mode": DEFAULT_PERSON_MODE,
    "background_id": DEFAULT_BACKGROUND_ID,
    "background_opacity": DEFAULT_BACKGROUND_OPACITY,
    "opening_enabled": DEFAULT_OPENING_ENABLED,
    "opening_ms": DEFAULT_OPENING_MS,
    "conjugation_mastery_threshold": DEFAULT_CONJUGATION_MASTERY_THRESHOLD,
    "vocab_mastery_threshold": DEFAULT_VOCAB_MASTERY_THRESHOLD,
    "guardian_price_coins": DEFAULT_GUARDIAN_PRICE_COINS,
}


def _normalize_settings(raw: dict | None) -> dict:
    data = deepcopy(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return data

    categories = raw.get("enabled_categories")
    if isinstance(categories, list):
        filtered = [c for c in categories if c in CATEGORY_ORDER]
        data["enabled_categories"] = filtered or list(DEFAULT_ENABLED_CATEGORIES)

    tenses = raw.get("enabled_tenses")
    if isinstance(tenses, list):
        filtered = [t for t in tenses if t in TENSE_ORDER]
        data["enabled_tenses"] = filtered or list(DEFAULT_ENABLED_TENSES)

    if raw.get("asr_engine") in ("whisper", "web_speech"):
        data["asr_engine"] = raw["asr_engine"]
    if raw.get("whisper_model") in ("whisper-1", "gpt-4o-mini-transcribe"):
        data["whisper_model"] = raw["whisper_model"]
    if raw.get("strictness") in ("lenient", "strict"):
        data["strictness"] = raw["strictness"]

    try:
        qps = int(raw.get("questions_per_session", DEFAULT_QUESTIONS_PER_SESSION))
        data["questions_per_session"] = max(3, min(50, qps))
    except (TypeError, ValueError):
        pass

    try:
        tpq = int(raw.get("targets_per_question", DEFAULT_TARGETS_PER_QUESTION))
        data["targets_per_question"] = 2 if tpq >= 2 else 1
    except (TypeError, ValueError):
        pass

    if "gustar_enabled" in raw:
        data["gustar_enabled"] = bool(raw.get("gustar_enabled"))

    try:
        gps = int(raw.get("gustar_per_session", DEFAULT_GUSTAR_PER_SESSION))
        data["gustar_per_session"] = max(0, min(5, gps))
    except (TypeError, ValueError):
        pass

    if "prioritize_weak_verbs" in raw:
        data["prioritize_weak_verbs"] = bool(raw.get("prioritize_weak_verbs"))

    if raw.get("person_mode") in PERSON_MODES:
        data["person_mode"] = raw["person_mode"]

    bg_id = raw.get("background_id")
    if bg_id in BACKGROUND_PRESETS:
        data["background_id"] = bg_id
    if "background_opacity" in raw:
        data["background_opacity"] = clamp_opacity(raw.get("background_opacity"))
    if "opening_enabled" in raw:
        data["opening_enabled"] = bool(raw.get("opening_enabled"))
    if "opening_ms" in raw:
        data["opening_ms"] = clamp_opening_ms(raw.get("opening_ms"))
    if "conjugation_mastery_threshold" in raw:
        data["conjugation_mastery_threshold"] = clamp_mastery_threshold(
            raw.get("conjugation_mastery_threshold"),
            DEFAULT_CONJUGATION_MASTERY_THRESHOLD,
        )
    if "vocab_mastery_threshold" in raw:
        data["vocab_mastery_threshold"] = clamp_mastery_threshold(
            raw.get("vocab_mastery_threshold"),
            DEFAULT_VOCAB_MASTERY_THRESHOLD,
        )
    if "guardian_price_coins" in raw:
        data["guardian_price_coins"] = clamp_guardian_price(
            raw.get("guardian_price_coins"),
            DEFAULT_GUARDIAN_PRICE_COINS,
        )

    return data


def load_settings() -> dict:
    ensure_dirs()
    with _lock:
        return _normalize_settings(_read_json(SETTINGS_FILE, DEFAULT_SETTINGS))


def save_settings(data: dict) -> dict:
    normalized = _normalize_settings(data)
    with _lock:
        _write_json(SETTINGS_FILE, normalized)
    return normalized


# ── セッション（進行中の出題） ───────────────────────────────

def _safe_id(value: str) -> str:
    return "".join(c for c in str(value) if c.isalnum() or c == "-")


def _session_path(session_id: str):
    return SESSIONS_DIR / f"{_safe_id(session_id)}.json"


def get_session_lock(session_id: str) -> threading.Lock:
    safe_id = _safe_id(session_id)
    with _session_locks_guard:
        lock = _session_locks.get(safe_id)
        if lock is None:
            lock = threading.Lock()
            _session_locks[safe_id] = lock
        return lock


def new_session_id() -> str:
    return uuid.uuid4().hex[:16]


def save_session(session: dict) -> dict:
    session["updated_at"] = _now_iso()
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


# ── セッション結果サマリ ─────────────────────────────────────

def load_submissions() -> list[dict]:
    ensure_dirs()
    with _lock:
        data = _read_json(SUBMISSIONS_FILE, [])
    return data if isinstance(data, list) else []


def save_submission(entry: dict) -> dict:
    ensure_dirs()
    entry = {"id": uuid.uuid4().hex[:12], "submitted_at": _now_iso(), **entry}
    with _lock:
        submissions = _read_json(SUBMISSIONS_FILE, [])
        if not isinstance(submissions, list):
            submissions = []
        submissions.append(entry)
        # 直近500件のみ保持（無制限肥大化を防ぐ）
        submissions = submissions[-500:]
        _write_json(SUBMISSIONS_FILE, submissions)
    return entry


def get_submissions(limit: int = 50) -> list[dict]:
    return list(reversed(load_submissions()))[:limit]


# ── 弱点動詞集計 ─────────────────────────────────────────────

def load_weak_verbs() -> dict:
    ensure_dirs()
    with _lock:
        data = _read_json(WEAK_VERBS_FILE, {})
    return data if isinstance(data, dict) else {}


def record_answer_result(verb_id: int, infinitive: str, level: str) -> None:
    """1問の採点結果を弱点動詞集計に反映する。"""
    with _lock:
        stats = _read_json(WEAK_VERBS_FILE, {})
        if not isinstance(stats, dict):
            stats = {}
        key = str(verb_id)
        entry = stats.get(key) or {"infinitive": infinitive, "miss_count": 0, "correct_count": 0}
        entry["infinitive"] = infinitive
        if level == "correct":
            entry["correct_count"] = entry.get("correct_count", 0) + 1
            entry["miss_count"] = max(0, entry.get("miss_count", 0) - 1)
        else:
            entry["miss_count"] = entry.get("miss_count", 0) + 1
        entry["last_result"] = level
        entry["last_seen"] = _now_iso()
        stats[key] = entry
        _write_json(WEAK_VERBS_FILE, stats)


def _numeric_verb_ids(stats: dict) -> list[tuple[str, dict]]:
    """gustar等の非数値キーを除いた、通常動詞（verb_id）分のみ抽出。"""
    return [(k, v) for k, v in stats.items() if k.isdigit()]


def top_weak_verb_ids(limit: int = 20) -> list[int]:
    stats = load_weak_verbs()
    ranked = sorted(
        _numeric_verb_ids(stats),
        key=lambda kv: (kv[1].get("miss_count", 0)),
        reverse=True,
    )
    return [int(k) for k, v in ranked if v.get("miss_count", 0) > 0][:limit]


def weak_verbs_report(limit: int = 15) -> list[dict]:
    stats = load_weak_verbs()
    ranked = sorted(
        stats.items(),
        key=lambda kv: (kv[1].get("miss_count", 0)),
        reverse=True,
    )
    result = []
    for verb_id, entry in ranked[:limit]:
        if entry.get("miss_count", 0) <= 0:
            continue
        result.append({"verb_id": int(verb_id) if verb_id.isdigit() else verb_id, **entry})
    return result


# ── 学習進捗（ストリーク・累計・習得） ─────────────────────

def _mastery_thresholds(settings: dict | None = None) -> tuple[int, int]:
    data = settings if isinstance(settings, dict) else load_settings()
    return (
        clamp_mastery_threshold(
            data.get("conjugation_mastery_threshold"),
            DEFAULT_CONJUGATION_MASTERY_THRESHOLD,
        ),
        clamp_mastery_threshold(
            data.get("vocab_mastery_threshold"),
            DEFAULT_VOCAB_MASTERY_THRESHOLD,
        ),
    )


def _guardian_price(settings: dict | None = None) -> int:
    data = settings if isinstance(settings, dict) else load_settings()
    return clamp_guardian_price(data.get("guardian_price_coins"), DEFAULT_GUARDIAN_PRICE_COINS)


def _progress_view_from(data: dict, settings: dict | None = None) -> dict:
    conj_th, vocab_th = _mastery_thresholds(settings)
    guardian_price = _guardian_price(settings)
    return progress_view(
        data,
        conjugation_threshold=conj_th,
        vocab_threshold=vocab_th,
        guardian_price=guardian_price,
    )


def load_progress() -> dict:
    ensure_dirs()
    with _lock:
        return normalize_progress(_read_json(PROGRESS_FILE, {}))


def record_progress(
    *,
    verb_id=None,
    tense: str | None = None,
    is_correct: bool = False,
    kind: str = "conjugation",
    direction: str | None = None,
    person: str | None = None,
    track_mastery: bool = True,
) -> dict:
    """判定1回分を進捗に反映し、更新後のサマリを返す。"""
    settings = load_settings()
    conj_th, vocab_th = _mastery_thresholds(settings)
    threshold = vocab_th if kind == "vocab" else conj_th
    with _lock:
        data = normalize_progress(_read_json(PROGRESS_FILE, {}))
        delta = apply_attempt(
            data,
            verb_id=verb_id,
            tense=tense,
            is_correct=is_correct,
            kind=kind,
            threshold=threshold,
            direction=direction,
            person=person,
            track_mastery=track_mastery,
        )
        _write_json(PROGRESS_FILE, data)
        view = _progress_view_from(data, settings)
        view.update(delta)
        return view


def purchase_guardian() -> dict:
    """コインを消費してGuardiánを1体購入する（発動ロジックはPart 2で実装）。"""
    settings = load_settings()
    price = _guardian_price(settings)
    with _lock:
        data = normalize_progress(_read_json(PROGRESS_FILE, {}))
        success = apply_guardian_purchase(data, price)
        if success:
            _write_json(PROGRESS_FILE, data)
        view = _progress_view_from(data, settings)
        view["ok"] = success
        if not success:
            view["error"] = "コインが足りません。"
        return view


def save_daily_goal(goal) -> dict:
    settings = load_settings()
    value = clamp_daily_goal(goal, default=0)
    if value == 0:
        value = 10
    with _lock:
        data = normalize_progress(_read_json(PROGRESS_FILE, {}))
        data["daily_goal"] = value
        _write_json(PROGRESS_FILE, data)
        return _progress_view_from(data, settings)


def progress_summary() -> dict:
    settings = load_settings()
    return _progress_view_from(load_progress(), settings)


def progress_detail() -> dict:
    settings = load_settings()
    conj_th, vocab_th = _mastery_thresholds(settings)
    data = load_progress()
    view = _progress_view_from(data, settings)
    view["verbs"] = verb_progress_list(data, conj_th)
    view["vocab_verbs"] = vocab_progress_list(data, vocab_th)
    return view


def progress_verbs() -> list[dict]:
    conj_th, _ = _mastery_thresholds()
    return verb_progress_list(load_progress(), conj_th)
