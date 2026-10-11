"""観戦スクリプトを既存ジャッジに通し、設計との一致を見る。

ジャッジのプロンプトは debate/judge.py のまま。設計（勝者・論点の状態）は渡さない。
結果はセッションには保存しない。
"""
from __future__ import annotations

import logging

from debate.config import canonical_argument_status, side_score_totals
from debate.judge_model_pricing import JUDGE_MODEL_PRICING

logger = logging.getLogger(__name__)

MAX_CHECK_CALLS = 12
CHECK_RUNS_MAX = 3
ASSUMED_OUTPUT_TOKENS = 2000
CHECK_NOTE = "一致率は参考値です。不一致は、スクリプトの設計の問題とジャッジの問題のどちらでも起こります。原因は本文を読んで判断してください。実行回数が少ないうちは傾向までしか見られません。"
COST_NOTE = "出力は仮に2,000トークンとして計算しています。推論トークン次第で増えます。"


def parse_check_request(payload: dict) -> tuple[list[str], int]:
    raw_modes = payload.get("models") or payload.get("model_modes") or []
    if isinstance(raw_modes, str):
        raw_modes = [raw_modes]
    modes = []
    for item in raw_modes:
        mode = str(item or "").strip()
        if mode in JUDGE_MODEL_PRICING and mode not in modes:
            modes.append(mode)
    try:
        runs = int(payload.get("runs") or payload.get("runs_per_model") or 1)
    except (TypeError, ValueError):
        runs = 0
    if not modes:
        raise ValueError("ジャッジモデルを1つ以上選んでください。")
    if runs < 1 or runs > CHECK_RUNS_MAX:
        raise ValueError("1モデルあたりの実行回数は1〜3です。")
    calls = len(modes) * runs
    if calls > MAX_CHECK_CALLS:
        raise ValueError(f"1回の実行はAPI呼び出し{MAX_CHECK_CALLS}回までです（今回 {calls} 回）。")
    return modes, runs


def estimate_check_cost(script: dict, model_modes: list[str], runs: int) -> dict:
    from debate.ai_script import word_count
    from debate.judge import JUDGE_SYSTEM_PROMPT

    words = 0
    for part in script.get("parts") or []:
        if isinstance(part, dict):
            words += word_count(str(part.get("text") or ""))
    prompt_tokens = max(1, round(len(JUDGE_SYSTEM_PROMPT) / 4 + words * 1.3 + 500))
    per_call = []
    total = 0.0
    for mode in model_modes:
        meta = JUDGE_MODEL_PRICING[mode]
        one = (
            prompt_tokens * float(meta["input_price_per_1m"]) / 1_000_000
            + ASSUMED_OUTPUT_TOKENS * float(meta["output_price_per_1m"]) / 1_000_000
        )
        cost = round(one * runs, 6)
        total += cost
        per_call.append(
            {
                "model_mode": mode,
                "model": meta["model"],
                "runs": runs,
                "cost_usd": cost,
            }
        )
    return {
        "calls": len(model_modes) * runs,
        "prompt_tokens_estimate": prompt_tokens,
        "output_tokens_assumption": ASSUMED_OUTPUT_TOKENS,
        "word_count": words,
        "cost_usd": round(total, 6),
        "per_model": per_call,
        "note": COST_NOTE,
    }


def _side_rows(items) -> dict[str, list]:
    grouped = {"Gov": [], "Opp": []}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        side = str(item.get("side") or "").strip()
        if side in grouped:
            grouped[side].append(item)
    return grouped


def compare_design_and_judge(script: dict, judge_result: dict) -> dict:
    """陣営ごとの出現順で4論点を対応づける。ジャッジの id は使わない。"""
    design = _side_rows(script.get("argument_map") or [])
    judged = _side_rows(judge_result.get("argument_flow") or [])
    design_totals = side_score_totals(script.get("argument_map") or [])
    judge_totals = judge_result.get("score_total") if isinstance(judge_result.get("score_total"), dict) else {}
    winner = str(judge_result.get("winner") or "")
    intended = str(script.get("intended_winner") or "")
    counts_ok = all(len(design[side]) == 2 and len(judged[side]) == 2 for side in ("Gov", "Opp"))
    base = {
        "winner": winner,
        "intended_winner": intended,
        "winner_match": bool(winner) and winner == intended,
        "gov": judge_totals.get("gov"),
        "opp": judge_totals.get("opp"),
        "design_gov": design_totals.get("gov"),
        "design_opp": design_totals.get("opp"),
        "point_count_mismatch": not counts_ok,
        "design_counts": {side: len(design[side]) for side in ("Gov", "Opp")},
        "judge_counts": {side: len(judged[side]) for side in ("Gov", "Opp")},
    }
    if not counts_ok:
        base["status_match"] = None
        base["status_ratio"] = None
        base["status_key"] = "count-mismatch"
        base["points"] = []
        return base
    points = []
    matched = 0
    keys = []
    for side in ("Gov", "Opp"):
        for index in range(2):
            designed = design[side][index]
            judged_row = judged[side][index]
            design_status = canonical_argument_status(designed.get("status"))
            judge_status = canonical_argument_status(judged_row.get("status"))
            same = design_status == judge_status
            matched += int(same)
            keys.append(judge_status)
            points.append(
                {
                    "label": f"{side} {index + 1}",
                    "design_status": design_status,
                    "judge_status": judge_status,
                    "reason_ja": str(judged_row.get("reason_ja") or "").strip(),
                    "same": same,
                }
            )
    base["status_match"] = f"{matched}/4"
    base["status_ratio"] = matched / 4
    base["status_key"] = ",".join(keys)
    base["points"] = points
    return base


def summarize_results(results: list[dict]) -> list[dict]:
    grouped: dict[str, list] = {}
    for row in results or []:
        if row.get("status") != "done":
            continue
        grouped.setdefault(str(row.get("model_mode") or ""), []).append(row)
    summaries = []
    for mode, rows in grouped.items():
        if not mode:
            continue
        winner_hits = sum(1 for row in rows if row.get("winner_match"))
        ratios = [float(row["status_ratio"]) for row in rows if row.get("status_ratio") is not None]
        winners = [str(row.get("winner") or "") for row in rows]
        status_keys = [str(row.get("status_key") or "") for row in rows]
        summaries.append(
            {
                "model_mode": mode,
                "model": rows[0].get("model") or mode,
                "runs": len(rows),
                "winner_rate": round(winner_hits / len(rows), 3),
                "status_avg": round(sum(ratios) / len(ratios), 3) if ratios else None,
                "same_winner": len(set(winners)) == 1 if len(rows) > 1 else None,
                "same_status": len(set(status_keys)) == 1 if len(rows) > 1 else None,
            }
        )
    return summaries
