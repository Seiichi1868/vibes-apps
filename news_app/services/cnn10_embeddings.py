"""CNN10 ライブラリのタイトル意味検索（β）。

cnn10_library.json は読むだけで変更しない。ベクトルは data/cnn10_library_embeddings.json に別保存する。
保存形式: {"model", "dimensions", "updated_at", "vectors": {video_id: base64(float32 正規化済み)}}
（JSON の数値配列だと 1 本あたり 10KB 超になるため、float32 の base64 にしている）
"""

from __future__ import annotations

from array import array
import base64
from datetime import datetime, timezone
import fcntl
import json
import logging
import math
from operator import mul
import os
import re
import threading
import time

from openai import OpenAI

from news_app.config import DATA_DIR, get_openai_api_key
from news_app.services.cnn10_library import load_library
from news_app.services import cnn10

logger = logging.getLogger(__name__)

EMBEDDINGS_FILE = DATA_DIR / "cnn10_library_embeddings.json"
JOB_FILE = DATA_DIR / "cnn10_embeddings_job.json"
LOCK_FILE = DATA_DIR / "cnn10_embeddings.lock"

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 512
BATCH_SIZE = 50
BATCH_DELAY_SEC = 0.3
MAX_BATCHES = 400
INLINE_SYNC_MAX = 100
SEMANTIC_DEFAULT_LIMIT = 10
SEMANTIC_MAX_LIMIT = 50

_file_lock = threading.Lock()
_cache: dict = {"mtime": None, "vectors": {}}

_TITLE_DATE_SUFFIX_RE = re.compile(r"\s*\|\s*[A-Za-z]+\s+\d{1,2},?\s+\d{4}\s*$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _embedding_text(title: str) -> str:
    """末尾の「| September 25, 2026」は意味に寄与しないので外す。"""
    text = _TITLE_DATE_SUFFIX_RE.sub("", str(title or "")).strip()
    return text or str(title or "").strip() or "Untitled"


def _encode(vector: list[float]) -> str:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return base64.b64encode(array("f", (v / norm for v in vector)).tobytes()).decode("ascii")


def _decode(raw: str) -> array:
    vec = array("f")
    vec.frombytes(base64.b64decode(raw))
    return vec


# ---------------------------------------------------------------------------
# 保存
# ---------------------------------------------------------------------------

def _read_json(path) -> dict:
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_atomic(path, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _load_raw_vectors() -> dict[str, str]:
    with _file_lock:
        data = _read_json(EMBEDDINGS_FILE)
    if data.get("model") != EMBEDDING_MODEL or data.get("dimensions") != EMBEDDING_DIMENSIONS:
        return {}
    vectors = data.get("vectors")
    return vectors if isinstance(vectors, dict) else {}


def _save_raw_vectors(vectors: dict[str, str]) -> None:
    with _file_lock:
        _write_json_atomic(
            EMBEDDINGS_FILE,
            {
                "model": EMBEDDING_MODEL,
                "dimensions": EMBEDDING_DIMENSIONS,
                "updated_at": _now_iso(),
                "count": len(vectors),
                "vectors": vectors,
            },
        )


def _load_vectors_cached() -> dict[str, array]:
    """検索のたびに数 MB の JSON を読まないよう、更新時刻が変わったときだけ読み直す。"""
    try:
        mtime = EMBEDDINGS_FILE.stat().st_mtime
    except FileNotFoundError:
        return {}
    if _cache["mtime"] != mtime:
        raw = _load_raw_vectors()
        _cache["vectors"] = {vid: _decode(value) for vid, value in raw.items()}
        _cache["mtime"] = mtime
    return _cache["vectors"]


# ---------------------------------------------------------------------------
# Embedding 計算
# ---------------------------------------------------------------------------

def _client() -> OpenAI:
    api_key = get_openai_api_key()
    if not api_key:
        raise ValueError("OpenAI API キーが未設定です。管理画面の設定からキーを保存してください。")
    return OpenAI(api_key=api_key, timeout=60.0)


def _embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    ordered = sorted(response.data, key=lambda item: item.index)
    return [item.embedding for item in ordered]


def _missing_episodes() -> tuple[list[dict], dict[str, str]]:
    vectors = _load_raw_vectors()
    missing = [item for item in load_library()["episodes"] if item["video_id"] not in vectors]
    return missing, vectors


def embed_missing_titles(progress=None, max_items: int | None = None) -> dict:
    """まだベクトルが無いタイトルだけをバッチで Embedding 化して追記する。

    初期化にも差分追加にも使う（全件再計算はしない）。バッチごとに保存するため、
    途中で失敗しても次回はその続きから再開される。
    """
    missing, vectors = _missing_episodes()
    if max_items is not None:
        missing = missing[:max_items]
    total = len(missing)
    done = 0
    error = ""
    if not missing:
        return {"embedded": 0, "target": 0, "total": len(vectors), "error": ""}

    client = _client()
    for batch_index in range(0, total, BATCH_SIZE):
        if batch_index // BATCH_SIZE >= MAX_BATCHES:
            break
        batch = missing[batch_index : batch_index + BATCH_SIZE]
        try:
            embeddings = _embed_texts(client, [_embedding_text(item["title"]) for item in batch])
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("cnn10 embeddings: batch %s failed: %s", batch_index // BATCH_SIZE + 1, exc)
            break
        for item, embedding in zip(batch, embeddings):
            vectors[item["video_id"]] = _encode(embedding)
        done += len(batch)
        _save_raw_vectors(vectors)
        if progress:
            progress(embedded=done, target=total)
        if batch_index + BATCH_SIZE < total:
            time.sleep(BATCH_DELAY_SEC)

    return {"embedded": done, "target": total, "total": len(vectors), "error": error}


# ---------------------------------------------------------------------------
# バックグラウンド実行
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


def _release(handle) -> None:
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()


def _is_running() -> bool:
    handle = _try_lock()
    if handle is None:
        return True
    _release(handle)
    return False


def _write_job(job: dict) -> None:
    with _file_lock:
        _write_json_atomic(JOB_FILE, job)


def _run_job(handle) -> None:
    job = {"running": True, "started_at": _now_iso(), "embedded": 0, "target": 0}
    _write_job(job)

    def progress(embedded: int, target: int) -> None:
        job.update(embedded=embedded, target=target, heartbeat_at=_now_iso())
        _write_job(job)

    try:
        job.update(embed_missing_titles(progress=progress))
    except Exception as exc:  # noqa: BLE001
        logger.exception("cnn10 embeddings job failed")
        job["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        job.update(running=False, finished_at=_now_iso())
        _write_job(job)
        _release(handle)


def start_embedding_job() -> dict:
    """未計算分の Embedding 化をバックグラウンドで開始する。既に実行中なら何もしない。"""
    if not get_openai_api_key():
        raise ValueError("OpenAI API キーが未設定です。管理画面の設定からキーを保存してください。")
    handle = _try_lock()
    if handle is None:
        return {"started": False, **get_embedding_status()}
    thread = threading.Thread(target=_run_job, args=(handle,), name="cnn10-embeddings", daemon=True)
    thread.start()
    return {"started": True, **get_embedding_status()}


def get_embedding_status() -> dict:
    episodes = load_library()["episodes"]
    vectors = _load_raw_vectors()
    embedded = sum(1 for item in episodes if item["video_id"] in vectors)
    with _file_lock:
        job = _read_json(JOB_FILE)
    running = _is_running()
    if job.get("running") and not running:
        job["running"] = False
        job.setdefault("error", "Embedding 化が中断されました。")
    return {
        "library_count": len(episodes),
        "embedded_count": embedded,
        "missing_count": len(episodes) - embedded,
        "ready": embedded > 0,
        "running": running,
        "model": EMBEDDING_MODEL,
        "job": job,
    }


# ---------------------------------------------------------------------------
# 意味検索
# ---------------------------------------------------------------------------

def semantic_search(query: str, limit: int = SEMANTIC_DEFAULT_LIMIT) -> dict:
    """クエリを Embedding 化し、保存済みタイトルとのコサイン類似度上位を返す。"""
    query = str(query or "").strip()
    limit = max(1, min(int(limit or SEMANTIC_DEFAULT_LIMIT), SEMANTIC_MAX_LIMIT))
    if not query:
        return {"query": query, "episodes": [], "synced": 0}

    synced = 0
    if not _is_running():
        missing, _ = _missing_episodes()
        # 差分更新で増えた少数の新着だけならその場で追記する（大量なら init ジョブに任せる）。
        if missing and len(missing) <= INLINE_SYNC_MAX and _load_raw_vectors():
            handle = _try_lock()
            if handle is not None:
                try:
                    synced = embed_missing_titles(max_items=INLINE_SYNC_MAX)["embedded"]
                except Exception as exc:  # noqa: BLE001
                    logger.warning("cnn10 embeddings: inline sync failed: %s", exc)
                finally:
                    _release(handle)

    vectors = _load_vectors_cached()
    if not vectors:
        raise ValueError("意味検索の準備ができていません。先に「意味検索を準備」を実行してください。")

    query_vec = _decode(_encode(_embed_texts(_client(), [query])[0]))
    episodes_by_id = {item["video_id"]: item for item in load_library()["episodes"]}
    scored = [
        (sum(map(mul, query_vec, vec)), video_id)
        for video_id, vec in vectors.items()
        if video_id in episodes_by_id
    ]
    scored.sort(reverse=True)

    results = []
    for score, video_id in scored[:limit]:
        item = episodes_by_id[video_id]
        results.append(
            {
                **item,
                "score": round(float(score), 4),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "thumbnail_url": cnn10.YOUTUBE_THUMBNAIL_URL.format(video_id=video_id),
            }
        )
    return {"query": query, "episodes": results, "synced": synced}
