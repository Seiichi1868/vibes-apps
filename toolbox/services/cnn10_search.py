"""News Talk 用の CNN10 タイトル検索。保存先は data/toolbox だけ。"""
from __future__ import annotations

from array import array
import base64
from datetime import datetime, timezone
import json
import logging
import math
import threading
import time
import urllib.request

from toolbox.config import DATA_DIR, get_openai_api_key
from toolbox.openai_http import OpenAIHttpError, _ssl_context
from toolbox.services.cnn10 import fetch_cnn10_episodes, reset_episode_cache

logger = logging.getLogger(__name__)

LIBRARY_FILE = DATA_DIR / "cnn10_library.json"
EMBEDDINGS_FILE = DATA_DIR / "cnn10_library_embeddings.json"
JOB_FILE = DATA_DIR / "cnn10_library_job.json"
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 512

_lock = threading.Lock()
_jobs = {"library": False, "embed": False}
_vector_cache = {"mtime": None, "vectors": {}}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read(path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(path, payload: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_library() -> dict:
    data = _read(LIBRARY_FILE)
    episodes = data.get("episodes") if isinstance(data.get("episodes"), list) else []
    return {
        "updated_at": data.get("updated_at") or "",
        "episodes": [item for item in episodes if isinstance(item, dict) and item.get("video_id")],
    }


def library_status() -> dict:
    library = load_library()
    job = _read(JOB_FILE)
    return {
        "count": len(library["episodes"]),
        "updated_at": library["updated_at"],
        "running": _jobs["library"],
        "job": job,
    }


def _slim(episode: dict) -> dict:
    return {
        "video_id": episode.get("video_id") or "",
        "title": episode.get("title") or "Untitled",
        "published": episode.get("published") or "",
        "url": episode.get("url") or "",
        "thumbnail_url": episode.get("thumbnail_url") or "",
    }


def _run_update(mode: str) -> None:
    job = {"running": True, "mode": mode, "pages": 0, "added": 0, "started_at": _now()}
    _write(JOB_FILE, job)
    try:
        if mode == "full":
            reset_episode_cache()
        known = set() if mode == "full" else {item["video_id"] for item in load_library()["episodes"]}
        found: list[dict] = []
        offset = 0
        for _page in range(300):
            data = fetch_cnn10_episodes(offset=offset, limit=30)
            batch = data.get("episodes") or []
            job["pages"] = _page + 1
            fresh = [_slim(item) for item in batch if item.get("video_id") and item["video_id"] not in known]
            if mode != "full" and batch and not fresh:
                break
            for item in fresh:
                known.add(item["video_id"])
                found.append(item)
            job["added"] = len(found)
            _write(JOB_FILE, job)
            if not data.get("has_more"):
                break
            offset = int(data.get("next_offset") or offset + len(batch))
            time.sleep(0.25)
        current = [] if mode == "full" else load_library()["episodes"]
        merged = {item["video_id"]: item for item in current}
        for item in found:
            merged[item["video_id"]] = item
        _write(LIBRARY_FILE, {"updated_at": _now(), "episodes": list(merged.values())})
        job["error"] = ""
    except Exception as exc:
        logger.exception("toolbox cnn10 library update failed")
        job["error"] = str(exc)
    finally:
        job["running"] = False
        job["finished_at"] = _now()
        _write(JOB_FILE, job)
        _jobs["library"] = False


def start_library_update(mode: str = "diff") -> dict:
    mode = "full" if mode == "full" else "diff"
    with _lock:
        if _jobs["library"]:
            return {"started": False, **library_status()}
        _jobs["library"] = True
    threading.Thread(target=_run_update, args=(mode,), daemon=True).start()
    return {"started": True, **library_status()}


def search_titles(query: str, limit: int = 50) -> dict:
    terms = [part.casefold() for part in str(query or "").split() if part.strip()]
    limit = max(1, min(int(limit or 50), 100))
    if not terms:
        return {"query": query, "total": 0, "episodes": []}
    matches = [
        item for item in load_library()["episodes"]
        if all(term in str(item.get("title") or "").casefold() for term in terms)
    ]
    matches.sort(key=lambda item: str(item.get("published") or ""), reverse=True)
    return {"query": query, "total": len(matches), "episodes": matches[:limit]}


def _encode(vector: list[float]) -> str:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    packed = array("f", (value / norm for value in vector))
    return base64.b64encode(packed.tobytes()).decode("ascii")


def _decode(raw: str) -> array:
    values = array("f")
    values.frombytes(base64.b64decode(raw))
    return values


def _vectors() -> dict[str, str]:
    data = _read(EMBEDDINGS_FILE)
    raw = data.get("vectors")
    return raw if isinstance(raw, dict) else {}


def embedding_status() -> dict:
    episodes = load_library()["episodes"]
    vectors = _vectors()
    embedded = sum(1 for item in episodes if item["video_id"] in vectors)
    years = sorted({str(item.get("published") or "")[:4] for item in episodes if str(item.get("published") or "")[:4].isdigit()}, reverse=True)
    return {
        "library_count": len(episodes),
        "embedded_count": embedded,
        "missing_count": len(episodes) - embedded,
        "ready": embedded > 0,
        "running": _jobs["embed"],
        "years": [int(year) for year in years],
    }


def _embed(texts: list[str]) -> list[list[float]]:
    api_key = get_openai_api_key()
    if not api_key:
        raise OpenAIHttpError("OpenAI の API キーが設定されていません。")
    payload = json.dumps({
        "model": EMBED_MODEL,
        "input": texts,
        "dimensions": EMBED_DIM,
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60, context=_ssl_context()) as response:
        data = json.loads(response.read().decode("utf-8"))
    ordered = sorted(data.get("data") or [], key=lambda item: item.get("index") or 0)
    return [item["embedding"] for item in ordered]


def _run_embed() -> None:
    try:
        vectors = _vectors()
        missing = [item for item in load_library()["episodes"] if item["video_id"] not in vectors]
        for start in range(0, len(missing), 50):
            batch = missing[start:start + 50]
            embedded = _embed([str(item.get("title") or "Untitled") for item in batch])
            for item, vector in zip(batch, embedded):
                vectors[item["video_id"]] = _encode(vector)
            _write(EMBEDDINGS_FILE, {"model": EMBED_MODEL, "updated_at": _now(), "vectors": vectors})
            time.sleep(0.2)
    except Exception:
        logger.exception("toolbox cnn10 embeddings failed")
    finally:
        _jobs["embed"] = False
        _vector_cache["mtime"] = None


def start_embeddings() -> dict:
    if not get_openai_api_key():
        raise OpenAIHttpError("OpenAI の API キーが設定されていません。")
    with _lock:
        if _jobs["embed"]:
            return {"started": False, **embedding_status()}
        _jobs["embed"] = True
    threading.Thread(target=_run_embed, daemon=True).start()
    return {"started": True, **embedding_status()}


def _loaded_vectors() -> dict[str, array]:
    try:
        mtime = EMBEDDINGS_FILE.stat().st_mtime
    except OSError:
        return {}
    if _vector_cache["mtime"] != mtime:
        _vector_cache["vectors"] = {key: _decode(value) for key, value in _vectors().items()}
        _vector_cache["mtime"] = mtime
    return _vector_cache["vectors"]


def semantic_search(query: str, limit: int = 10, since_year: int | None = None) -> dict:
    query = str(query or "").strip()
    limit = max(1, min(int(limit or 10), 30))
    vectors = _loaded_vectors()
    if not query:
        return {"query": query, "episodes": [], "since_year": since_year}
    if not vectors:
        raise OpenAIHttpError("AI検索の準備ができていません。先に「AI検索を準備」を押してください。")
    query_vec = _decode(_encode(_embed([query])[0]))

    def included(item: dict) -> bool:
        if since_year is None:
            return True
        year = str(item.get("published") or "")[:4]
        return year.isdigit() and int(year) >= since_year

    episodes = {
        item["video_id"]: item
        for item in load_library()["episodes"]
        if included(item)
    }
    scored = []
    for video_id, vector in vectors.items():
        item = episodes.get(video_id)
        if not item:
            continue
        score = sum(left * right for left, right in zip(query_vec, vector))
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = []
    for score, item in scored[:limit]:
        results.append({**item, "score": round(float(score), 4)})
    return {"query": query, "episodes": results, "since_year": since_year}
