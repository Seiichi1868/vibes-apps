"""お題の埋め込みインデックス。保存先は data/toolbox。"""
from __future__ import annotations

from array import array
import base64
import logging
import math
import threading

from toolbox.config import MINUTE_SPEECH_EMBEDDINGS_FILE
from toolbox.pricing import estimate_embed_usd
from toolbox.storage import _read_json, _write_json, get_setting, now_iso
from toolbox.tools.minute_speech.topics import content_hash, embed_document, merged_topics
from toolbox.usage import UsageError, UsageLimitError, embed_texts, selected_model

logger = logging.getLogger(__name__)

EMBED_DIM = 256
TOOL_ID = "minute-speech"
_lock = threading.Lock()
_job = {"running": False, "done": 0, "total": 0, "error": "", "kind": ""}
_query_cache: dict = {"key": "", "vec": None}


def _encode(values: list[float]) -> str:
    raw = array("f", (float(value) for value in values))
    return base64.b64encode(raw.tobytes()).decode("ascii")


def _decode(raw: str) -> list[float]:
    values = array("f")
    values.frombytes(base64.b64decode(raw))
    return list(values)


def load_index() -> dict:
    data = _read_json(MINUTE_SPEECH_EMBEDDINGS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    items = data.get("items")
    data["items"] = items if isinstance(items, dict) else {}
    return data


def _save_index(data: dict) -> None:
    _write_json(MINUTE_SPEECH_EMBEDDINGS_FILE, data)


def _stale_topics() -> list[dict]:
    index = load_index()
    model = ""
    try:
        model = selected_model("embed")
    except UsageError:
        model = str(get_setting("embed_model") or "")
    items = index.get("items") or {}
    same_model = index.get("model") == model and int(index.get("dim") or 0) == EMBED_DIM
    stale = []
    for topic in merged_topics():
        digest = content_hash(topic)
        stored = items.get(topic["id"]) if same_model else None
        if not isinstance(stored, dict) or stored.get("hash") != digest or not stored.get("vector"):
            stale.append(topic)
    return stale


def index_status() -> dict:
    topics = merged_topics()
    index = load_index()
    stale = _stale_topics()
    includes_ja = any((topic.get("ja") or "").strip() for topic in topics if topic["id"] in (index.get("items") or {}))
    return {
        "ready": len(index.get("items") or {}) > 0,
        "count": len(index.get("items") or {}),
        "topic_count": len(topics),
        "stale": len(stale),
        "model": index.get("model"),
        "dim": index.get("dim"),
        "updated_at": index.get("updated_at"),
        "includes_ja": includes_ja,
        "running": _job["running"],
        "done": _job["done"],
        "total": _job["total"],
        "error": _job["error"],
    }


def index_estimate() -> dict:
    stale = _stale_topics()
    try:
        model_id = selected_model("embed")
    except UsageError as exc:
        return {"count": len(stale), "est_cost_usd": None, "error": exc.message, "model": None}
    tokens = len(stale) * 90
    cost = estimate_embed_usd(model_id, tokens)
    search_cost = estimate_embed_usd(model_id, 40)
    return {
        "count": len(stale),
        "tokens": tokens,
        "model": model_id,
        "est_cost_usd": None if cost is None else round(cost, 4),
        "search_est_usd": None if search_cost is None else round(search_cost, 6),
        "dim": EMBED_DIM,
    }


def _run(user_id: str) -> None:
    try:
        stale = _stale_topics()
        _job["total"] = len(stale)
        _job["done"] = 0
        index = load_index()
        model_id = selected_model("embed")
        index["model"] = model_id
        index["dim"] = EMBED_DIM
        items = dict(index.get("items") or {})
        for start in range(0, len(stale), 100):
            batch = stale[start:start + 100]
            vectors = embed_texts(
                texts=[embed_document(topic) for topic in batch],
                user_id=user_id,
                tool_id=TOOL_ID,
                dimensions=EMBED_DIM,
            )
            for topic, vector in zip(batch, vectors):
                items[topic["id"]] = {"hash": content_hash(topic), "vector": _encode(vector)}
            index["items"] = items
            index["updated_at"] = now_iso()
            _save_index(index)
            _job["done"] = min(len(stale), start + len(batch))
        _query_cache["key"] = ""
        _query_cache["vec"] = None
    except (UsageError, UsageLimitError) as exc:
        _job["error"] = exc.message
        logger.warning("minute speech embed stopped: %s", exc)
    except Exception as exc:
        _job["error"] = "インデックスの作成に失敗しました。"
        logger.exception("minute speech embed failed: %s", exc)
    finally:
        _job["running"] = False


def start_index(user_id: str) -> dict:
    with _lock:
        if _job["running"]:
            return {"started": False, **index_status()}
        _job.update({"running": True, "done": 0, "total": 0, "error": "", "kind": "embed"})
    threading.Thread(target=_run, args=(user_id,), daemon=True).start()
    return {"started": True, **index_status()}


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / math.sqrt(left_norm * right_norm)


def query_vector(query: str, user_id: str) -> list[float]:
    model_id = selected_model("embed")
    key = f"{model_id}:{EMBED_DIM}:{query}"
    if _query_cache["key"] == key and _query_cache["vec"] is not None:
        return _query_cache["vec"]
    vector = embed_texts(texts=[query], user_id=user_id, tool_id=TOOL_ID, dimensions=EMBED_DIM)[0]
    _query_cache["key"] = key
    _query_cache["vec"] = vector
    return vector


def indexed_vectors() -> dict[str, list[float]]:
    index = load_index()
    rows = {}
    for topic_id, item in (index.get("items") or {}).items():
        if isinstance(item, dict) and item.get("vector"):
            try:
                rows[topic_id] = _decode(item["vector"])
            except Exception:
                continue
    return rows


def index_includes_ja() -> bool:
    index = load_index()
    by_id = {topic["id"]: topic for topic in merged_topics()}
    for topic_id, item in (index.get("items") or {}).items():
        topic = by_id.get(topic_id)
        if topic and (topic.get("ja") or "").strip() and isinstance(item, dict) and item.get("hash") == content_hash(topic):
            return True
    return False
