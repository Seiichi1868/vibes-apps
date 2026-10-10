"""Debate app の表示設定（背景・透過率）の永続化。

GTECアプリの管理画面と同様の考え方だが、依存関係を持たせないよう完全に独立して実装する
（data/debate/settings.json に保存）。
"""
import json
import threading
import uuid
from copy import deepcopy
from pathlib import Path

from debate.config import (
    DATA_DIR,
    JUDGE_MODEL_OVERRIDE,
    POI_PROTECTED_SEC,
    POI_PROTECTED_SEC_MAX,
    POI_PROTECTED_SEC_MIN,
    POI_PROTECTED_SEC_STEP,
    ensure_dirs,
)
from debate.judge_models import (
    DEFAULT_JUDGE_MODEL_MODE,
    get_judge_model_options,
    resolve_judge_model_id,
    resolve_judge_model_mode,
)

_lock = threading.Lock()
SETTINGS_FILE = DATA_DIR / "settings.json"

BACKGROUND_PRESETS = {
    "meadow": {"label": "草原", "image": "debate/images/bg/debate-bg-meadow.jpg"},
    "forest": {"label": "森", "image": "debate/images/bg/debate-bg-forest.jpg"},
    "mountain": {"label": "山", "image": "debate/images/bg/debate-bg-mountain.jpg"},
    "ocean": {"label": "海", "image": "debate/images/bg/debate-bg-ocean.jpg"},
    "lake": {"label": "湖", "image": "debate/images/bg/debate-bg-lake.jpg"},
}

DEFAULT_BACKGROUND_ID = "forest"
DEFAULT_BACKGROUND_OPACITY = 0.32

TRANSCRIPTION_MODES = ("batch", "realtime")

DEFAULT_SETTINGS = {
    "background_id": DEFAULT_BACKGROUND_ID,
    "background_opacity": DEFAULT_BACKGROUND_OPACITY,
    "transcription_mode": "batch",
    "judge_model_mode": DEFAULT_JUDGE_MODEL_MODE,
    "opponent_model_mode": DEFAULT_JUDGE_MODEL_MODE,
    "poi_protected_start_sec": POI_PROTECTED_SEC,
    "poi_protected_end_sec": POI_PROTECTED_SEC,
    "affiliations": [],
}

MAX_AFFILIATION_NAME_LEN = 40
MAX_AFFILIATIONS = 50


def resolve_judge_model(mode: str | None = None) -> str:
    """管理画面で選択中のジャッジモデルIDを返す。DEBATE_JUDGE_MODEL があれば最優先。"""
    if JUDGE_MODEL_OVERRIDE:
        return JUDGE_MODEL_OVERRIDE
    selected = mode if mode in get_judge_model_options() else None
    if selected is None:
        stored = load_settings().get("judge_model_mode", DEFAULT_JUDGE_MODEL_MODE)
        selected = resolve_judge_model_mode(stored, fallback_mode=DEFAULT_JUDGE_MODEL_MODE)
    return resolve_judge_model_id(selected)


def resolve_opponent_model(mode: str | None = None) -> str:
    """Solo Practice の対戦AIモデル。選択肢はジャッジと同一（価格定義を再利用）。"""
    selected = mode if mode in get_judge_model_options() else None
    if selected is None:
        stored = load_settings().get("opponent_model_mode", DEFAULT_JUDGE_MODEL_MODE)
        selected = resolve_judge_model_mode(stored, fallback_mode=DEFAULT_JUDGE_MODEL_MODE)
    return resolve_judge_model_id(selected)


def clamp_poi_protected_sec(value, default: int = POI_PROTECTED_SEC) -> int:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        n = default
    step = POI_PROTECTED_SEC_STEP or 1
    n = int(round(n / step) * step)
    return max(POI_PROTECTED_SEC_MIN, min(POI_PROTECTED_SEC_MAX, n))


def format_poi_protected_label(sec) -> str:
    n = clamp_poi_protected_sec(sec)
    if n <= 0:
        return "無し"
    if n % 60 == 0:
        return f"{n // 60}分"
    if n > 60:
        return f"{n // 60}分{n % 60}秒"
    return f"{n}秒"


def poi_protected_hint_clause(start_sec, end_sec=None) -> str:
    start = clamp_poi_protected_sec(start_sec)
    end = start if end_sec is None else clamp_poi_protected_sec(end_sec)
    if start <= 0 and end <= 0:
        return "保護時間はありません。"
    if start > 0 and end > 0:
        if start == end:
            return f"最初と最後の{format_poi_protected_label(start)}は保護時間です。"
        return f"最初の{format_poi_protected_label(start)}と最後の{format_poi_protected_label(end)}は保護時間です。"
    if start > 0:
        return f"最初の{format_poi_protected_label(start)}は保護時間です。"
    return f"最後の{format_poi_protected_label(end)}は保護時間です。"


def poi_protected_intro_clause(start_sec, end_sec=None) -> str:
    start = clamp_poi_protected_sec(start_sec)
    end = start if end_sec is None else clamp_poi_protected_sec(end_sec)
    if start <= 0 and end <= 0:
        return "保護時間はなく、スピーチ中いつでも"
    if start > 0 and end > 0:
        if start == end:
            return f"最初と最後の{format_poi_protected_label(start)}を除き"
        return f"最初の{format_poi_protected_label(start)}と最後の{format_poi_protected_label(end)}を除き"
    if start > 0:
        return f"最初の{format_poi_protected_label(start)}を除き"
    return f"最後の{format_poi_protected_label(end)}を除き"


def resolve_poi_protected_times(raw: dict | None) -> tuple[int, int]:
    data = raw if isinstance(raw, dict) else {}
    legacy = None
    if "poi_protected_sec" in data:
        legacy = clamp_poi_protected_sec(data.get("poi_protected_sec"))
    start_default = POI_PROTECTED_SEC if legacy is None else legacy
    end_default = POI_PROTECTED_SEC if legacy is None else legacy
    start = (
        clamp_poi_protected_sec(data.get("poi_protected_start_sec"))
        if "poi_protected_start_sec" in data
        else start_default
    )
    end = (
        clamp_poi_protected_sec(data.get("poi_protected_end_sec"))
        if "poi_protected_end_sec" in data
        else end_default
    )
    return start, end


def _clamp_opacity(value, default: float = DEFAULT_BACKGROUND_OPACITY) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return round(max(0.0, min(n, 1.0)), 2)


def _normalize(raw: dict | None) -> dict:
    data = deepcopy(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return data

    bg_id = raw.get("background_id")
    if bg_id in BACKGROUND_PRESETS:
        data["background_id"] = bg_id

    if "background_opacity" in raw:
        data["background_opacity"] = _clamp_opacity(raw.get("background_opacity"))

    mode = raw.get("transcription_mode")
    if mode in TRANSCRIPTION_MODES:
        data["transcription_mode"] = mode

    judge_mode = raw.get("judge_model_mode")
    if judge_mode in get_judge_model_options():
        data["judge_model_mode"] = judge_mode
    elif judge_mode:
        data["judge_model_mode"] = DEFAULT_JUDGE_MODEL_MODE

    opponent_mode = raw.get("opponent_model_mode")
    if opponent_mode in get_judge_model_options():
        data["opponent_model_mode"] = opponent_mode
    elif opponent_mode:
        data["opponent_model_mode"] = DEFAULT_JUDGE_MODEL_MODE

    start_sec, end_sec = resolve_poi_protected_times(raw)
    data["poi_protected_start_sec"] = start_sec
    data["poi_protected_end_sec"] = end_sec
    data["affiliations"] = _normalize_affiliations(raw.get("affiliations"))

    return data


def resolve_background(background_id: str | None = None) -> dict:
    preset_id = background_id if background_id in BACKGROUND_PRESETS else DEFAULT_BACKGROUND_ID
    preset = BACKGROUND_PRESETS[preset_id]
    return {
        "background_id": preset_id,
        "background_label": preset["label"],
        "background_image": preset["image"],
    }


def load_settings() -> dict:
    ensure_dirs()
    with _lock:
        if not SETTINGS_FILE.is_file():
            return deepcopy(DEFAULT_SETTINGS)
        try:
            with SETTINGS_FILE.open(encoding="utf-8") as handle:
                return _normalize(json.load(handle))
        except (json.JSONDecodeError, OSError):
            return deepcopy(DEFAULT_SETTINGS)


def save_settings(data: dict) -> dict:
    ensure_dirs()
    normalized = _normalize(data)
    with _lock:
        with SETTINGS_FILE.open("w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
    return normalized


def update_settings(**kwargs) -> dict:
    current = load_settings()
    current.update(kwargs)
    return save_settings(current)


def public_settings() -> dict:
    settings = load_settings()
    return {**settings, **resolve_background(settings.get("background_id"))}


def _normalize_affiliation_name(name) -> str:
    return str(name or "").strip()[:MAX_AFFILIATION_NAME_LEN]


def _normalize_affiliations(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for item in raw[:MAX_AFFILIATIONS]:
        if isinstance(item, str):
            name = _normalize_affiliation_name(item)
            affiliation_id = ""
        elif isinstance(item, dict):
            name = _normalize_affiliation_name(item.get("name"))
            affiliation_id = str(item.get("id") or "").strip()
        else:
            continue
        if not name or name in seen_names:
            continue
        if not affiliation_id or affiliation_id in seen_ids:
            affiliation_id = str(uuid.uuid4())
        seen_ids.add(affiliation_id)
        seen_names.add(name)
        out.append({"id": affiliation_id, "name": name})
    return out


def list_affiliations() -> list[dict]:
    return list(load_settings().get("affiliations") or [])


def get_affiliation(affiliation_id: str) -> dict | None:
    wanted = str(affiliation_id or "").strip()
    if not wanted:
        return None
    for item in list_affiliations():
        if item.get("id") == wanted:
            return item
    return None


# 修正確認用。生徒向け所属の一番下に置く想定で、開始時だけ管理パスワードが要る。
UPDATE_CHECK_AFFILIATION_NAME = "アップデート確認用"


def affiliation_requires_admin(name) -> bool:
    return str(name or "").strip() == UPDATE_CHECK_AFFILIATION_NAME


def add_affiliation(name: str) -> tuple[list[dict], str | None]:
    cleaned = _normalize_affiliation_name(name)
    if not cleaned:
        return list_affiliations(), "所属名を入力してください。"
    current = list_affiliations()
    if len(current) >= MAX_AFFILIATIONS:
        return current, f"所属は{MAX_AFFILIATIONS}件までです。"
    if any(item.get("name") == cleaned for item in current):
        return current, "同じ名前の所属がすでにあります。"
    current.append({"id": str(uuid.uuid4()), "name": cleaned})
    return update_settings(affiliations=current)["affiliations"], None


def rename_affiliation(affiliation_id: str, name: str) -> tuple[list[dict], str | None]:
    cleaned = _normalize_affiliation_name(name)
    if not cleaned:
        return list_affiliations(), "所属名を入力してください。"
    wanted = str(affiliation_id or "").strip()
    current = list_affiliations()
    target = next((item for item in current if item.get("id") == wanted), None)
    if not target:
        return current, "所属が見つかりません。"
    if any(item.get("id") != wanted and item.get("name") == cleaned for item in current):
        return current, "同じ名前の所属がすでにあります。"
    target["name"] = cleaned
    return update_settings(affiliations=current)["affiliations"], None


def delete_affiliation(affiliation_id: str) -> tuple[list[dict], str | None]:
    wanted = str(affiliation_id or "").strip()
    current = list_affiliations()
    next_items = [item for item in current if item.get("id") != wanted]
    if len(next_items) == len(current):
        return current, "所属が見つかりません。"
    return update_settings(affiliations=next_items)["affiliations"], None
