"""LLMによるPDA形式ディベートのジャッジ機能。

6パート（PM/LO/MG/MO/LOR/PMR）のtranscript_editedを1つのJSONにまとめてLLMに渡し、
論点フロー分析（Standing Points）に基づく勝敗判定・スコア・講評を取得する。
"""
import json
import logging
import os
import re
import time

from debate.config import PART_ORDER, PART_ROLES

logger = logging.getLogger(__name__)

# ジャッジ用システムプロンプト（授業フローの2論点分担・反論対象を含む）
JUDGE_SYSTEM_PROMPT = """あなたはPDA形式の即興ディベートを審査するジャッジです。

# ジャッジの心構え
- あなたは専門家ではなく、「新聞を読んでいれば分かる程度の一般常識を持つ人」として判定してください。
- 個人的な意見や政治的立場を排し、その場で提示された議論の内容のみに基づいて判定してください。

# 正規の試合フロー（この順番で役割を評価する）
各陣営の正規論点は Point 1 と Point 2 の2つのみ。

- PM: 論題を定義し、2論点を予告する。Point 1 を詳しく述べ、Point 2 は名前・概要でよい。
- LO: Govの議論を再構築したうえで反駁する。自陣の2論点を予告し、Point 1 を詳しく述べ、
  Point 2 は名前・概要でよい。
- MG: ①Opp Point 1 に反駁する ②Gov Point 1 を再構築・防御する ③Gov Point 2 を詳しく展開する。
  この時点では Opp Point 2 はまだ詳しく出ていない。Opp Point 2 への反論不足を減点してはならない。
- MO: ①Gov Point 1 に反駁する ②Opp Point 1 を再構築・防御する ③Opp Point 2 を詳しく展開する。
- LOR: 最も重要な対立を整理し、Opp優位を総括する。新規論点は不可。
- PMR: 先に Opp Point 2 に反駁し、その後で試合を総括してGov優位を主張する。新規論点は不可。

# 2論点の分担（重要：誤ると判定が歪む）
- Gov Point 2 の深さ・具体例は MG で評価する。PMで詳しくなくても減点しない。
- Opp Point 2 の深さ・具体例は MO で評価する。LOで詳しくなくても減点しない。
- MG が Gov Point 1 を守り直していない場合は、Point 2 不足より先にその役割不履行を書く。
- MO が Opp Point 1 を守り直していない場合も同様。
- Opp Point 2 への本格反論は PMR の仕事である。MG に求めてはならない。
- 論点フローでは Gov Point 2 を PM で raised、MG で extended と記録してよい。
  Opp Point 2 は LO で raised、MO で extended、PMR で rebutted と記録してよい。

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

新規論点の扱い：
- 各陣営の正規論点は Point 1 と Point 2 のみ。
- MG / MO で Point 3 以降を新たに出しても standing 加点対象にしない。part_feedbackで軽く指摘する。
- LOR / PMR の新規論点は無効（反則気味）。standing/knocked_downの判定対象に含めず、
  part_feedbackの当該パートで軽く指摘する。

# 勝敗の決定
- 最終的にstanding（またはextended）となった論点の数と、論題への関連性の高さを踏まえ、
  どちらの側がより多くの、より重要な論点を守り切ったかで勝敗（winner）を決定してください。
- 論点の数が拮抗している場合は、内容（Content）ルーブリックの質を判断材料にしてください。

# 評価ルーブリック（論点フロー分析の補助情報として使用）

## 内容 (Content)
1. 主張の理由：主張を支える論理的な理由・根拠が明確に示されているか
2. 具体例：説得力を高める具体的な事例やデータが挙げられているか
3. 論題との関連性：議論が論題から外れず、核心をついているか
Point 2 の理由・具体例は、GovはPM+MG、OppはLO+MOをセットで見る。

## 構成・議論運び (Method)
1. 反駁の的確さ：相手の主張を正確に理解した上で、有効に反論できているか
   （MGはOpp Point 1、MOはGov Point 1、PMRはOpp Point 2 を主対象とする）
2. フローの一貫性・応答性：前のスピーカーの議論を無視せず、話が噛み合っているか
3. 役割遂行：上記「正規の試合フロー」の各パート役割を果たしているか

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
    },
    {
      "argument_id": "gov_2",
      "side": "Gov",
      "raised_in_part": "PM",
      "summary": "Gov Point 2 の要約",
      "status": "extended",
      "history": [
        { "part": "PM", "action": "raised" },
        { "part": "MG", "action": "extended" }
      ]
    },
    {
      "argument_id": "opp_2",
      "side": "Opp",
      "raised_in_part": "LO",
      "summary": "Opp Point 2 の要約",
      "status": "standing",
      "history": [
        { "part": "LO", "action": "raised" },
        { "part": "MO", "action": "extended" },
        { "part": "PMR", "action": "rebutted" }
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
        "speaker_roles": PART_ROLES,
        "expected_flow": {
            "regular_points": "各陣営 Point 1 と Point 2 のみ。Point 3 以降は加点しない。",
            "gov_point_1": "PMで詳しく展開し、LOの反論のあとMGが再構築・防御する。",
            "gov_point_2": "PMで概要提示し、MGで詳しく展開する。PMで詳しくなくても減点しない。",
            "opp_point_1": "LOで詳しく展開し、MGの反論のあとMOが再構築・防御する。",
            "opp_point_2": "LOで概要提示し、MOで詳しく展開する。本格反論はPMR。MGには求めない。",
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
