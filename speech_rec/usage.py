"""日次・月次の費用。追記は flock。API キーは書かない。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from speech_rec.config import data_dir
from speech_rec.settings import get_settings
from speech_rec.store import append_line

JST = ZoneInfo("Asia/Tokyo")


def _now() -> datetime:
    return datetime.now(JST)


def usage_path():
    return data_dir() / "usage.jsonl"


def record_cost(usd: float, *, kind: str, model: str) -> None:
    row = {
        "at": _now().isoformat(timespec="seconds"),
        "kind": kind,
        "model": model,
        "usd": round(float(usd), 6),
    }
    append_line(usage_path(), json.dumps(row, ensure_ascii=False))


def _rows() -> list[dict]:
    path = usage_path()
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and "usd" in row and "at" in row:
            rows.append(row)
    return rows


def _parse(at: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(at)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST)


def summarize() -> dict:
    now = _now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    today = month = 0.0
    for row in _rows():
        dt = _parse(str(row.get("at") or ""))
        if dt is None:
            continue
        usd = float(row.get("usd") or 0)
        if dt >= month_start:
            month += usd
        if dt >= day_start:
            today += usd
    limit = float(get_settings().get("daily_limit_usd") or 0)
    return {
        "today_usd": round(today, 6),
        "month_usd": round(month, 6),
        "daily_limit_usd": limit,
        "over_daily_limit": limit > 0 and today >= limit,
        "as_of": now.isoformat(timespec="seconds"),
    }


def daily_limit_reached() -> bool:
    return bool(summarize()["over_daily_limit"])


def retention_cutoff(days: int) -> datetime:
    return _now() - timedelta(days=max(0, int(days)))
