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

from debate.config import (
    ARGUMENT_STATUS,
    HISTORY_ACTION,
    PART_DEFS,
    PART_GUIDES,
    PART_ORDER,
    PART_ROLES,
    SCRIPT_LEVEL_WORD_RANGES,
    SCRIPT_WINNER_MARGIN_MAX,
    SCRIPT_WINNER_MARGIN_MIN,
    SCRIPT_WORDS_PER_MINUTE,
    argument_status_rules_text,
    format_score_total,
    side_score_totals,
)

logger = logging.getLogger(__name__)

SCRIPT_TIMEOUT_SEC = float(os.environ.get("DEBATE_SCRIPT_TIMEOUT_SEC", "240"))
SCRIPT_MAX_RETRIES = int(os.environ.get("DEBATE_SCRIPT_MAX_RETRIES", "0"))

LEVELS = ("easy", "normal", "hard")
WINNERS = ("Gov", "Opp")
POINT_IDS = {
    "Gov": ("gov_1", "gov_2"),
    "Opp": ("opp_1", "opp_2"),
}
_LEVEL_STYLE = {
    "easy": {
        "sentence_rule": "Keep most sentences to 15 words or fewer.",
        "level_rules": "CEFR A2–B1. Short sentences. Everyday school words. Default playback 0.75x.",
    },
    "normal": {
        "sentence_rule": "Keep most sentences to 22 words or fewer.",
        "level_rules": "CEFR B1–B2. Clear classroom English. Default playback 1.0x.",
    },
    "hard": {
        "sentence_rule": "Use natural sentence length for a fluent debate speech.",
        "level_rules": "CEFR B2 or above. Natural debate English. Default playback 1.0x.",
    },
}
LEVEL_SPECS = {
    level: {**style, **SCRIPT_LEVEL_WORD_RANGES[level]} for level, style in _LEVEL_STYLE.items()
}

_FABRICATION_PATTERNS = (
    (re.compile(r"\d+(?:\.\d+)?\s*%"), "%"),
    (re.compile(r"\bstudies\b", re.I), "studies"),
    (re.compile(r"\bresearch\b", re.I), "research"),
    (re.compile(r"\bsurvey\b", re.I), "survey"),
    (re.compile(r"\baccording to\b", re.I), "according to"),
    (re.compile(r"\bexperts\b", re.I), "experts"),
)

CONSTRUCTIVE_PARTS = {"PM", "LO", "MG", "MO"}
REPLY_PARTS = {"LOR", "PMR"}


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def make_warning(message: str, severity: str) -> dict:
    return {"severity": "strong" if severity == "strong" else "weak", "message": message}


def warning_message(item) -> str:
    if isinstance(item, dict):
        return str(item.get("message") or "")
    return str(item)


def normalize_warning(item) -> dict:
    if isinstance(item, dict):
        severity = "strong" if item.get("severity") == "strong" else "weak"
        return {"severity": severity, "message": str(item.get("message") or "")}
    text = str(item)
    strong = any(token in text for token in ("制限", "優勢差", "架空"))
    return {"severity": "strong" if strong else "weak", "message": text}


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
- Plan the argument_map so the intended winner's total weight is {SCRIPT_WINNER_MARGIN_MIN} to {SCRIPT_WINNER_MARGIN_MAX} higher than the other side. Avoid a gap of 1.5 or more. Both sides should still argue well.
- A point may be weakened or collapsed only when a speech in this script actually reaches that point's reason and the owning side does not fully answer it. Do not exaggerate the rebuttal. The speeches and the statuses must describe the same debate.
- Follow this judgment procedure exactly:
{argument_status_rules_text()}
- Write for the ear: plain text only, no markdown, bullets, parentheses, emoji, or abbreviations.
- Word counts per speech: {_word_ranges_text(level)}. Sentence length: {spec["sentence_rule"]}.
- Before you output JSON, count the words in each speech and rewrite any speech that is outside its range.

# Output
JSON only, no preface. Keys in this order (plan first, then write):
motion, intended_winner, points, argument_map, parts, summary_ja
- points: Gov and Opp, each a list of two objects {{id, summary_ja, summary_en}}. ids must be gov_1, gov_2, opp_1, opp_2.
- argument_map: one object per point id, with id, side, raised_in, status (intact, weakened, or collapsed only), reason_ja (Japanese, one sentence, 60 characters or fewer), history (list of {{part, action}}).
  Actions are raised, rebutted, defended, or extended. extended is an action, never a status.
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


def validate_generated(data: dict, level: str) -> tuple[dict, list[str], list[dict], str]:
    """生成JSONを検証し、(正規化済み, 致命的エラー, 警告, 優勢差の問題) を返す。

    優勢差が外れていても致命的にはしない。呼び出し側が1回再生成し、だめなら警告付きで残す。
    """
    fatal: list[str] = []
    warnings: list[dict] = []
    if level not in LEVEL_SPECS:
        fatal.append("レベルが不正です。")
        return {}, fatal, warnings, ""

    winner = str(data.get("intended_winner") or "").strip()
    if winner not in WINNERS:
        fatal.append("優勢側（intended_winner）が Gov / Opp になっていません。")

    points = _normalize_points(data.get("points"), fatal)
    argument_map = _normalize_argument_map(data.get("argument_map"), points, fatal, warnings)
    balance = ""
    if winner in WINNERS and not fatal:
        balance = _margin_problem(argument_map, winner)

    parts = _normalize_parts(data.get("parts"), level, warnings, fatal)
    summary = str(data.get("summary_ja") or "").strip()
    if len(summary) > 200:
        warnings.append(make_warning(f"全体解説が200字を超えています（{len(summary)}字）。", "weak"))

    normalized = {
        "intended_winner": winner if winner in WINNERS else "",
        "points": points,
        "argument_map": argument_map,
        "parts": parts,
        "summary_ja": summary,
    }
    return normalized, fatal, warnings, balance


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


def _normalize_argument_map(raw, points: dict, fatal: list[str], warnings: list[dict]) -> list:
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
        if status not in ARGUMENT_STATUS:
            fatal.append(
                f"{point_id} の status「{status or '空'}」は不正です。"
                "intact / weakened / collapsed のみ使ってください。"
            )
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
            if action == "reinforced":
                action = "extended"
            if part not in PART_ORDER or action not in HISTORY_ACTION:
                if action or part:
                    warnings.append(
                        make_warning(f"{point_id}: history の {part or '?'} / {action or '?'} を除きました。", "weak")
                    )
                continue
            history.append({"part": part, "action": action})
        reason = str(item.get("reason_ja") or "").strip()
        if not reason:
            warnings.append(make_warning(f"{point_id}: reason_ja がありません。", "weak"))
        elif len(reason) > 60:
            warnings.append(
                make_warning(f"{point_id}: reason_ja が60字を超えています（{len(reason)}字）。", "weak")
            )
        point = lookup[point_id]
        normalized.append(
            {
                "id": point_id,
                "argument_id": point_id,
                "side": side,
                "raised_in": raised,
                "raised_in_part": raised,
                "status": status if status in ARGUMENT_STATUS else "",
                "summary": str(item.get("summary") or point.get("summary_ja") or "").strip(),
                "summary_ja": str(point.get("summary_ja") or "").strip(),
                "summary_en": str(point.get("summary_en") or "").strip(),
                "reason_ja": reason,
                "history": history,
            }
        )
    for point_id in ("gov_1", "gov_2", "opp_1", "opp_2"):
        if point_id not in seen and point_id in lookup:
            fatal.append(f"argument_map に {point_id} がありません。")
    return normalized


def _margin_problem(argument_map: list, winner: str) -> str:
    totals = side_score_totals(argument_map)
    gov = float(totals["gov"])
    opp = float(totals["opp"])
    leader = "Gov" if gov > opp else "Opp" if opp > gov else ""
    gap = round(abs(gov - opp) + 1e-9, 1)
    if leader == winner and SCRIPT_WINNER_MARGIN_MIN - 1e-9 <= gap <= SCRIPT_WINNER_MARGIN_MAX + 1e-9:
        return ""
    line = format_score_total(totals)
    return (
        f"優勢差が範囲外です（{line}、差 {gap:.1f}。"
        f"目安 {SCRIPT_WINNER_MARGIN_MIN:.1f}–{SCRIPT_WINNER_MARGIN_MAX:.1f}、指定 {winner}）。"
    )


def _part_quality_warnings(part: str, text: str, level: str) -> list[dict]:
    """語数・制限時間・架空の統計。下書きは落とさない。"""
    warnings = []
    count = word_count(text)
    if not text or not count:
        return warnings
    hits = [label for pattern, label in _FABRICATION_PATTERNS if pattern.search(text)]
    if hits:
        warnings.append(
            make_warning(f"{part}: 架空の統計・引用の可能性（{'、'.join(hits)}）", "strong")
        )
    low, high = word_range_for(part, level if level in LEVEL_SPECS else "normal")
    limit = int(PART_DEFS[part]["time_limit_sec"])
    est = round(count / SCRIPT_WORDS_PER_MINUTE * 60)
    if est > limit:
        warnings.append(
            make_warning(
                f"{part}: 読み時間の目安が制限を超えています"
                f"（約{est}秒 / 制限{limit}秒、{count}語・約{SCRIPT_WORDS_PER_MINUTE}語/分）。",
                "strong",
            )
        )
    elif count < low or count > high:
        warnings.append(
            make_warning(
                f"{part}: 語数が目安の外です（{count}語。目安 {low}–{high}）。"
                f"読み時間の目安は約{est}秒（制限{limit}秒、約{SCRIPT_WORDS_PER_MINUTE}語/分）。",
                "weak",
            )
        )
    return warnings


def _normalize_parts(raw, level: str, warnings: list[dict], fatal: list[str]) -> list:
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
            warnings.append(make_warning(f"{part}: 日本語ポイントが40字を超えています（{len(key_point)}字）。", "weak"))
        count = word_count(text)
        if text:
            warnings.extend(_part_quality_warnings(part, text, level))
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
    fallback: tuple[dict, list[dict], str] | None = None

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
            if attempt == 0:
                messages = _retry_messages(prompt, last_fatal)
                continue
            break
        normalized, fatal, warnings, balance = validate_generated(data, level)
        if not fatal and not balance:
            return _pack_script(normalized, warnings, model, total_cost)
        reasons = list(fatal)
        if balance:
            reasons.append(balance)
        last_fatal = reasons
        logger.info("Script validation failed (attempt=%s): %s", attempt + 1, "; ".join(reasons))
        if not fatal:
            fallback = (normalized, warnings, balance)
        if attempt == 0:
            messages = _retry_messages(prompt, reasons)
            continue
        break

    if fallback:
        normalized, warnings, balance = fallback
        kept = list(warnings)
        if balance:
            kept.append(make_warning(balance, "strong"))
        return _pack_script(normalized, kept, model, total_cost)

    raise ValueError(" / ".join(last_fatal) or "スクリプトを生成できませんでした。")


def _pack_script(normalized: dict, warnings: list, model: str, total_cost: float) -> dict:
    packed = dict(normalized)
    packed["script_model"] = model
    packed["gen_cost_usd"] = round(total_cost, 6)
    packed["warnings"] = [normalize_warning(item) for item in warnings]
    return packed


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


def apply_part_text(part: dict, text: str, level: str) -> tuple[dict, list[dict]]:
    """本文編集後のパート。語数・時間・引用の警告を返す。音声ハッシュは残す。"""
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
    part_name = str(updated.get("part") or "PM")
    return updated, _part_quality_warnings(part_name, cleaned, level if level in LEVEL_SPECS else "normal")
