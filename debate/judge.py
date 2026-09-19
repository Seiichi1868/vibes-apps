"""LLMによるPDA形式ディベートのジャッジ機能。

6パート（PM/LO/MG/MO/LOR/PMR）のtranscript_editedを1つのJSONにまとめてLLMに渡し、
論点フロー分析（Standing Points）に基づく勝敗判定・スコア・講評を取得する。
"""
import json
import logging
import os
import re
import time

from debate.config import PART_ORDER

logger = logging.getLogger(__name__)

# ジャッジ用システムプロンプト（PDAの2論点分担を含む）
JUDGE_SYSTEM_PROMPT = """あなたはPDA形式の即興ディベートを審査するジャッジです。

# ジャッジの心構え
- あなたは専門家ではなく、「新聞を読んでいれば分かる程度の一般常識を持つ人」として判定してください。
- 個人的な意見や政治的立場を排し、その場で提示された議論の内容のみに基づいて判定してください。

# 2論点の分担（重要：誤ると判定が歪む）
各陣営は2つの論点を出すが、2つ目の詳細展開は後続スピーカーの正規の役割である。

- Gov: PMが Point 1 と Point 2 を提示する。Point 1 は主にPMが詳しく述べ、
  Point 2 はPMでは概要・予告でよく、詳細な理由・具体例はMGが展開する。
- Opp: LOが Point 1 と Point 2 を提示する。Point 1 は主にLOが詳しく述べ、
  Point 2 はLOでは概要・予告でよく、詳細な理由・具体例はMOが展開する。

したがって：
- PM / LO の part_feedback・role_fulfillment・Content で、
  「2つ目の論点が詳しく述べられていない」ことを欠点として指摘してはならない。
  概要提示で役割は果たしている。
- Gov Point 2 の深さ・具体例は MG の発話で評価する。展開が弱い場合は MG の役割不履行として書く。
- Opp Point 2 の深さ・具体例は MO の発話で評価する。展開が弱い場合は MO の役割不履行として書く。
- 論点フローでは Gov Point 2 を PM で raised、MG で extended と記録してよい。
  Opp Point 2 は LO で raised、MO で extended と記録してよい。これは正常な進行である。

# 勝敗判定の中心ロジック：論点のフロー分析（Standing Points）
6パートを発言順に読み、Gov側・Opp側それぞれが提示した論点を抽出してください。
各論点について、以下のプロセスで追跡してください。

1. どのパートで、どちらの側が、どの論点を最初に提示したか
2. その論点に対し、相手側が後続パートで有効な反論をしたか
3. 反論された場合、論点を出した側が、さらに後続パートでその反論に対して
   再反論・防御をしたか

各論点の最終ステータスを以下のいずれかに分類してください。
- "standing"：反論を受けなかった、または反論に対して有効に再反論・防御された
- "knocked_down"：有効な反論を受けたが、再反論・防御が一切なされなかった
- "extended"：反論の有無に関わらず、元の側が後続パートで自ら補強・具体化した
  （Gov Point 2 をMGが展開した場合、Opp Point 2 をMOが展開した場合も含む）

新規論点の扱い：LORおよびPMRで新たに提示された論点は、ディベートのルール上
無効（反則気味）として扱い、standing/knocked_downの判定対象に含めないでください。
part_feedbackの当該パートで軽く指摘してください。

# 勝敗の決定
- 最終的にstanding（またはextended）となった論点の数と、論題への関連性の高さを踏まえ、
  どちらの側がより多くの、より重要な論点を守り切ったかで勝敗（winner）を決定してください。
- 論点の数が拮抗している場合は、内容（Content）ルーブリックの質を判断材料にしてください。

# 評価ルーブリック（論点フロー分析の補助情報として使用）

## 内容 (Content)
1. 主張の理由：主張を支える論理的な理由・根拠が明確に示されているか
2. 具体例：説得力を高める具体的な事例やデータが挙げられているか
3. 論題との関連性：議論が論題から外れず、核心をついているか

## 構成・議論運び (Method)
1. 反駁の的確さ：相手の主張を正確に理解した上で、有効に反論できているか
2. フローの一貫性・応答性：前のスピーカーの議論を無視せず、話が噛み合っているか
3. 役割遂行：各パートに求められる役割
   （PM:定義+2論点提示。Point 1は詳しく、Point 2は概要でよい／
   LO:再構築+反駁+2論点提示。Point 1は詳しく、Point 2は概要でよい／
   MG:反駁+Gov Point 2の詳細展開・強化／
   MO:反駁+Opp Point 2の詳細展開・深化／
   LOR:整理+総括（新規論点不可）／
   PMR:総括（新規論点不可））を果たしているか

# タイムマネジメント (Time Management)
システム側で計算済みのelapsed_sec / time_limit_secが渡されるので、判定不要です。
超過が著しい場合のみ、part_feedbackで軽く言及してください。

# 出力フォーマット（このJSON形式のみで出力し、前置き・Markdown装飾は不要）

{
  "argument_flow": [
    {
      "argument_id": "gov_1",
      "side": "Gov",
      "raised_in_part": "PM",
      "summary": "論点の要約（日本語、30字程度）",
      "status": "standing",
      "history": [
        { "part": "PM", "action": "raised" },
        { "part": "LO", "action": "rebutted" },
        { "part": "MG", "action": "defended" }
      ]
    }
  ],
  "winner": "Gov または Opp",
  "standing_point_count": { "gov": 0, "opp": 0 },
  "scores": {
    "content": { "reasoning": 1-5, "examples": 1-5, "relevance": 1-5 },
    "method": { "rebuttal_accuracy": 1-5, "flow_consistency": 1-5, "role_fulfillment": 1-5 }
  },
  "overall_feedback": "全体講評（日本語、200字程度、論点フローに基づいた根拠を含める）",
  "part_feedback": [
    { "part": "PM", "comment": "そのパートへの具体的フィードバック（日本語、100字程度）" },
    { "part": "LO", "comment": "..." },
    { "part": "MG", "comment": "..." },
    { "part": "MO", "comment": "..." },
    { "part": "LOR", "comment": "..." },
    { "part": "PMR", "comment": "..." }
  ]
}"""

_ARGUMENT_STATUSES = {"standing", "knocked_down", "extended"}
_SIDES = {"Gov", "Opp"}


def _get_client():
    from openai import OpenAI

    from debate.config import JUDGE_MAX_RETRIES, JUDGE_TIMEOUT_SEC

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAI(api_key=api_key, timeout=JUDGE_TIMEOUT_SEC, max_retries=JUDGE_MAX_RETRIES)


def _is_reasoning_model(model: str) -> bool:
    name = (model or "").strip().lower()
    if name.startswith("gpt-5") and "chat" not in name:
        return True
    return name.startswith(("o1", "o3", "o4"))


def build_judge_payload(session: dict) -> dict:
    """6パートのpart/side/transcript_edited/elapsed_sec/time_limit_secを1つのJSONにまとめる。"""
    parts_by_name = {p.get("part"): p for p in session.get("parts", [])}
    parts_payload = []
    for part_name in PART_ORDER:
        part_data = parts_by_name.get(part_name) or {}
        parts_payload.append(
            {
                "part": part_name,
                "side": part_data.get("side", ""),
                "transcript_edited": part_data.get("transcript_edited", ""),
                "elapsed_sec": part_data.get("elapsed_sec"),
                "time_limit_sec": part_data.get("time_limit_sec"),
            }
        )
    return {
        "motion": session.get("motion", ""),
        "point_development": {
            "gov_point_2": "PMで提示し、MGで詳しく展開する。PMで詳しく述べなくても減点しない。",
            "opp_point_2": "LOで提示し、MOで詳しく展開する。LOで詳しく述べなくても減点しない。",
        },
        "parts": parts_payload,
    }


def _extract_text(completion) -> str:
    if not completion.choices:
        return ""
    content = getattr(completion.choices[0].message, "content", None)
    return (content or "").strip()


def _parse_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("ジャッジ結果がJSONオブジェクトではありません。")
    return data


def _clamp_score(value) -> int | None:
    try:
        n = round(float(value))
    except (TypeError, ValueError):
        return None
    return max(1, min(5, n))


def _normalize_argument_flow(raw_flow) -> list:
    if not isinstance(raw_flow, list):
        return []

    normalized = []
    for idx, item in enumerate(raw_flow):
        if not isinstance(item, dict):
            continue
        side = str(item.get("side") or "").strip()
        if side not in _SIDES:
            continue
        status = str(item.get("status") or "").strip()
        if status not in _ARGUMENT_STATUSES:
            status = "standing"
        raised_in_part = str(item.get("raised_in_part") or "").strip()
        if raised_in_part not in PART_ORDER:
            raised_in_part = ""

        history = []
        for entry in item.get("history") or []:
            if not isinstance(entry, dict):
                continue
            part = str(entry.get("part") or "").strip()
            action = str(entry.get("action") or "").strip()
            if not part or not action:
                continue
            history.append({"part": part, "action": action})

        normalized.append(
            {
                "argument_id": str(item.get("argument_id") or f"{side.lower()}_{idx + 1}"),
                "side": side,
                "raised_in_part": raised_in_part,
                "summary": str(item.get("summary") or "").strip(),
                "status": status,
                "history": history,
            }
        )
    return normalized


def _normalize_result(data: dict) -> dict:
    winner = str(data.get("winner") or "").strip()
    if winner not in _SIDES:
        winner = None

    raw_count = data.get("standing_point_count") or {}
    try:
        gov_count = int(raw_count.get("gov", 0))
    except (TypeError, ValueError):
        gov_count = 0
    try:
        opp_count = int(raw_count.get("opp", 0))
    except (TypeError, ValueError):
        opp_count = 0

    raw_scores = data.get("scores") or {}
    raw_content = raw_scores.get("content") or {}
    raw_method = raw_scores.get("method") or {}

    part_feedback_by_part = {}
    for item in data.get("part_feedback") or []:
        if not isinstance(item, dict):
            continue
        part = str(item.get("part") or "").strip()
        if part in PART_ORDER:
            part_feedback_by_part[part] = str(item.get("comment") or "").strip()

    return {
        "argument_flow": _normalize_argument_flow(data.get("argument_flow")),
        "winner": winner,
        "standing_point_count": {"gov": max(0, gov_count), "opp": max(0, opp_count)},
        "scores": {
            "content": {
                "reasoning": _clamp_score(raw_content.get("reasoning")),
                "examples": _clamp_score(raw_content.get("examples")),
                "relevance": _clamp_score(raw_content.get("relevance")),
            },
            "method": {
                "rebuttal_accuracy": _clamp_score(raw_method.get("rebuttal_accuracy")),
                "flow_consistency": _clamp_score(raw_method.get("flow_consistency")),
                "role_fulfillment": _clamp_score(raw_method.get("role_fulfillment")),
            },
        },
        "overall_feedback": str(data.get("overall_feedback") or "").strip(),
        "part_feedback": [
            {"part": part, "comment": part_feedback_by_part.get(part, "")} for part in PART_ORDER
        ],
    }


def run_judge(session: dict) -> dict:
    """LLMを呼び出し、正規化済みのジャッジ結果（新しい判定内容の各フィールド）を返す。

    戻り値はnew_judge_result()のうちstatus/error/started_at/judged_at/transcription_mode
    以外のフィールド（argument_flow, winner, standing_point_count, scores,
    overall_feedback, part_feedback, model）を含む。
    """
    client = _get_client()
    if not client:
        raise RuntimeError("OPENAI_API_KEYが設定されていないため、ジャッジを実行できません。")

    from debate.judge_models import resolve_judge_model_metadata, resolve_judge_model_mode
    from debate.settings import load_settings, resolve_judge_model

    settings = load_settings()
    judge_mode = resolve_judge_model_mode(settings.get("judge_model_mode"))
    judge_model = resolve_judge_model(judge_mode)
    judge_model_info = resolve_judge_model_metadata(judge_mode)
    payload = build_judge_payload(session)
    user_content = json.dumps(payload, ensure_ascii=False, indent=2)

    kwargs: dict = {
        "model": judge_model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    if not _is_reasoning_model(judge_model):
        kwargs["temperature"] = 0.2

    started = time.monotonic()
    try:
        completion = client.chat.completions.create(**kwargs)
    except Exception as exc:
        elapsed = time.monotonic() - started
        logger.warning("Judge request failed after %.1fs (model=%s): %s", elapsed, judge_model, exc)
        raise

    elapsed = time.monotonic() - started
    raw = _extract_text(completion)
    if not raw:
        raise ValueError("ジャッジ結果が空でした。")

    data = _parse_json_object(raw)
    result = _normalize_result(data)
    result["model"] = judge_model
    result["judge_model"] = judge_model_info
    logger.info("Judge finished in %.1fs (model=%s, winner=%s)", elapsed, judge_model, result.get("winner"))
    return result
