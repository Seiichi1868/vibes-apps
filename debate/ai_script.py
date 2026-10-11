"""観戦用お手本スクリプトの生成と検証。

役割文・定型ガイドは debate/config.py の PART_ROLES / PART_GUIDES をそのまま埋める。
ソロの opponent.py は呼ばない。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time

from debate.config import PART_DEFS, PART_GUIDES, PART_ORDER, PART_ROLES

logger = logging.getLogger(__name__)

SCRIPT_TIMEOUT_SEC = float(os.environ.get("DEBATE_SCRIPT_TIMEOUT_SEC", "240"))
SCRIPT_MAX_RETRIES = int(os.environ.get("DEBATE_SCRIPT_MAX_RETRIES", "0"))

LEVELS = ("easy", "normal", "hard")
WINNERS = ("Gov", "Opp")
POINT_IDS = {
    "Gov": ("gov_1", "gov_2"),
    "Opp": ("opp_1", "opp_2"),
}
ARGUMENT_STATUSES = {"standing", "knocked_down", "extended"}

LEVEL_SPECS = {
    "easy": {
        "constructive": (220, 280),
        "reply": (150, 190),
        "sentence_rule": "Keep most sentences to 15 words or fewer.",
        "level_rules": "CEFR A2–B1. Short sentences. Everyday school words. Default playback 0.75x.",
    },
    "normal": {
        "constructive": (330, 400),
        "reply": (220, 270),
        "sentence_rule": "Keep most sentences to 22 words or fewer.",
        "level_rules": "CEFR B1–B2. Clear classroom English. Default playback 1.0x.",
    },
    "hard": {
        "constructive": (430, 480),
        "reply": (300, 340),
        "sentence_rule": "Use natural sentence length for a fluent debate speech.",
        "level_rules": "CEFR B2 or above. Natural debate English. Default playback 1.0x.",
    },
}

CONSTRUCTIVE_PARTS = {"PM", "LO", "MG", "MO"}
REPLY_PARTS = {"LOR", "PMR"}


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def text_hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def word_range_for(part: str, level: str) -> tuple[int, int]:
    spec = LEVEL_SPECS[level]
    if part in REPLY_PARTS:
        return spec["reply"]
    return spec["constructive"]


def _roles_block() -> str:
    lines = []
    for part in PART_ORDER:
        side = PART_DEFS[part]["side"]
        lines.append(f"- {part} ({side}): {PART_ROLES[part]}")
    return "\n".join(lines)


def _guides_block() -> str:
    lines = []
    for part in PART_ORDER:
        lines.append(f"- {part}: {PART_GUIDES[part]}")
    return "\n".join(lines)


def _word_ranges_text(level: str) -> str:
    spec = LEVEL_SPECS[level]
    c_low, c_high = spec["constructive"]
    r_low, r_high = spec["reply"]
    return f"PM, LO, MG, MO: {c_low}-{c_high} words each. LOR, PMR: {r_low}-{r_high} words each."


def build_script_prompt(motion: str, level: str, intended_winner: str) -> str:
    winner_line = intended_winner if intended_winner in WINNERS else "Choose either Gov or Opp, whichever can win clearly but fairly, and set intended_winner to that side."
    spec = LEVEL_SPECS[level]
    return f"""You are an expert English debate coach writing a MODEL SCRIPT for a classroom parliamentary debate (six speeches) for Japanese high-school students.

MOTION: {motion}
LEVEL: {level}  ({spec["level_rules"]})
INTENDED WINNER: {winner_line}

# Structure
Each side has exactly two points (Point 1 and Point 2). No other arguments may appear.
Speech order and roles (follow these exactly):
{_roles_block()}
Begin each speech with, and use throughout, the signpost templates below (verbatim):
{_guides_block()}

# Rules
- Rebuttals must respond to what the previous speaker ACTUALLY said: "They said ... However ... Therefore ...". Reconstruct before rebutting where the role requires it.
- LOR and PMR introduce NO new arguments.
- Do NOT invent statistics, study names, institutions, quotations, or named experts. Do not write "studies show" or "research shows". Argue with logic and concrete everyday school-life examples instead.
- The intended winner's points should remain standing at the end. The other side should lose at least one point through a rebuttal that goes unanswered. Keep the debate plausible and fair: both sides argue well; the result is clear but not a blowout.
- Write for the ear: plain text only, no markdown, bullets, parentheses, emoji, or abbreviations.
- Word counts per speech: {_word_ranges_text(level)}. Sentence length: {spec["sentence_rule"]}.
- Before you output JSON, count the words in each speech and rewrite any speech that is outside its range.

# Output
JSON only, no preface. Keys in this order (plan first, then write):
motion, intended_winner, points, argument_map, parts, summary_ja
- points: Gov and Opp, each a list of two objects {{id, summary_ja, summary_en}}. ids must be gov_1, gov_2, opp_1, opp_2.
- argument_map: one object per point id, with id, side, raised_in, status (standing, knocked_down, or extended), history (list of {{part, action}}).
  Actions should be raised, rebutted, defended, or extended. summary is a short Japanese label for the point.
- parts: 6 items in order PM, LO, MG, MO, LOR, PMR, each {{part, side, text, signpost_phrases, key_point_ja}}
  - signpost_phrases: exact substrings of text that are signpost expressions
  - key_point_ja: Japanese, 40 characters or fewer, what this speech does
- summary_ja: Japanese, 200 characters or fewer, why the intended winner won, described in terms of which points stood or fell.
- intended_winner must be exactly Gov or Opp.
"""


def _get_client():
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAI(api_key=api_key, timeout=SCRIPT_TIMEOUT_SEC, max_retries=SCRIPT_MAX_RETRIES)


def _is_reasoning_model(model: str) -> bool:
    name = (model or "").strip().lower()
    if name.startswith("gpt-5") and "chat" not in name:
        return True
    return name.startswith(("o1", "o3", "o4"))


def _parse_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("生成結果がJSONオブジェクトではありません。")
    return data


def _extract_text(completion) -> str:
    if not completion.choices:
        return ""
    content = getattr(completion.choices[0].message, "content", None)
    if isinstance(content, list):
        chunks = []
        for part in content:
            if isinstance(part, dict):
                chunks.append(str(part.get("text") or ""))
            else:
                chunks.append(str(getattr(part, "text", "") or part))
        content = "".join(chunks)
    return (content or "").strip()


def _usage_cost_usd(completion, model_mode: str) -> float:
    from debate.judge_models import resolve_judge_model_metadata

    usage = getattr(completion, "usage", None)
    if usage is None:
        return 0.0
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    meta = resolve_judge_model_metadata(model_mode)
    cost = (
        prompt_tokens * float(meta["input_price_per_1m"]) / 1_000_000
        + completion_tokens * float(meta["output_price_per_1m"]) / 1_000_000
    )
    return round(cost, 6)


def _clean_speech_text(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").strip()
    cleaned = cleaned.replace("*", "")
    return cleaned.strip()


def validate_generated(data: dict, level: str) -> tuple[dict, list[str], list[str]]:
    """生成JSONを検証し、(正規化済み中身, 致命的エラー, 警告) を返す。"""
    fatal: list[str] = []
    warnings: list[str] = []
    if level not in LEVEL_SPECS:
        fatal.append("レベルが不正です。")
        return {}, fatal, warnings

    winner = str(data.get("intended_winner") or "").strip()
    if winner not in WINNERS:
        fatal.append("優勢側（intended_winner）が Gov / Opp になっていません。")

    points = _normalize_points(data.get("points"), fatal)
    argument_map = _normalize_argument_map(data.get("argument_map"), points, fatal)
    if winner in WINNERS and not fatal:
        _check_winner_balance(argument_map, winner, fatal)

    parts = _normalize_parts(data.get("parts"), level, warnings, fatal)
    summary = str(data.get("summary_ja") or "").strip()
    if len(summary) > 200:
        warnings.append(f"全体解説が200字を超えています（{len(summary)}字）。")

    normalized = {
        "intended_winner": winner if winner in WINNERS else "",
        "points": points,
        "argument_map": argument_map,
        "parts": parts,
        "summary_ja": summary,
    }
    return normalized, fatal, warnings


def _normalize_points(raw, fatal: list[str]) -> dict:
    points = {"Gov": [], "Opp": []}
    if not isinstance(raw, dict):
        fatal.append("points がありません。")
        return points
    seen = set()
    for side, ids in POINT_IDS.items():
        items = raw.get(side)
        if not isinstance(items, list):
            fatal.append(f"{side} の論点がありません。")
            continue
        by_id = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            point_id = str(item.get("id") or "").strip()
            if point_id in ids:
                by_id[point_id] = {
                    "id": point_id,
                    "summary_ja": str(item.get("summary_ja") or "").strip(),
                    "summary_en": str(item.get("summary_en") or "").strip(),
                }
        for point_id in ids:
            if point_id not in by_id:
                fatal.append(f"論点 {point_id} がありません。")
            else:
                points[side].append(by_id[point_id])
                seen.add(point_id)
    return points


def _point_lookup(points: dict) -> dict[str, dict]:
    found = {}
    for side in ("Gov", "Opp"):
        for item in points.get(side) or []:
            found[item["id"]] = {**item, "side": side}
    return found


def _normalize_argument_map(raw, points: dict, fatal: list[str]) -> list:
    lookup = _point_lookup(points)
    if not isinstance(raw, list):
        fatal.append("argument_map がありません。")
        return []
    normalized = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        point_id = str(item.get("id") or item.get("argument_id") or "").strip()
        if point_id not in lookup:
            fatal.append(f"argument_map の id「{point_id or '空'}」が points にありません。")
            continue
        if point_id in seen:
            continue
        seen.add(point_id)
        side = lookup[point_id]["side"]
        status = str(item.get("status") or "").strip()
        if status not in ARGUMENT_STATUSES:
            fatal.append(f"{point_id} の status が不正です。")
            status = "standing"
        raised = str(item.get("raised_in") or item.get("raised_in_part") or "").strip()
        if raised not in PART_ORDER:
            fatal.append(f"{point_id} の提示パートが不正です。")
            raised = ""
        history = []
        for entry in item.get("history") or []:
            if not isinstance(entry, dict):
                continue
            part = str(entry.get("part") or "").strip()
            action = str(entry.get("action") or "").strip()
            if part in PART_ORDER and action:
                history.append({"part": part, "action": action})
        summary = str(item.get("summary") or lookup[point_id].get("summary_ja") or "").strip()
        normalized.append(
            {
                "id": point_id,
                "argument_id": point_id,
                "side": side,
                "raised_in": raised,
                "raised_in_part": raised,
                "status": status,
                "summary": summary,
                "history": history,
            }
        )
    for point_id in ("gov_1", "gov_2", "opp_1", "opp_2"):
        if point_id not in seen and point_id in lookup:
            fatal.append(f"argument_map に {point_id} がありません。")
    return normalized


def _check_winner_balance(argument_map: list, winner: str, fatal: list[str]) -> None:
    counts = {"Gov": 0, "Opp": 0}
    for item in argument_map:
        if item.get("status") in ("standing", "extended"):
            side = item.get("side")
            if side in counts:
                counts[side] += 1
    loser = "Opp" if winner == "Gov" else "Gov"
    if counts[winner] <= counts[loser]:
        fatal.append(
            f"優勢側 {winner} の残っている論点（{counts[winner]}）が相手（{counts[loser]}）より多くありません。"
        )


def _normalize_parts(raw, level: str, warnings: list[str], fatal: list[str]) -> list:
    if not isinstance(raw, list) or len(raw) != 6:
        fatal.append("parts が6つありません。")
        raw_items = raw if isinstance(raw, list) else []
    else:
        raw_items = raw
    by_part = {}
    for item in raw_items:
        if isinstance(item, dict):
            by_part[str(item.get("part") or "").strip()] = item
    parts = []
    for part in PART_ORDER:
        item = by_part.get(part)
        expected_side = PART_DEFS[part]["side"]
        if not isinstance(item, dict):
            fatal.append(f"{part} がありません。")
            continue
        side = str(item.get("side") or "").strip()
        if side != expected_side:
            fatal.append(f"{part} の陣営が {expected_side} ではありません。")
            side = expected_side
        text = _clean_speech_text(str(item.get("text") or ""))
        if not text:
            fatal.append(f"{part} の英文が空です。")
        phrases = []
        for phrase in item.get("signpost_phrases") or []:
            snippet = str(phrase or "").strip()
            if snippet and snippet in text:
                phrases.append(snippet)
        key_point = str(item.get("key_point_ja") or "").strip()
        if len(key_point) > 40:
            warnings.append(f"{part}: 日本語ポイントが40字を超えています（{len(key_point)}字）。")
        count = word_count(text)
        low, high = word_range_for(part, level)
        if text and (count < low or count > high):
            warnings.append(f"{part}: 語数が範囲外です（{count}語。目安 {low}–{high}）。")
        digest = text_hash(text)
        parts.append(
            {
                "part": part,
                "side": side,
                "text": text,
                "signpost_phrases": phrases,
                "key_point_ja": key_point,
                "word_count": count,
                "text_hash": digest,
                "audio": {"status": "none", "text_hash": ""},
            }
        )
    if [item["part"] for item in parts] != list(PART_ORDER):
        fatal.append("パートの順序が PM→LO→MG→MO→LOR→PMR になっていません。")
    return parts


def generate_model_script(motion: str, level: str, intended_winner: str, model_mode: str) -> dict:
    """1回生成し、致命的不備ならもう1回だけ再生成する。成功時は保存用フィールドを返す。"""
    client = _get_client()
    if not client:
        raise RuntimeError("OPENAI_API_KEYが設定されていないため、スクリプトを生成できません。")

    from debate.judge_models import resolve_judge_model_id, resolve_judge_model_mode

    selected_mode = resolve_judge_model_mode(model_mode, fallback_mode="5.6-terra")
    model = resolve_judge_model_id(selected_mode)
    prompt = build_script_prompt(motion, level, intended_winner)
    messages = [{"role": "user", "content": prompt}]
    total_cost = 0.0
    last_fatal: list[str] = []

    for attempt in range(2):
        kwargs: dict = {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": messages,
        }
        if not _is_reasoning_model(model):
            kwargs["temperature"] = 0.4
        started = time.monotonic()
        try:
            completion = client.chat.completions.create(**kwargs)
        except Exception as exc:
            elapsed = time.monotonic() - started
            logger.warning(
                "Script request failed after %.1fs (model=%s attempt=%s): %s",
                elapsed,
                model,
                attempt + 1,
                exc,
            )
            last_fatal = [f"生成APIが失敗しました（{exc}）。"]
            if attempt == 0:
                messages = [
                    {"role": "user", "content": prompt},
                    {"role": "user", "content": "The previous request failed. Return the JSON script now."},
                ]
                continue
            break
        total_cost += _usage_cost_usd(completion, selected_mode)
        elapsed = time.monotonic() - started
        raw = _extract_text(completion)
        logger.info("Script finished in %.1fs (model=%s attempt=%s)", elapsed, model, attempt + 1)
        try:
            data = _parse_json_object(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            last_fatal = [f"JSONとして読めませんでした（{exc}）。"]
            messages = _retry_messages(prompt, last_fatal)
            continue
        normalized, fatal, warnings = validate_generated(data, level)
        if not fatal:
            normalized["script_model"] = model
            normalized["gen_cost_usd"] = round(total_cost, 6)
            normalized["warnings"] = warnings
            return normalized
        last_fatal = fatal
        logger.info("Script validation failed (attempt=%s): %s", attempt + 1, "; ".join(fatal))
        messages = _retry_messages(prompt, fatal)

    raise ValueError(" / ".join(last_fatal) or "スクリプトを生成できませんでした。")


def _retry_messages(prompt: str, fatal: list[str]) -> list[dict]:
    reason = "\n".join(f"- {item}" for item in fatal)
    return [
        {"role": "user", "content": prompt},
        {
            "role": "user",
            "content": (
                "The previous JSON failed these checks. Regenerate the full JSON and fix only these problems:\n"
                f"{reason}"
            ),
        },
    ]


def apply_part_text(part: dict, text: str, level: str) -> tuple[dict, str | None]:
    """本文編集後のパート。語数警告があれば返す。音声ハッシュは残し、古さは呼び出し側で見る。"""
    cleaned = _clean_speech_text(text)
    phrases = [phrase for phrase in (part.get("signpost_phrases") or []) if phrase and phrase in cleaned]
    updated = dict(part)
    updated["text"] = cleaned
    updated["signpost_phrases"] = phrases
    updated["word_count"] = word_count(cleaned)
    updated["text_hash"] = text_hash(cleaned)
    audio = dict(updated.get("audio") or {})
    audio.setdefault("status", "none")
    audio.setdefault("text_hash", "")
    updated["audio"] = audio
    low, high = word_range_for(updated.get("part") or "PM", level if level in LEVEL_SPECS else "normal")
    warning = None
    count = updated["word_count"]
    if cleaned and (count < low or count > high):
        warning = f"{updated.get('part')}: 語数が範囲外です（{count}語。目安 {low}–{high}）。"
    return updated, warning
