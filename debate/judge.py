"""LLMによるPDA形式ディベートのジャッジ機能。

6パート（PM/LO/MG/MO/LOR/PMR）のtranscript_editedを1つのJSONにまとめてLLMに渡し、
論点の状態（intact / weakened / collapsed）に基づく勝敗判定・スコア・講評を取得する。
"""
import json
import logging
import os
import re
import time

from debate.config import (
    HISTORY_ACTION,
    PART_ORDER,
    PART_ROLES,
    POI_ALLOWED_PARTS,
    argument_status_rules_text,
    canonical_argument_status,
    side_score_totals,
)

logger = logging.getLogger(__name__)

# ジャッジ用システムプロンプト（授業フローの2論点分担・反論対象を含む）
JUDGE_SYSTEM_PROMPT = """あなたはPDA形式の即興ディベートを審査するジャッジです。

# ジャッジの心構え
- あなたは専門家ではなく、「新聞を読んでいれば分かる程度の一般常識を持つ人」として判定してください。
- 個人的な意見や政治的立場を排し、その場で提示された議論の内容のみに基づいて判定してください。

# 正規の試合フロー（この順番で役割を評価する）
各陣営の正規論点は Point 1 と Point 2 の2つのみ。

- PM: 論題を定義し、2論点を予告する。Point 1 を詳しく述べ、Point 2 は名前・概要でよい。
- LO: Gov Point 1 を再構築したうえで反駁する。自陣の2論点を予告し、Point 1 を詳しく述べ、
  Point 2 は名前・概要でよい。PMが Gov Point 2 をタイトルだけにしたことを攻撃してはならない。
  その詳しい説明は次のMGの仕事であり、PMで詳しくないことは欠点ではない。
- MG: ①Opp Point 1 に反駁する ②Gov Point 1 を再構築・防御する ③Gov Point 2 を詳しく展開する。
  この時点では Opp Point 2 はまだ詳しく出ていない。Opp Point 2 への反論不足を減点してはならない。
- MO: ①MGによる Gov Point 1 再構築に反駁する ②その直後に Gov Point 2 に反駁する
  ③Opp Point 1 を再構築・防御する ④Opp Point 2 を詳しく展開する。
  Gov Point 2 への反論をLORへ回してはならない。
- LOR: 最も重要な対立を整理し、Opp優位を総括する。新規論点は不可。
  Gov Point 2 への反論を冒頭で行ってはならない。それはMOの2番目である。
- PMR: 先に Opp Point 2 に反駁し、その後で試合を総括してGov優位を主張する。新規論点は不可。

# 2論点の分担（重要：誤ると判定が歪む）
- Gov Point 2 の深さ・具体例は MG で評価する。PMで詳しくなくても減点しない。
  LOが「PMはPoint 2を詳しく説明しなかった」と攻撃していても、その攻撃は役割違反であり、
  Govの欠点にはしない。
- Opp Point 2 の深さ・具体例は MO で評価する。LOで詳しくなくても減点しない。
- MG が Gov Point 1 を守り直していない場合は、Point 2 不足より先にその役割不履行を書く。
- MO が Opp Point 1 を守り直していない場合も同様。
- Opp Point 2 への本格反論は PMR の仕事である。MG に求めてはならない。
- Gov Point 2 への本格反論は MO の2番目（MGによる Gov Point 1 再構築への反論の直後）である。
  LORの冒頭に置くのは役割違反。LORがそこで初めて反論していても、MOがやるべき仕事の肩代わりとして扱う。
- 論点フローでは Gov Point 2 を PM で raised、MG で extended、MO で rebutted と記録してよい。
  Opp Point 2 は LO で raised、MO で extended、PMR で rebutted と記録してよい。

# 勝敗判定の中心ロジック：論点の状態
6パートを発言順に読み、Gov側・Opp側それぞれが提示した正規論点（各陣営 Point 1 と Point 2）を追跡してください。
補強（Gov Point 2 を MG が展開、Opp Point 2 を MO が展開）は status にせず、history の action "extended" に記録してください。

{argument_status_rules_text()}

新規論点の扱い：
- 各陣営の正規論点は Point 1 と Point 2 のみ。
- MG / MO で Point 3 以降を新たに出しても合計点に入れない。part_feedbackで軽く指摘する。
- LOR / PMR の新規論点は無効（反則気味）。状態判定の対象に含めず、
  part_feedbackの当該パートで軽く指摘する。

# 評価ルーブリック（論点フロー分析の補助情報として使用）

## 内容 (Content)
1. 主張の理由：主張を支える論理的な理由・根拠が明確に示されているか
2. 具体例：説得力を高める具体的な事例やデータが挙げられているか
3. 論題との関連性：議論が論題から外れず、核心をついているか
Point 2 の理由・具体例は、GovはPM+MG、OppはLO+MOをセットで見る。

## 構成・議論運び (Method)
1. 反駁の的確さ：相手の主張を正確に理解した上で、有効に反論できているか
   （MGはOpp Point 1、MOはGov Point 1の再構築とGov Point 2、PMRはOpp Point 2 を主対象とする）
2. フローの一貫性・応答性：前のスピーカーの議論を無視せず、話が噛み合っているか
3. 役割遂行：上記「正規の試合フロー」の各パート役割を果たしているか

# タイムマネジメント (Time Management)
システム側で計算済みのelapsed_sec / time_limit_secが渡されるので、判定不要です。
超過が著しい場合のみ、part_feedbackで軽く言及してください。
speaker が "ai" のパートはタイムマネジメントの対象外です（elapsed_sec は null）。

# POI（Point of Information）
PM / LO / MG / MO では、保護時間を除き相手がPOIを出せます。
保護時間は payload の poi_protected_start_sec（最初）と poi_protected_end_sec（最後）。0 ならその側は保護なしです。
LOR / PMR（Reply）ではPOIは不可です。POI中もスピーカーの持ち時間は止まりません。1回あたり最長15秒です。
payload の各パートに poi（allowed / offered / accepted / events）が付きます。
- 勝敗判定と論点の合計点の根拠に、POIの回数は使わないでください。
- POIを出さなかった／取らなかったことを減点しないでください（授業練習のため任意です）。
- 文字起こしからPOIの質問と応答が読み取れる場合のみ、part_feedbackで短く触れてよいです。

# 話者について
一部のパートは練習用AIが担当しています。payload の各パートに speaker ("human" または "ai") が付きます。
argument_flow の intact / weakened / collapsed と勝敗判定は、話者によって基準を変えないでください。
part_feedback では human パートに生徒への改善提案を書き、ai パートは相手の発話として簡潔に触れるに留めてください。
生徒側へのフィードバックが「相手の発話の改善案」にならないようにしてください。
AIが使ったモデル名には触れないでください。

# 出力フォーマット（このJSON形式のみで出力し、前置き・Markdown装飾は不要）

{
  "argument_flow": [
    {
      "argument_id": "gov_1",
      "side": "Gov",
      "raised_in_part": "PM",
      "summary": "論点の要約（日本語、30字程度）",
      "status": "intact",
      "reason_ja": "LOの反論は核心に届いたが、MGが十分に防御して回復した。",
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
      "status": "weakened",
      "reason_ja": "MOの反論は範囲への指摘にとどまり、その後の防御も部分的だった。",
      "history": [
        { "part": "PM", "action": "raised" },
        { "part": "MG", "action": "extended" },
        { "part": "MO", "action": "rebutted" }
      ]
    },
    {
      "argument_id": "opp_2",
      "side": "Opp",
      "raised_in_part": "LO",
      "summary": "Opp Point 2 の要約",
      "status": "collapsed",
      "reason_ja": "PMRの反論は核心に届き、その後に防御がなかった。",
      "history": [
        { "part": "LO", "action": "raised" },
        { "part": "MO", "action": "extended" },
        { "part": "PMR", "action": "rebutted" }
      ]
    }
  ],
  "winner": "Gov または Opp",
  "score_total": { "gov": 0.0, "opp": 0.0 },
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

JUDGE_SYSTEM_PROMPT = JUDGE_SYSTEM_PROMPT.replace(
    "{argument_status_rules_text()}",
    argument_status_rules_text(),
)

# パート練習で範囲が6パート未満のときだけ足す。通常対戦・ソロの全文ジャッジには付けない。
PARTIAL_PRACTICE_ADDENDUM = """

# 今回は途中までのパート練習です
payload.parts に含まれるパートだけが実施されています。それ以外のパートは行われていません。
- 未実施パートの役割を誰かが果たしていないことを減点しないでください。
- Gov Point 2 の詳細は、MG が今回の範囲に無いなら PM の概要のままでよく、減点しません。
- Opp Point 2 の詳細は、MO が範囲に無いなら LO の概要のままでよく、減点しません。
- 後続パートが範囲外であるだけを理由に collapsed や weakened にしないでください。実施済みの中で核心に届く反論があり、実施済みの範囲で防御がないときだけ collapsed にしてください。届き方が partial なら weakened にしてください。
- 片方の陣営しか発言していない場合、winner は null にしてください。
- part_feedback は payload.parts にあるパートだけ書いてください。human は生徒への改善提案、ai は相手の発話の短い要約に留めてください。
- overall_feedback は、生徒（speaker が human）のパートをどう良くするかを中心にしてください。
- scores は実施された human の発話に対する評価です。
"""

_SIDES = {"Gov", "Opp"}


def _poi_protected_times() -> tuple[int, int]:
    from debate.settings import clamp_poi_protected_sec, load_settings

    settings = load_settings()
    return (
        clamp_poi_protected_sec(settings.get("poi_protected_start_sec")),
        clamp_poi_protected_sec(settings.get("poi_protected_end_sec")),
    )


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


def _judge_part_names(session: dict) -> list[str]:
    """通常・ソロは6パート。パート練習は選ばれた範囲だけ。"""
    if str(session.get("mode") or "") != "practice":
        return list(PART_ORDER)
    from debate.solo import part_is_omitted

    parts_by_name = {p.get("part"): p for p in session.get("parts", [])}
    return [name for name in PART_ORDER if not part_is_omitted(parts_by_name.get(name))]


def build_judge_payload(session: dict) -> dict:
    """採点対象パートの transcript を1つのJSONにまとめる。"""
    parts_by_name = {p.get("part"): p for p in session.get("parts", [])}
    part_names = _judge_part_names(session)
    partial = str(session.get("mode") or "") == "practice" and part_names != list(PART_ORDER)
    parts_payload = []
    for part_name in part_names:
        part_data = parts_by_name.get(part_name) or {}
        speaker = part_data.get("speaker") or "human"
        elapsed = None if speaker == "ai" else part_data.get("elapsed_sec")
        pois = part_data.get("pois") if isinstance(part_data.get("pois"), list) else []
        accepted = sum(1 for item in pois if isinstance(item, dict) and item.get("status") == "accepted")
        parts_payload.append(
            {
                "part": part_name,
                "side": part_data.get("side", ""),
                "speaker": speaker,
                "transcript_edited": part_data.get("transcript_edited", ""),
                "elapsed_sec": elapsed,
                "time_limit_sec": part_data.get("time_limit_sec"),
                "poi": {
                    "allowed": part_name in POI_ALLOWED_PARTS,
                    "offered": len(pois),
                    "accepted": accepted,
                    "events": pois,
                },
            }
        )
    start_sec, end_sec = _poi_protected_times()
    payload = {
        "motion": session.get("motion", ""),
        "speaker_roles": PART_ROLES if not partial else {name: PART_ROLES.get(name, "") for name in part_names},
        "poi_protected_start_sec": start_sec,
        "poi_protected_end_sec": end_sec,
        "expected_flow": {
            "regular_points": "各陣営 Point 1 と Point 2 のみ。Point 3 以降は加点しない。",
            "gov_point_1": "PMで詳しく展開し、LOの反論のあとMGが再構築・防御する。",
            "gov_point_2": "PMではタイトルのみ。詳しい説明はMG。PMで詳しくないことは欠点ではなく、LOがそれを攻撃してもGovの減点理由にしない。本格反論はMOの2番目（Gov Point 1再構築への反論の直後）。LORの冒頭では行わない。",
            "opp_point_1": "LOで詳しく展開し、MGの反論のあとMOが再構築・防御する。",
            "opp_point_2": "LOで概要提示し、MOで詳しく展開する。本格反論はPMR。MGには求めない。",
        },
        "parts": parts_payload,
    }
    if partial:
        payload["partial_practice"] = True
        payload["included_parts"] = part_names
    return payload


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
        raw_status = str(item.get("status") or "").strip()
        status = canonical_argument_status(raw_status)
        raised_in_part = str(item.get("raised_in_part") or "").strip()
        if raised_in_part not in PART_ORDER:
            raised_in_part = ""

        history = []
        saw_extended = False
        for entry in item.get("history") or []:
            if not isinstance(entry, dict):
                continue
            part = str(entry.get("part") or "").strip()
            action = str(entry.get("action") or "").strip()
            if action == "reinforced":
                action = "extended"
            if not part or action not in HISTORY_ACTION:
                continue
            if action == "extended":
                saw_extended = True
            history.append({"part": part, "action": action})
        if raw_status == "extended" and not saw_extended and raised_in_part:
            history.append({"part": raised_in_part, "action": "extended"})

        normalized.append(
            {
                "argument_id": str(item.get("argument_id") or f"{side.lower()}_{idx + 1}"),
                "side": side,
                "raised_in_part": raised_in_part,
                "summary": str(item.get("summary") or "").strip(),
                "status": status,
                "reason_ja": str(item.get("reason_ja") or "").strip(),
                "history": history,
            }
        )
    return normalized


def _normalize_result(data: dict) -> dict:
    winner = str(data.get("winner") or "").strip()
    if winner not in _SIDES:
        winner = None

    flow = _normalize_argument_flow(data.get("argument_flow"))
    totals = side_score_totals(flow)
    gov_n = sum(1 for item in flow if item.get("side") == "Gov")
    opp_n = sum(1 for item in flow if item.get("side") == "Opp")
    if gov_n and opp_n:
        if totals["gov"] > totals["opp"]:
            winner = "Gov"
        elif totals["opp"] > totals["gov"]:
            winner = "Opp"

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
        "argument_flow": flow,
        "winner": winner,
        "score_total": totals,
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


# 観戦スクリプトの照合で、ジャッジに渡してはいけない設計情報。
SCRIPT_CHECK_FORBIDDEN_KEYS = frozenset(
    {
        "intended_winner",
        "argument_map",
        "points",
        "key_point_ja",
        "summary_ja",
        "reason_ja",
        "level",
        "teacher_note",
    }
)


def build_script_check_session(script: dict) -> dict:
    """照合用の仮セッション。保存しない。設計の答えは入れない。

    elapsed_sec と time_limit_sec は null（タイムマネジメントは対象外）。
    speaker は ai。既存プロンプトでは ai の持ち時間を見ない。
    """
    parts = []
    for part in script.get("parts") or []:
        if not isinstance(part, dict):
            continue
        parts.append(
            {
                "part": part.get("part"),
                "side": part.get("side"),
                "speaker": "ai",
                "transcript_edited": part.get("text") or "",
                "elapsed_sec": None,
                "time_limit_sec": None,
                "pois": [],
            }
        )
    return {"motion": script.get("motion") or "", "mode": "duo", "parts": parts}


def forbidden_keys_in(value, path: str = "") -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{path}.{key}" if path else str(key)
            if key in SCRIPT_CHECK_FORBIDDEN_KEYS:
                found.append(here)
            found.extend(forbidden_keys_in(child, here))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(forbidden_keys_in(child, f"{path}[{index}]"))
    return found


def run_judge(session: dict, *, model_mode: str | None = None, include_usage: bool = False) -> dict:
    """LLMを呼び出し、正規化済みのジャッジ結果（新しい判定内容の各フィールド）を返す。

    戻り値はnew_judge_result()のうちstatus/error/started_at/judged_at/transcription_mode
    以外のフィールド（argument_flow, winner, score_total, scores,
    overall_feedback, part_feedback, model）を含む。
    model_mode を渡したときだけ、管理画面のジャッジモデルではなくそのモデルを使う。
    """
    client = _get_client()
    if not client:
        raise RuntimeError("OPENAI_API_KEYが設定されていないため、ジャッジを実行できません。")

    from debate.judge_models import resolve_judge_model_id, resolve_judge_model_metadata, resolve_judge_model_mode
    from debate.settings import load_settings, resolve_judge_model

    if model_mode:
        judge_mode = resolve_judge_model_mode(model_mode)
        judge_model = resolve_judge_model_id(judge_mode)
    else:
        settings = load_settings()
        judge_mode = resolve_judge_model_mode(settings.get("judge_model_mode"))
        judge_model = resolve_judge_model(judge_mode)
    judge_model_info = resolve_judge_model_metadata(judge_mode)
    payload = build_judge_payload(session)
    leaked = forbidden_keys_in(payload)
    if model_mode and leaked:
        raise RuntimeError("照合の入力に設計情報が入っています: " + ", ".join(leaked))
    if model_mode:
        part_keys = sorted((payload.get("parts") or [{}])[0].keys()) if payload.get("parts") else []
        logger.info(
            "Script check judge payload keys=%s part_keys=%s elapsed_sec=null time_limit_sec=null",
            sorted(payload.keys()),
            part_keys,
        )
    system_prompt = JUDGE_SYSTEM_PROMPT
    if payload.get("partial_practice"):
        system_prompt += PARTIAL_PRACTICE_ADDENDUM
    user_content = json.dumps(payload, ensure_ascii=False, indent=2)

    kwargs: dict = {
        "model": judge_model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
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
    if include_usage:
        result["usage"] = _completion_usage(completion, judge_mode, elapsed)
    logger.info("Judge finished in %.1fs (model=%s, winner=%s)", elapsed, judge_model, result.get("winner"))
    return result


def _completion_usage(completion, model_mode: str, elapsed: float) -> dict:
    from debate.judge_models import resolve_judge_model_metadata

    usage = getattr(completion, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else 0
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage is not None else 0
    meta = resolve_judge_model_metadata(model_mode)
    cost = (
        prompt_tokens * float(meta["input_price_per_1m"]) / 1_000_000
        + completion_tokens * float(meta["output_price_per_1m"]) / 1_000_000
    )
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": round(cost, 6),
        "seconds": round(elapsed, 1),
    }
