"""CNN10 の全エピソードタイトルをローカルに蓄積し、キーワード検索する。

ページ取得は cnn10.py の既存ヘルパ（チャンネルページ + continuation）を読み取り専用で再利用する。
cnn10._CACHE と app_state.json には触れず、data/cnn10_library.json に独立して保存する。

本番は gunicorn 複数ワーカーのため、実行中フラグはメモリではなくファイルロックで共有する。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fcntl
import json
import logging
import os
import re
import threading
import time
from urllib.error import URLError

from news_app.config import DATA_DIR
from news_app.services import cnn10

logger = logging.getLogger(__name__)

LIBRARY_FILE = DATA_DIR / "cnn10_library.json"
JOB_FILE = DATA_DIR / "cnn10_library_job.json"
LOCK_FILE = DATA_DIR / "cnn10_library.lock"

PAGE_DELAY_SEC = 0.5
MAX_PAGES_FULL = 300
MAX_PAGES_DIFF = 20
MAX_EPISODES = 10000
MAX_EMPTY_PAGES = 3
SAVE_EVERY_PAGES = 10
SEARCH_DEFAULT_LIMIT = 50
SEARCH_MAX_LIMIT = 200

_file_lock = threading.Lock()

_MONTHS = {
    name: index
    for index, name in enumerate(
        (
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ),
        start=1,
    )
}
_EN_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)
_JA_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_REL_EN_RE = re.compile(r"(\d+)\s*(second|minute|hour|day|week|month|year)s?\s+ago", re.IGNORECASE)
_REL_JA_RE = re.compile(r"(\d+)\s*(秒|分|時間|日|週間|か月|ヶ月|カ月|年)\s*前")
_REL_UNIT_DAYS = {
    "second": 0, "minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365,
    "秒": 0, "分": 0, "時間": 0, "日": 1, "週間": 7, "か月": 30, "ヶ月": 30, "カ月": 30, "年": 365,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 日付の推定
# ---------------------------------------------------------------------------

def _date_from_title(title: str) -> str:
    text = str(title or "")
    match = _EN_DATE_RE.search(text)
    if match:
        month = _MONTHS[match.group(1).lower()]
        day, year = int(match.group(2)), int(match.group(3))
    else:
        match = _JA_DATE_RE.search(text)
        if not match:
            return ""
        year, month, day = (int(match.group(i)) for i in (1, 2, 3))
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _date_from_relative(text: str, now: datetime) -> str:
    raw = str(text or "")
    match = _REL_EN_RE.search(raw) or _REL_JA_RE.search(raw)
    if not match:
        return ""
    amount = int(match.group(1))
    unit = match.group(2).lower() if match.re is _REL_EN_RE else match.group(2)
    days = amount * _REL_UNIT_DAYS.get(unit, 0)
    return (now - timedelta(days=days)).strftime("%Y-%m-%d")


def _relative_dates_by_video(data: dict) -> dict[str, str]:
    """lockup の 2 番目のメタ情報（"1 month ago" 等）を video_id ごとに拾う。"""
    result: dict[str, str] = {}

    def walk(obj) -> None:
        if isinstance(obj, dict):
            lockup = obj.get("lockupViewModel")
            if isinstance(lockup, dict):
                video_id = str(lockup.get("contentId") or "").strip()
                rows = (
                    lockup.get("metadata", {})
                    .get("lockupMetadataViewModel", {})
                    .get("metadata", {})
                    .get("contentMetadataViewModel", {})
                    .get("metadataRows", [])
                )
                texts = [
                    str(part.get("text", {}).get("content", "") or "")
                    for row in rows
                    for part in row.get("metadataParts", [])
                ]
                for text in texts:
                    if video_id and (_REL_EN_RE.search(text) or _REL_JA_RE.search(text)):
                        result[video_id] = text
                        break
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(data)
    return result


def _to_library_items(episodes: list[dict], relative_dates: dict[str, str], now: datetime) -> list[dict]:
    items = []
    for episode in episodes:
        video_id = str(episode.get("video_id") or "").strip()
        if not video_id:
            continue
        title = str(episode.get("title") or "").strip() or "Untitled"
        published = _date_from_title(title)
        estimated = False
        if not published:
            published = _date_from_relative(relative_dates.get(video_id, ""), now)
            estimated = bool(published)
        items.append(
            {
                "video_id": video_id,
                "title": title,
                "published": published,
                "published_estimated": estimated,
            }
        )
    return items


# ---------------------------------------------------------------------------
# ページ取得（cnn10.py のヘルパを再利用）
# ---------------------------------------------------------------------------

def _fetch_first_page(now: datetime) -> tuple[list[dict], str | None]:
    html = cnn10._fetch_bytes(cnn10.CNN10_VIDEOS_PAGE, timeout=12).decode("utf-8", errors="replace")
    data = cnn10._parse_yt_initial_data(html)
    episodes, _ = cnn10._extract_episodes_and_tokens(data)
    relative = _relative_dates_by_video(data)
    # チャンネル HTML はアクセス元の地域で日本語タイトルになることがあるため、英語題に寄せる。
    episodes = cnn10._enrich_english_titles(episodes)
    return _to_library_items(episodes, relative, now), cnn10._grid_continuation_token(data)


def _fetch_next_page(token: str, now: datetime) -> tuple[list[dict], str | None]:
    payload = {"context": {"client": cnn10.INNERTUBE_CLIENT}, "continuation": token}
    data = cnn10._post_json(cnn10.INNERTUBE_BROWSE_URL, payload)
    episodes, tokens = cnn10._extract_episodes_and_tokens(data)
    relative = _relative_dates_by_video(data)
    next_token = cnn10._grid_continuation_token(data) or (tokens[-1] if tokens else None)
    return _to_library_items(episodes, relative, now), next_token


# ---------------------------------------------------------------------------
# 保存
# ---------------------------------------------------------------------------

def _write_json_atomic(path, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _read_json(path) -> dict:
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def load_library() -> dict:
    with _file_lock:
        data = _read_json(LIBRARY_FILE)
    episodes = data.get("episodes") if isinstance(data.get("episodes"), list) else []
    return {
        "updated_at": data.get("updated_at") or "",
        "full_fetched_at": data.get("full_fetched_at") or "",
        "episodes": [item for item in episodes if isinstance(item, dict) and item.get("video_id")],
    }


def _save_library(episodes: list[dict], *, full_completed: bool = False) -> dict:
    with _file_lock:
        previous = _read_json(LIBRARY_FILE)
        data = {
            "updated_at": _now_iso(),
            "full_fetched_at": _now_iso() if full_completed else (previous.get("full_fetched_at") or ""),
            "count": len(episodes),
            "episodes": episodes,
        }
        _write_json_atomic(LIBRARY_FILE, data)
    return data


def _merge_front(new_items: list[dict], existing: list[dict]) -> list[dict]:
    """new_items を先頭に置き、既存分のうち未登場のものを後ろに残す（取得失敗で既存を消さない）。"""
    seen: set[str] = set()
    merged: list[dict] = []
    for item in list(new_items) + list(existing):
        video_id = item.get("video_id")
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        merged.append(item)
    return merged


# ---------------------------------------------------------------------------
# 取得本体
# ---------------------------------------------------------------------------

_FETCH_ERRORS = (OSError, URLError, json.JSONDecodeError, RuntimeError, ValueError)


def _crawl(*, stop_at_known: set[str] | None, max_pages: int, progress=None) -> dict:
    """先頭ページから順に取得する。stop_at_known に当たったら打ち切る（差分用）。"""
    now = datetime.now()
    collected: list[dict] = []
    seen: set[str] = set()
    pages = 0
    empty_pages = 0
    reached_known = False
    exhausted = False
    error = ""
    token: str | None = None

    while True:
        try:
            if pages == 0:
                items, token = _fetch_first_page(now)
            else:
                items, token = _fetch_next_page(token, now)
        except _FETCH_ERRORS as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("cnn10 library: page %s failed: %s", pages + 1, exc)
            break
        pages += 1

        added = 0
        for item in items:
            video_id = item["video_id"]
            if stop_at_known is not None and video_id in stop_at_known:
                reached_known = True
                break
            if video_id in seen:
                continue
            seen.add(video_id)
            collected.append(item)
            added += 1

        empty_pages = 0 if added else empty_pages + 1
        if progress:
            progress(pages=pages, fetched=len(collected), partial=collected)

        if reached_known:
            break
        if not token:
            exhausted = True
            break
        if empty_pages >= MAX_EMPTY_PAGES or pages >= max_pages or len(collected) >= MAX_EPISODES:
            break
        time.sleep(PAGE_DELAY_SEC)

    return {
        "items": collected,
        "pages": pages,
        "reached_known": reached_known,
        "exhausted": exhausted,
        "error": error,
    }


def fetch_all_episodes(progress=None) -> dict:
    """全件取得して保存する（初回用）。途中で失敗しても取得できた分は保存する。"""
    existing = load_library()["episodes"]
    saved_pages = {"count": 0}

    def on_progress(pages: int, fetched: int, partial: list[dict]) -> None:
        if progress:
            progress(pages=pages, fetched=fetched)
        if pages - saved_pages["count"] >= SAVE_EVERY_PAGES:
            saved_pages["count"] = pages
            _save_library(_merge_front(partial, existing))

    result = _crawl(stop_at_known=None, max_pages=MAX_PAGES_FULL, progress=on_progress)
    merged = _merge_front(result["items"], existing)
    if result["items"] or not existing:
        _save_library(merged, full_completed=result["exhausted"] and not result["error"])
    return {
        "mode": "full",
        "fetched": len(result["items"]),
        "added": len(merged) - len(existing),
        "total": len(merged),
        "pages": result["pages"],
        "complete": result["exhausted"],
        "error": result["error"],
    }


def update_new_episodes(progress=None) -> dict:
    """先頭から取得し、既知の video_id に当たったら打ち切って新規分だけ追加する（週次差分用）。"""
    existing = load_library()["episodes"]
    if not existing:
        return fetch_all_episodes(progress=progress)

    known = {item["video_id"] for item in existing}

    def on_progress(pages: int, fetched: int, partial: list[dict]) -> None:
        if progress:
            progress(pages=pages, fetched=fetched)

    result = _crawl(stop_at_known=known, max_pages=MAX_PAGES_DIFF, progress=on_progress)
    merged = _merge_front(result["items"], existing)
    if result["items"] or not result["error"]:
        _save_library(merged)
    return {
        "mode": "diff",
        "fetched": len(result["items"]),
        "added": len(merged) - len(existing),
        "total": len(merged),
        "pages": result["pages"],
        "complete": result["reached_known"] or result["exhausted"],
        "error": result["error"],
    }


# ---------------------------------------------------------------------------
# バックグラウンド実行（HTTP リクエストを待たせない）
# ---------------------------------------------------------------------------

def _try_lock():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handle = LOCK_FILE.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def _is_running() -> bool:
    handle = _try_lock()
    if handle is None:
        return True
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()
    return False


def _write_job(job: dict) -> None:
    with _file_lock:
        _write_json_atomic(JOB_FILE, job)


def _run_job(handle, mode: str) -> None:
    job = {"mode": mode, "running": True, "started_at": _now_iso(), "pages": 0, "fetched": 0}
    _write_job(job)

    def progress(pages: int, fetched: int) -> None:
        job.update(pages=pages, fetched=fetched, heartbeat_at=_now_iso())
        _write_job(job)

    try:
        func = fetch_all_episodes if mode == "full" else update_new_episodes
        result = func(progress=progress)
        job.update(result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("cnn10 library job failed")
        job["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        job.update(running=False, finished_at=_now_iso())
        _write_job(job)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def start_update_job(mode: str = "diff") -> dict:
    """更新をバックグラウンドで開始する。既に実行中なら何もしない。"""
    mode = "full" if mode == "full" else "diff"
    handle = _try_lock()
    if handle is None:
        return {"started": False, **get_library_status()}
    thread = threading.Thread(target=_run_job, args=(handle, mode), name="cnn10-library", daemon=True)
    thread.start()
    return {"started": True, **get_library_status()}


# ---------------------------------------------------------------------------
# 状態・検索
# ---------------------------------------------------------------------------

def get_library_status() -> dict:
    """最終更新日時と件数（＋実行中ジョブの進捗）を返す。"""
    library = load_library()
    with _file_lock:
        job = _read_json(JOB_FILE)
    running = _is_running()
    if job.get("running") and not running:
        job["running"] = False
        job.setdefault("error", "更新処理が中断されました。")
    return {
        "updated_at": library["updated_at"],
        "full_fetched_at": library["full_fetched_at"],
        "count": len(library["episodes"]),
        "running": running,
        "job": job,
    }


def search_episodes(query: str, limit: int = SEARCH_DEFAULT_LIMIT) -> dict:
    """タイトルの大文字小文字無視の部分一致検索。空白区切りの語はすべて含むもの（AND）。"""
    terms = [term.casefold() for term in str(query or "").split() if term.strip()]
    limit = max(1, min(int(limit or SEARCH_DEFAULT_LIMIT), SEARCH_MAX_LIMIT))
    episodes = load_library()["episodes"]
    if not terms:
        return {"query": str(query or ""), "total": 0, "episodes": []}

    matches = [
        item for item in episodes
        if all(term in str(item.get("title") or "").casefold() for term in terms)
    ]
    matches.sort(key=lambda item: item.get("published") or "", reverse=True)
    page = [
        {
            **item,
            "url": f"https://www.youtube.com/watch?v={item['video_id']}",
            "thumbnail_url": cnn10.YOUTUBE_THUMBNAIL_URL.format(video_id=item["video_id"]),
        }
        for item in matches[:limit]
    ]
    return {"query": str(query or ""), "total": len(matches), "episodes": page}
