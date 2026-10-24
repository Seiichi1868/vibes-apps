"""生徒向け有料APIのサーバー全体・種類別の1日上限。

日付は Asia/Tokyo。設定は settings.json。回数は data/debate/paid_usage.json。
上限オフはオフにした時刻から24時間だけで、次のチェック時にオンへ戻す。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from debate.config import DATA_DIR, ensure_dirs
from debate.file_lock import get_named_lock
from debate.settings import load_settings, update_settings

JST = timezone(timedelta(hours=9))
DAILY_LIMIT = 20
UNLIMITED_HOURS = 24
LIMIT_MESSAGE = "1日の使用上限に到達しました。使用する場合は管理者に連絡してください。"
KINDS = ("script", "judge", "tts")


class PaidLimitError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(JST)


def _usage_path():
    return DATA_DIR / "paid_usage.json"


def _usage_lock():
    return get_named_lock(DATA_DIR / "locks" / "paid_usage.lock")


def _parse_stamp(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt.astimezone(JST)


def _empty_usage(day: str) -> dict:
    return {"date": day, "counts": {kind: 0 for kind in KINDS}}


def _read_usage(day: str) -> dict:
    path = _usage_path()
    if not path.is_file():
        return _empty_usage(day)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_usage(day)
    if not isinstance(raw, dict) or raw.get("date") != day:
        return _empty_usage(day)
    counts = raw.get("counts") if isinstance(raw.get("counts"), dict) else {}
    usage = _empty_usage(day)
    for kind in KINDS:
        try:
            usage["counts"][kind] = max(0, int(counts.get(kind) or 0))
        except (TypeError, ValueError):
            usage["counts"][kind] = 0
    return usage


def _write_usage(usage: dict) -> None:
    ensure_dirs()
    path = _usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def refresh_paid_limit_toggle(now: datetime | None = None) -> dict:
    """オフから24時間過ぎていればオンに戻してから設定を返す。"""
    current = _now() if now is None else now
    settings = load_settings()
    if settings.get("paid_daily_limit_enabled", True):
        return settings
    disabled_at = _parse_stamp(settings.get("paid_daily_limit_disabled_at"))
    if disabled_at is None or current - disabled_at >= timedelta(hours=UNLIMITED_HOURS):
        return update_settings(paid_daily_limit_enabled=True, paid_daily_limit_disabled_at=None)
    return settings


def set_paid_daily_limit_enabled(enabled: bool, now: datetime | None = None) -> dict:
    current = _now() if now is None else now
    if enabled:
        return update_settings(paid_daily_limit_enabled=True, paid_daily_limit_disabled_at=None)
    return update_settings(
        paid_daily_limit_enabled=False,
        paid_daily_limit_disabled_at=current.isoformat(timespec="seconds"),
    )


def consume(kind: str, n: int = 1, now: datetime | None = None) -> None:
    """上限内なら回数を足す。上限なら有料APIを呼ぶ前に PaidLimitError。"""
    if kind not in KINDS:
        raise ValueError(f"不明な利用種別です: {kind}")
    count = int(n)
    if count <= 0:
        return
    current = _now() if now is None else now
    settings = refresh_paid_limit_toggle(current)
    limited = bool(settings.get("paid_daily_limit_enabled", True))
    day = current.strftime("%Y-%m-%d")
    with _usage_lock():
        usage = _read_usage(day)
        used = usage["counts"][kind]
        if limited and used + count > DAILY_LIMIT:
            raise PaidLimitError(LIMIT_MESSAGE)
        usage["counts"][kind] = used + count
        _write_usage(usage)


def usage_snapshot(now: datetime | None = None) -> dict:
    current = _now() if now is None else now
    with _usage_lock():
        usage = _read_usage(current.strftime("%Y-%m-%d"))
    return usage
