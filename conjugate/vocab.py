"""登録動詞の意味を4択で練習する語彙クイズ。

通常の活用ドリルとは独立。日本語→スペイン語 / スペイン語→日本語の両方向。
"""
import random
import uuid
from collections import Counter

from conjugate.data.verbs import VERBS
from conjugate.storage import record_progress

DIRECTIONS = ("ja_to_es", "es_to_ja")
DIRECTION_LABELS = {
    "ja_to_es": "日本語 → スペイン語",
    "es_to_ja": "スペイン語 → 日本語",
}
DEFAULT_VOCAB_COUNT = 10


def vocab_verbs() -> list[dict]:
    """意味クイズ対象。gustar も含めた登録動詞すべて。"""
    return list(VERBS)


def _unique_meaning_verbs(pool: list[dict]) -> list[dict]:
    counts = Counter(v["meaning_ja"] for v in pool)
    return [v for v in pool if counts[v["meaning_ja"]] == 1]


def _choice_key(direction: str) -> str:
    return "infinitive" if direction == "ja_to_es" else "meaning_ja"


def _prompt_text(verb: dict, direction: str) -> str:
    return verb["meaning_ja"] if direction == "ja_to_es" else verb["infinitive"]


def _pick_distractors(correct: dict, pool: list[dict], key: str, n: int = 3) -> list[dict]:
    correct_label = correct[key]
    same_cat = [v for v in pool if v["id"] != correct["id"] and v["category"] == correct["category"]]
    others = [v for v in pool if v["id"] != correct["id"] and v["category"] != correct["category"]]
    random.shuffle(same_cat)
    random.shuffle(others)

    picked = []
    seen = {correct_label}
    for verb in same_cat + others:
        label = verb[key]
        if label in seen:
            continue
        seen.add(label)
        picked.append(verb)
        if len(picked) >= n:
            break
    return picked


def build_vocab_questions(direction: str, count: int = DEFAULT_VOCAB_COUNT) -> list[dict]:
    if direction not in DIRECTIONS:
        direction = "ja_to_es"

    pool = vocab_verbs()
    key = _choice_key(direction)
    if direction == "ja_to_es":
        candidates = _unique_meaning_verbs(pool)
        if len(candidates) < 4:
            candidates = pool
    else:
        candidates = pool

    if len(candidates) < 4:
        return []

    count = max(4, min(20, int(count)))
    random.shuffle(candidates)
    if len(candidates) >= count:
        chosen = candidates[:count]
    else:
        chosen = list(candidates)
        while len(chosen) < count:
            extra = random.choice(candidates)
            if extra not in chosen or len(chosen) >= len(candidates):
                chosen.append(extra)

    questions = []
    for verb in chosen:
        distractors = _pick_distractors(verb, pool, key, n=3)
        if len(distractors) < 3:
            continue
        options = [verb] + distractors
        random.shuffle(options)
        choice_ids = [uuid.uuid4().hex[:8] for _ in options]
        correct_idx = next(i for i, opt in enumerate(options) if opt["id"] == verb["id"])
        questions.append(
            {
                "question_id": uuid.uuid4().hex[:10],
                "kind": "vocab",
                "verb_id": verb["id"],
                "infinitive": verb["infinitive"],
                "meaning_ja": verb["meaning_ja"],
                "direction": direction,
                "prompt": _prompt_text(verb, direction),
                "choices": [{"id": cid, "label": opt[key]} for cid, opt in zip(choice_ids, options)],
                "correct_choice_id": choice_ids[correct_idx],
                "answer": None,
            }
        )
    return questions


def public_vocab_question(question: dict) -> dict:
    """クライアントへ正解IDを隠したバージョン。解答後は正解も返す。"""
    q = {
        "question_id": question["question_id"],
        "kind": "vocab",
        "direction": question["direction"],
        "prompt": question["prompt"],
        "choices": list(question["choices"]),
        "answer": None,
    }
    if question.get("answer"):
        q["answer"] = dict(question["answer"])
        q["correct_choice_id"] = question["correct_choice_id"]
        q["infinitive"] = question.get("infinitive", "")
        q["meaning_ja"] = question.get("meaning_ja", "")
    return q


def grade_vocab_choice(question: dict, choice_id: str) -> dict:
    correct_id = question["correct_choice_id"]
    is_correct = choice_id == correct_id
    chosen = next((c for c in question["choices"] if c["id"] == choice_id), None)
    correct_choice = next((c for c in question["choices"] if c["id"] == correct_id), None)
    progress = record_progress(
        verb_id=question.get("verb_id"),
        tense=None,
        is_correct=is_correct,
        kind="vocab",
        direction=question.get("direction"),
    )
    result = {
        "correct": is_correct,
        "choice_id": choice_id,
        "chosen_label": (chosen or {}).get("label", ""),
        "correct_choice_id": correct_id,
        "correct_label": (correct_choice or {}).get("label", ""),
        "infinitive": question.get("infinitive", ""),
        "meaning_ja": question.get("meaning_ja", ""),
        "message": "正解！" if is_correct else f"不正解。正解は「{(correct_choice or {}).get('label', '')}」です。",
        "newly_mastered": bool(progress.get("newly_mastered")),
        "progress": progress,
    }
    return result


def build_vocab_summary(session: dict) -> dict:
    total = 0
    correct = 0
    weak_items = []
    for q in session.get("questions", []):
        ans = q.get("answer")
        if not ans:
            continue
        total += 1
        if ans.get("correct"):
            correct += 1
        else:
            weak_items.append(
                {
                    "verb_id": q.get("verb_id"),
                    "infinitive": q.get("infinitive", ""),
                    "meaning_ja": q.get("meaning_ja", ""),
                    "prompt": q.get("prompt", ""),
                    "chosen_label": ans.get("chosen_label", ""),
                    "correct_label": ans.get("correct_label", ""),
                    "miss_count": 0,
                }
            )
    accuracy = round((correct / total) * 100, 1) if total else 0.0
    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "weak_items": weak_items,
        "direction": session.get("direction", "ja_to_es"),
        "direction_label": DIRECTION_LABELS.get(session.get("direction", ""), ""),
    }
