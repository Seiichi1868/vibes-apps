"""ストリーク・累計練習数・習得の純ロジック。

活用は人称（tú / él・ella・usted）ごとに連続正解を数え、それぞれが
しきい値に達した時点でその人称を習得とする。両方そろわなくても、
達した側の習得数は増える。
単語4択は方向（日→西 / 西→日）ごとにデフォルト5回連続正解でマスター。
間違えると連続カウントはゼロに戻るが、累計の間違い回数は残す。
活用の間違いは時制（現在・点過去・線過去）ごとに残す。しきい値は管理画面から渡す。
"""
from datetime import date, datetime, timedelta, timezone

from conjugate.data.conjugations import TENSE_ORDER
from conjugate.data.persons import PERSON_IDS, person_badge_text
from conjugate.data.verbs import VERBS, drillable_verbs

JST = timezone(timedelta(hours=9))
DEFAULT_CONJUGATION_THRESHOLD = 5
DEFAULT_VOCAB_THRESHOLD = 5

# 時制追加（点過去・線過去）に合わせ、この版より古い活用進捗は読み込み時に捨ててゼロから数える。
CONJUGATION_PROGRESS_VERSION = 1
# 間違いがこの回数を超えた時制は赤く表示する（5回ちょうどは通常色）。
MISS_ALERT_OVER = 5
MISS_DISPLAY_TENSES = (
    ("present", "現在"),
    ("preterite", "点過去"),
    ("imperfect", "線過去"),
)
DEFAULT_GUARDIAN_PRICE_COINS = 50
VOCAB_DIRECTIONS = ("ja_to_es", "es_to_ja")

# 暗記マスター（意味クイズ5回連続正解）がこの個数貯まるごとに、コイン消費なしでGuardiánを1体付与する。
DEFAULT_VOCAB_MASTER_BONUS_EVERY = 5

# Guardián進化（軽量RPG要素）。累計獲得コイン数（＝累計正解数）で見た目とセリフのみが変化する。
GUARDIAN_STAGES = (
    {
        "stage": 1,
        "min_coins_earned": 0,
        "title": "Aprendiz",
        "title_ja": "見習い",
        "quote_es": "¡No te rindas!",
        "quote_ja": "諦めないで！",
        "color": "#8BC34A",
    },
    {
        "stage": 2,
        "min_coins_earned": 150,
        "title": "Guerrero",
        "title_ja": "戦士",
        "quote_es": "¡Sigue adelante!",
        "quote_ja": "前進あるのみ！",
        "color": "#4A90D9",
    },
    {
        "stage": 3,
        "min_coins_earned": 400,
        "title": "Sabio",
        "title_ja": "賢者",
        "quote_es": "Tu esfuerzo no es en vano.",
        "quote_ja": "君の努力は無駄じゃない",
        "color": "#9B59B6",
    },
)


def guardian_stage_info(coins_earned_total: int) -> dict:
    """累計獲得コイン数から現在のGuardián進化段階（見た目・セリフ）を返す。"""
    total = max(0, int(coins_earned_total or 0))
    current = GUARDIAN_STAGES[0]
    for stage in GUARDIAN_STAGES:
        if total >= stage["min_coins_earned"]:
            current = stage
    return current


DEFAULT_PROGRESS = {
    "last_practice_date": None,
    "practice_dates": [],
    "daily_attempts": {},
    "daily_goal": 0,
    "current_streak": 0,
    "longest_streak": 0,
    "total_attempts": 0,
    "coins": 0,
    "coins_earned_total": 0,
    "guardian_count": 0,
    "guardian_dates": [],
    "vocab_master_total": 0,
    "conjugation_progress_version": CONJUGATION_PROGRESS_VERSION,
    "verbs": {},
    "vocab": {},
}


def today_jst(now: datetime | None = None) -> date:
    current = now or datetime.now(JST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=JST)
    return current.astimezone(JST).date()


def _blank_person_side() -> dict:
    return {"consecutive_correct": 0, "mastered": False}


def _person_streak(side) -> int:
    if not isinstance(side, dict):
        return 0
    return _as_nonneg_int(side.get("consecutive_correct"))


def _person_side_mastered(side, threshold: int) -> bool:
    if not isinstance(side, dict):
        return False
    limit = max(1, int(threshold or DEFAULT_CONJUGATION_THRESHOLD))
    return bool(side.get("mastered")) or _person_streak(side) >= limit


def _normalize_persons(entry: dict, tense_map: dict, legacy_mastered: bool) -> dict:
    """人称別連続カウント。旧データ（túのみ）は tú 側へ引き継ぐ。"""
    raw = entry.get("persons") if isinstance(entry.get("persons"), dict) else {}
    max_tense = 0
    for tense_entry in tense_map.values():
        max_tense = max(max_tense, _as_nonneg_int(tense_entry.get("consecutive_correct")))

    tu_raw = raw.get("tu") if isinstance(raw.get("tu"), dict) else {}
    el_raw = raw.get("el_ella_usted") if isinstance(raw.get("el_ella_usted"), dict) else {}

    tu_consec = _as_nonneg_int(tu_raw.get("consecutive_correct"))
    if tu_consec <= 0:
        tu_consec = max_tense
    tu_mastered = bool(tu_raw.get("mastered")) or legacy_mastered
    if tu_mastered:
        tu_consec = max(tu_consec, DEFAULT_CONJUGATION_THRESHOLD)

    el_consec = _as_nonneg_int(el_raw.get("consecutive_correct"))
    el_mastered = bool(el_raw.get("mastered"))

    return {
        "tu": {
            "consecutive_correct": tu_consec,
            "mastered": tu_mastered or tu_consec >= DEFAULT_CONJUGATION_THRESHOLD,
        },
        "el_ella_usted": {
            "consecutive_correct": el_consec,
            "mastered": el_mastered or el_consec >= DEFAULT_CONJUGATION_THRESHOLD,
        },
    }


def _as_nonneg_int(value, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _iso_date(value) -> str | None:
    text = str(value or "").strip()[:10]
    if len(text) != 10:
        return None
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def normalize_progress(raw: dict | None) -> dict:
    data = {
        "last_practice_date": None,
        "practice_dates": [],
        "daily_attempts": {},
        "daily_goal": 0,
        "current_streak": 0,
        "longest_streak": 0,
        "total_attempts": 0,
        "coins": 0,
        "coins_earned_total": 0,
        "guardian_count": 0,
        "guardian_dates": [],
        "vocab_master_total": 0,
        "conjugation_progress_version": CONJUGATION_PROGRESS_VERSION,
        "verbs": {},
        "vocab": {},
    }
    if not isinstance(raw, dict):
        return data

    last = _iso_date(raw.get("last_practice_date"))
    if last:
        data["last_practice_date"] = last

    dates = []
    seen = set()
    raw_dates = raw.get("practice_dates")
    if isinstance(raw_dates, list):
        for item in raw_dates:
            iso = _iso_date(item)
            if iso and iso not in seen:
                seen.add(iso)
                dates.append(iso)
    if last and last not in seen:
        dates.append(last)
    dates.sort()
    data["practice_dates"] = dates

    daily = raw.get("daily_attempts")
    if isinstance(daily, dict):
        cleaned_daily = {}
        for key, value in daily.items():
            iso = _iso_date(key)
            if iso:
                cleaned_daily[iso] = _as_nonneg_int(value)
        data["daily_attempts"] = cleaned_daily

    data["daily_goal"] = min(100, _as_nonneg_int(raw.get("daily_goal")))

    for key in ("current_streak", "longest_streak", "total_attempts", "coins", "guardian_count"):
        data[key] = _as_nonneg_int(raw.get(key))

    # 累計獲得コイン数（Guardián進化に使用）。旧データに無ければ現在の残高を初期値にする。
    data["coins_earned_total"] = _as_nonneg_int(
        raw.get("coins_earned_total"), default=data["coins"]
    )
    if data["coins_earned_total"] < data["coins"]:
        data["coins_earned_total"] = data["coins"]

    guardian_dates = []
    seen_guardian = set()
    raw_guardian_dates = raw.get("guardian_dates")
    if isinstance(raw_guardian_dates, list):
        for item in raw_guardian_dates:
            iso = _iso_date(item)
            if iso and iso not in seen_guardian:
                seen_guardian.add(iso)
                guardian_dates.append(iso)
    guardian_dates.sort()
    data["guardian_dates"] = guardian_dates

    stored_version = _as_nonneg_int(raw.get("conjugation_progress_version"))
    reset_conjugation = stored_version < CONJUGATION_PROGRESS_VERSION
    data["conjugation_progress_version"] = CONJUGATION_PROGRESS_VERSION

    verbs = raw.get("verbs")
    if isinstance(verbs, dict) and not reset_conjugation:
        cleaned = {}
        for verb_id, entry in verbs.items():
            if not isinstance(entry, dict):
                continue
            tense_map = {}
            max_correct = 0
            any_mastered = False
            for tense, tense_entry in entry.items():
                if tense not in TENSE_ORDER or not isinstance(tense_entry, dict):
                    continue
                consecutive = _as_nonneg_int(tense_entry.get("consecutive_correct"))
                t_correct = _as_nonneg_int(tense_entry.get("correct_count"), consecutive)
                t_correct = max(t_correct, consecutive)
                mastered = bool(tense_entry.get("mastered"))
                any_mastered = any_mastered or mastered
                max_correct = max(max_correct, t_correct)
                tense_map[tense] = {
                    "consecutive_correct": consecutive,
                    "correct_count": t_correct,
                    "miss_count": _as_nonneg_int(tense_entry.get("miss_count")),
                    "mastered": mastered,
                }
            verb_correct = max(_as_nonneg_int(entry.get("correct_count")), max_correct)
            # 旧仕様でマスター済みだった語は、tú側の進捗として保持する（él側は未着手のまま）
            legacy_mastered = any_mastered or bool(entry.get("mastered"))
            if legacy_mastered:
                verb_correct = max(verb_correct, DEFAULT_CONJUGATION_THRESHOLD)
            persons = _normalize_persons(entry, tense_map, legacy_mastered)
            both_mastered = _person_side_mastered(persons["tu"], DEFAULT_CONJUGATION_THRESHOLD) and _person_side_mastered(
                persons["el_ella_usted"], DEFAULT_CONJUGATION_THRESHOLD
            )
            row = {
                "correct_count": verb_correct,
                "mastered": both_mastered,
                "persons": persons,
            }
            row.update(tense_map)
            cleaned[str(verb_id)] = row
        data["verbs"] = cleaned

    vocab = raw.get("vocab")
    if isinstance(vocab, dict):
        cleaned_vocab = {}
        for verb_id, entry in vocab.items():
            if not isinstance(entry, dict):
                continue
            cleaned_vocab[str(verb_id)] = _normalize_vocab_entry(entry)
        data["vocab"] = cleaned_vocab

    # 暗記マスター累計数。旧データに無ければ既存のマスター済み数から算出し、
    # 移行時にまとめてGuardiánボーナスが発生しないようにする。
    if "vocab_master_total" in raw:
        data["vocab_master_total"] = _as_nonneg_int(raw.get("vocab_master_total"))
    else:
        data["vocab_master_total"] = total_vocab_master_count(data, DEFAULT_VOCAB_THRESHOLD)
    return data


def _vocab_side(raw_side, fallback: int = 0) -> dict:
    consecutive = 0
    mastered = False
    miss_count = 0
    if isinstance(raw_side, dict):
        consecutive = _as_nonneg_int(raw_side.get("consecutive_correct"))
        if consecutive <= 0 and "consecutive_correct" not in raw_side:
            consecutive = _as_nonneg_int(raw_side.get("correct_count"))
        mastered = bool(raw_side.get("mastered"))
        miss_count = _as_nonneg_int(raw_side.get("miss_count"))
    if consecutive <= 0:
        consecutive = fallback
    mastered = mastered or consecutive >= DEFAULT_VOCAB_THRESHOLD
    return {
        "consecutive_correct": consecutive,
        "correct_count": consecutive,
        "miss_count": miss_count,
        "mastered": mastered,
    }


def _normalize_vocab_entry(entry: dict) -> dict:
    legacy = _as_nonneg_int(entry.get("correct_count"))
    has_sides = any(isinstance(entry.get(direction), dict) for direction in VOCAB_DIRECTIONS)
    fallback = 0 if has_sides else legacy
    sides = {direction: _vocab_side(entry.get(direction), fallback) for direction in VOCAB_DIRECTIONS}
    total = sum(side["correct_count"] for side in sides.values())
    total_miss = sum(side["miss_count"] for side in sides.values())
    row = {
        "correct_count": total,
        "miss_count": total_miss,
        "mastered": any(side["mastered"] for side in sides.values()),
    }
    row.update(sides)
    return row


def apply_streak(progress: dict, today: date) -> dict:
    """練習日を反映する。

    ストリークが途切れる日（前日は練習済みだが間に未練習日がある）には、
    Guardián保有数を1日1体まで消費して自動的にストリークを守る。
    ギャップの日数分の保有数が無ければ、その時点でストリークはリセットされる。

    戻り値:
      streak_incremented: 同日2回目以降の呼び出しならFalse、新しい日ならTrue
      guardian_used: 今回の呼び出しで消費したGuardián数
      guardian_dates_used: 今回新たにGuardiánで守られた日付（ISO文字列）のリスト
      streak_broken: ギャップをカバーしきれずストリークがリセットされたか
    """
    last_raw = progress.get("last_practice_date")
    last_date = None
    if last_raw:
        try:
            last_date = date.fromisoformat(str(last_raw)[:10])
        except ValueError:
            last_date = None

    iso = today.isoformat()
    dates = progress.setdefault("practice_dates", [])
    if iso not in dates:
        dates.append(iso)
        dates.sort()

    if last_date == today:
        return {
            "streak_incremented": False,
            "guardian_used": 0,
            "guardian_dates_used": [],
            "streak_broken": False,
        }

    guardian_used = 0
    guardian_dates_used: list[str] = []
    streak_continues = last_date is None or last_date == today - timedelta(days=1)

    if last_date is not None and not streak_continues:
        gap_days = (today - last_date).days - 1
        guardian_count = int(progress.get("guardian_count") or 0)
        covered_all = True
        for i in range(gap_days):
            if guardian_count <= 0:
                covered_all = False
                break
            guardian_count -= 1
            guardian_used += 1
            guardian_dates_used.append((last_date + timedelta(days=1 + i)).isoformat())
        progress["guardian_count"] = guardian_count
        if guardian_dates_used:
            guardian_dates = progress.setdefault("guardian_dates", [])
            for d in guardian_dates_used:
                if d not in guardian_dates:
                    guardian_dates.append(d)
            guardian_dates.sort()
        streak_continues = covered_all

    if last_date is None:
        progress["current_streak"] = 1
    elif streak_continues:
        progress["current_streak"] = int(progress.get("current_streak") or 0) + 1
    else:
        progress["current_streak"] = 1

    progress["longest_streak"] = max(
        int(progress.get("longest_streak") or 0),
        int(progress["current_streak"]),
    )
    progress["last_practice_date"] = iso
    return {
        "streak_incremented": True,
        "guardian_used": guardian_used,
        "guardian_dates_used": guardian_dates_used,
        "streak_broken": last_date is not None and not streak_continues,
    }


def apply_mastery(
    progress: dict,
    verb_id,
    tense: str | None,
    is_correct: bool,
    threshold: int = DEFAULT_CONJUGATION_THRESHOLD,
    person: str | None = "tu",
) -> bool:
    """人称別の連続正解を更新。その人称が新たに習得へ達したら True。

    tú と él/ella/usted は別カウント。片方だけでは動詞全体の mastered にはならない。
    間違いは出題した時制の miss_count に残す。
    """
    if verb_id is None:
        return False
    try:
        key = str(int(verb_id))
    except (TypeError, ValueError):
        return False

    threshold = max(1, int(threshold or DEFAULT_CONJUGATION_THRESHOLD))
    person_key = person if person in PERSON_IDS else "tu"
    verbs = progress.setdefault("verbs", {})
    entry = verbs.setdefault(
        key,
        {
            "correct_count": 0,
            "mastered": False,
            "persons": {"tu": _blank_person_side(), "el_ella_usted": _blank_person_side()},
        },
    )
    entry.setdefault("persons", {"tu": _blank_person_side(), "el_ella_usted": _blank_person_side()})
    for pid in PERSON_IDS:
        entry["persons"].setdefault(pid, _blank_person_side())

    if tense in TENSE_ORDER:
        tense_entry = entry.setdefault(
            tense,
            {"consecutive_correct": 0, "correct_count": 0, "miss_count": 0, "mastered": False},
        )
        tense_entry["miss_count"] = _as_nonneg_int(tense_entry.get("miss_count"))
        if is_correct:
            tense_entry["consecutive_correct"] = int(tense_entry.get("consecutive_correct") or 0) + 1
            tense_entry["correct_count"] = int(tense_entry.get("correct_count") or 0) + 1
        else:
            tense_entry["consecutive_correct"] = 0
            tense_entry["miss_count"] += 1
        entry[tense] = tense_entry

    side = entry["persons"][person_key]
    was_side_mastered = _person_side_mastered(side, threshold)
    if is_correct:
        side["consecutive_correct"] = int(side.get("consecutive_correct") or 0) + 1
        entry["correct_count"] = int(entry.get("correct_count") or 0) + 1
    else:
        side["consecutive_correct"] = 0
    if side["consecutive_correct"] >= threshold:
        side["mastered"] = True
    entry["persons"][person_key] = side

    entry["mastered"] = verb_is_mastered(entry, threshold)
    if tense in TENSE_ORDER:
        entry[tense]["mastered"] = entry["mastered"]
    verbs[key] = entry
    return _person_side_mastered(side, threshold) and not was_side_mastered


def _vocab_streak(side) -> int:
    if not isinstance(side, dict):
        return 0
    if "consecutive_correct" in side:
        return _as_nonneg_int(side.get("consecutive_correct"))
    return _as_nonneg_int(side.get("correct_count"))


def _vocab_side_mastered(side, threshold: int) -> bool:
    if not isinstance(side, dict):
        return False
    return bool(side.get("mastered")) or _vocab_streak(side) >= threshold


def apply_vocab_mastery(
    progress: dict,
    verb_id,
    is_correct: bool,
    threshold: int = DEFAULT_VOCAB_THRESHOLD,
    direction: str | None = None,
) -> bool:
    """単語クイズの方向別連続正解を更新。新たにマスターしたら True。

    方向が不明なときは、反対側のカウントを誤って増やさないよう何もしない。
    """
    if verb_id is None:
        return False
    try:
        key = str(int(verb_id))
    except (TypeError, ValueError):
        return False

    if direction not in VOCAB_DIRECTIONS:
        return False
    side_key = direction
    threshold = max(1, int(threshold or DEFAULT_VOCAB_THRESHOLD))
    vocab = progress.setdefault("vocab", {})
    entry = vocab.setdefault(key, _normalize_vocab_entry({}))
    blank_side = {"consecutive_correct": 0, "correct_count": 0, "miss_count": 0, "mastered": False}
    for direction_id in VOCAB_DIRECTIONS:
        entry.setdefault(direction_id, dict(blank_side))
    side = entry[side_key]
    was_mastered = _vocab_side_mastered(side, threshold)
    streak = _vocab_streak(side)
    if is_correct:
        streak += 1
    else:
        streak = 0
        side["miss_count"] = _as_nonneg_int(side.get("miss_count")) + 1
    side["consecutive_correct"] = streak
    side["correct_count"] = streak
    side["mastered"] = was_mastered or streak >= threshold
    entry[side_key] = side
    entry["correct_count"] = sum(_vocab_streak(entry.get(d)) for d in VOCAB_DIRECTIONS)
    entry["miss_count"] = sum(
        _as_nonneg_int((entry.get(d) or {}).get("miss_count")) for d in VOCAB_DIRECTIONS
    )
    entry["mastered"] = any(_vocab_side_mastered(entry.get(d), threshold) for d in VOCAB_DIRECTIONS)
    vocab[key] = entry
    return bool(side["mastered"]) and not was_mastered


def can_afford_guardian(progress: dict, price: int = DEFAULT_GUARDIAN_PRICE_COINS) -> bool:
    """コイン残高がGuardián交換価格以上あるか。"""
    price = max(1, int(price or DEFAULT_GUARDIAN_PRICE_COINS))
    return int(progress.get("coins") or 0) >= price


def apply_guardian_purchase(progress: dict, price: int = DEFAULT_GUARDIAN_PRICE_COINS) -> bool:
    """コインを消費してGuardiánを1体購入する（発動ロジックはPart 2）。

    残高不足の場合は何も変更せずFalseを返す。
    """
    price = max(1, int(price or DEFAULT_GUARDIAN_PRICE_COINS))
    coins = int(progress.get("coins") or 0)
    if coins < price:
        return False
    progress["coins"] = coins - price
    progress["guardian_count"] = int(progress.get("guardian_count") or 0) + 1
    return True


def apply_attempt(
    progress: dict,
    *,
    verb_id=None,
    tense: str | None = None,
    is_correct: bool = False,
    today: date | None = None,
    kind: str = "conjugation",
    threshold: int | None = None,
    direction: str | None = None,
    person: str | None = None,
) -> dict:
    """1回の判定を進捗に反映する。"""
    today = today or today_jst()
    iso = today.isoformat()
    progress["total_attempts"] = int(progress.get("total_attempts") or 0) + 1
    daily = progress.setdefault("daily_attempts", {})
    daily[iso] = int(daily.get(iso) or 0) + 1
    streak_result = apply_streak(progress, today)

    if is_correct:
        progress["coins"] = int(progress.get("coins") or 0) + 1
        progress["coins_earned_total"] = int(progress.get("coins_earned_total") or 0) + 1

    guardian_bonus_awarded = 0
    if kind == "vocab":
        vocab_threshold = threshold if threshold is not None else DEFAULT_VOCAB_THRESHOLD
        newly_mastered = apply_vocab_mastery(
            progress, verb_id, is_correct, vocab_threshold, direction=direction
        )
        if newly_mastered:
            progress["vocab_master_total"] = int(progress.get("vocab_master_total") or 0) + 1
            if progress["vocab_master_total"] % DEFAULT_VOCAB_MASTER_BONUS_EVERY == 0:
                progress["guardian_count"] = int(progress.get("guardian_count") or 0) + 1
                guardian_bonus_awarded = 1
        conj_threshold = DEFAULT_CONJUGATION_THRESHOLD
    else:
        conj_threshold = threshold if threshold is not None else DEFAULT_CONJUGATION_THRESHOLD
        newly_mastered = apply_mastery(
            progress, verb_id, tense, is_correct, conj_threshold, person=person
        )

    return {
        "streak_incremented": streak_result["streak_incremented"],
        "streak_broken": streak_result["streak_broken"],
        "guardian_used": streak_result["guardian_used"],
        "guardian_dates_used": streak_result["guardian_dates_used"],
        "guardian_bonus_awarded": guardian_bonus_awarded,
        "newly_mastered": newly_mastered,
        "current_streak": int(progress.get("current_streak") or 0),
        "longest_streak": int(progress.get("longest_streak") or 0),
        "total_attempts": int(progress.get("total_attempts") or 0),
        "mastered_count": mastered_verb_count(progress, conj_threshold),
        "coins": int(progress.get("coins") or 0),
        "coin_earned": bool(is_correct),
        "guardian_count": int(progress.get("guardian_count") or 0),
    }


def verb_is_mastered(entry: dict | None, threshold: int = DEFAULT_CONJUGATION_THRESHOLD) -> bool:
    if not isinstance(entry, dict):
        return False
    persons = entry.get("persons") if isinstance(entry.get("persons"), dict) else {}
    if persons:
        return _person_side_mastered(persons.get("tu"), threshold) and _person_side_mastered(
            persons.get("el_ella_usted"), threshold
        )
    return False


def mastered_person_count(
    progress: dict,
    person: str,
    threshold: int = DEFAULT_CONJUGATION_THRESHOLD,
) -> int:
    """1つの人称について、習得済みの動詞数を返す。"""
    if person not in PERSON_IDS:
        return 0
    verbs = progress.get("verbs") or {}
    limit = max(1, int(threshold or DEFAULT_CONJUGATION_THRESHOLD))
    count = 0
    for verb in drillable_verbs():
        entry = verbs.get(str(verb["id"])) or {}
        persons = entry.get("persons") if isinstance(entry.get("persons"), dict) else {}
        if _person_side_mastered(persons.get(person), limit):
            count += 1
    return count


def mastered_verb_count(progress: dict, threshold: int = DEFAULT_CONJUGATION_THRESHOLD) -> int:
    verbs = progress.get("verbs") or {}
    count = 0
    for verb in drillable_verbs():
        if verb_is_mastered(verbs.get(str(verb["id"])), threshold):
            count += 1
    return count


def mastered_vocab_count(
    progress: dict,
    threshold: int = DEFAULT_VOCAB_THRESHOLD,
    direction: str | None = None,
) -> int:
    vocab = progress.get("vocab") or {}
    limit = max(1, int(threshold or DEFAULT_VOCAB_THRESHOLD))
    count = 0
    for verb in VERBS:
        entry = vocab.get(str(verb["id"])) or {}
        if direction in VOCAB_DIRECTIONS:
            if _vocab_side_mastered(entry.get(direction), limit):
                count += 1
        elif any(_vocab_side_mastered(entry.get(d), limit) for d in VOCAB_DIRECTIONS):
            count += 1
    return count


def total_vocab_master_count(
    progress: dict,
    threshold: int = DEFAULT_VOCAB_THRESHOLD,
) -> int:
    """日→西・西→日の両方向を合算した暗記マスター数（Guardiánボーナス判定に使用）。"""
    vocab = progress.get("vocab") or {}
    limit = max(1, int(threshold or DEFAULT_VOCAB_THRESHOLD))
    total = 0
    for entry in vocab.values():
        for direction in VOCAB_DIRECTIONS:
            if _vocab_side_mastered(entry.get(direction) if isinstance(entry, dict) else None, limit):
                total += 1
    return total


def tense_miss_view(tenses: dict | None) -> list[dict]:
    """現在・点過去・線過去の累計間違い回数。5回を超えると alert。"""
    source = tenses if isinstance(tenses, dict) else {}
    rows = []
    for tense_id, label in MISS_DISPLAY_TENSES:
        entry = source.get(tense_id)
        count = _as_nonneg_int(entry.get("miss_count") if isinstance(entry, dict) else 0)
        rows.append(
            {
                "id": tense_id,
                "label": label,
                "miss_count": count,
                "alert": count > MISS_ALERT_OVER,
            }
        )
    return rows


def learner_level(mastered_count: int) -> int:
    return max(1, 1 + max(0, int(mastered_count)) // 5)


def progress_view(
    progress: dict,
    *,
    conjugation_threshold: int = DEFAULT_CONJUGATION_THRESHOLD,
    vocab_threshold: int = DEFAULT_VOCAB_THRESHOLD,
    guardian_price: int = DEFAULT_GUARDIAN_PRICE_COINS,
) -> dict:
    conj_th = max(1, int(conjugation_threshold or DEFAULT_CONJUGATION_THRESHOLD))
    vocab_th = max(1, int(vocab_threshold or DEFAULT_VOCAB_THRESHOLD))
    guardian_price = max(1, int(guardian_price or DEFAULT_GUARDIAN_PRICE_COINS))
    coins = int(progress.get("coins") or 0)
    coins_earned_total = int(progress.get("coins_earned_total") or 0)
    guardian_count = int(progress.get("guardian_count") or 0)
    guardian_dates = list(progress.get("guardian_dates") or [])
    stage_info = guardian_stage_info(coins_earned_total)
    mastered = mastered_verb_count(progress, conj_th)
    mastered_tu = mastered_person_count(progress, "tu", conj_th)
    mastered_el = mastered_person_count(progress, "el_ella_usted", conj_th)
    vocab_mastered = mastered_vocab_count(progress, vocab_th)
    vocab_mastered_ja = mastered_vocab_count(progress, vocab_th, "ja_to_es")
    vocab_mastered_es = mastered_vocab_count(progress, vocab_th, "es_to_ja")
    total_verbs = len(drillable_verbs())
    total_vocab = len(VERBS)
    last = progress.get("last_practice_date")
    practiced_today = last == today_jst().isoformat()
    percent = round((mastered / total_verbs) * 100) if total_verbs else 0
    tu_percent = round((mastered_tu / total_verbs) * 100) if total_verbs else 0
    el_percent = round((mastered_el / total_verbs) * 100) if total_verbs else 0
    track_percent = round((tu_percent + el_percent) / 2) if total_verbs else 0
    daily_goal = min(100, _as_nonneg_int(progress.get("daily_goal")))
    return {
        "last_practice_date": last,
        "practice_dates": list(progress.get("practice_dates") or []),
        "daily_attempts": dict(progress.get("daily_attempts") or {}),
        "daily_goal": daily_goal,
        "current_streak": int(progress.get("current_streak") or 0),
        "longest_streak": int(progress.get("longest_streak") or 0),
        "total_attempts": int(progress.get("total_attempts") or 0),
        "mastered_count": mastered,
        "mastered_tu_count": mastered_tu,
        "mastered_el_count": mastered_el,
        "total_verbs": total_verbs,
        "mastered_percent": percent,
        "mastered_tu_percent": tu_percent,
        "mastered_el_percent": el_percent,
        "mastered_track_percent": track_percent,
        "miss_alert_over": MISS_ALERT_OVER,
        "vocab_mastered_count": vocab_mastered,
        "vocab_mastered_ja_to_es": vocab_mastered_ja,
        "vocab_mastered_es_to_ja": vocab_mastered_es,
        "total_vocab": total_vocab,
        "conjugation_threshold": conj_th,
        "vocab_threshold": vocab_th,
        "practiced_today": practiced_today,
        "level": learner_level(mastered),
        "xp": mastered * 10,
        "coins": coins,
        "coins_earned_total": coins_earned_total,
        "guardian_count": guardian_count,
        "guardian_price": guardian_price,
        "guardian_coins_needed": max(0, guardian_price - coins),
        "can_afford_guardian": coins >= guardian_price,
        "guardian_dates": guardian_dates,
        "guardian_stage": stage_info["stage"],
        "guardian_title": stage_info["title"],
        "guardian_title_ja": stage_info["title_ja"],
        "guardian_quote_es": stage_info["quote_es"],
        "guardian_quote_ja": stage_info["quote_ja"],
        "guardian_color": stage_info["color"],
        "guardian_stages": [
            {
                "stage": s["stage"],
                "title": s["title"],
                "title_ja": s["title_ja"],
                "min_coins_earned": s["min_coins_earned"],
                "color": s["color"],
            }
            for s in GUARDIAN_STAGES
        ],
        "vocab_master_total": int(progress.get("vocab_master_total") or 0),
        "vocab_master_bonus_every": DEFAULT_VOCAB_MASTER_BONUS_EVERY,
    }


def verb_progress_list(
    progress: dict,
    threshold: int = DEFAULT_CONJUGATION_THRESHOLD,
) -> list[dict]:
    verbs_data = progress.get("verbs") or {}
    limit = max(1, int(threshold or DEFAULT_CONJUGATION_THRESHOLD))
    rows = []
    for verb in drillable_verbs():
        entry = verbs_data.get(str(verb["id"])) or {}
        tenses = {}
        for tense in TENSE_ORDER:
            tense_entry = entry.get(tense) or {}
            tenses[tense] = {
                "consecutive_correct": int(tense_entry.get("consecutive_correct") or 0),
                "correct_count": int(tense_entry.get("correct_count") or 0),
                "miss_count": _as_nonneg_int(tense_entry.get("miss_count")),
                "mastered": bool(tense_entry.get("mastered")),
            }
        persons_raw = entry.get("persons") if isinstance(entry.get("persons"), dict) else {}
        persons = {}
        for pid in PERSON_IDS:
            side = persons_raw.get(pid) or {}
            streak = _person_streak(side)
            side_mastered = _person_side_mastered(side, limit)
            persons[pid] = {
                "consecutive_correct": streak,
                "correct_count": streak,
                "mastered": side_mastered,
            }
        mastered = persons["tu"]["mastered"] and persons["el_ella_usted"]["mastered"]
        tense_misses = tense_miss_view(tenses)
        rows.append(
            {
                "id": verb["id"],
                "infinitive": verb["infinitive"],
                "meaning_ja": verb["meaning_ja"],
                "category": verb["category"],
                "correct_count": _as_nonneg_int(entry.get("correct_count")),
                "threshold": limit,
                "mastered": mastered,
                "consecutive_correct": tenses["present"]["consecutive_correct"],
                "tenses": tenses,
                "tense_misses": tense_misses,
                "miss_total": sum(item["miss_count"] for item in tense_misses),
                "persons": persons,
                "person_badge": person_badge_text(
                    tu_mastered=persons["tu"]["mastered"],
                    el_mastered=persons["el_ella_usted"]["mastered"],
                    threshold=limit,
                    tu_count=persons["tu"]["consecutive_correct"],
                    el_count=persons["el_ella_usted"]["consecutive_correct"],
                ),
            }
        )
    return rows


def vocab_progress_list(
    progress: dict,
    threshold: int = DEFAULT_VOCAB_THRESHOLD,
) -> list[dict]:
    vocab_data = progress.get("vocab") or {}
    limit = max(1, int(threshold or DEFAULT_VOCAB_THRESHOLD))
    rows = []
    for verb in VERBS:
        entry = vocab_data.get(str(verb["id"])) or {}
        sides = {}
        for direction in VOCAB_DIRECTIONS:
            side = entry.get(direction) or {}
            streak = _vocab_streak(side)
            mastered = _vocab_side_mastered(side, limit)
            miss_count = _as_nonneg_int(side.get("miss_count"))
            sides[direction] = {
                "consecutive_correct": streak,
                "correct_count": max(streak, limit) if mastered else streak,
                "miss_count": miss_count,
                "mastered": mastered,
            }
        rows.append(
            {
                "id": verb["id"],
                "infinitive": verb["infinitive"],
                "meaning_ja": verb["meaning_ja"],
                "category": verb["category"],
                "correct_count": sides["ja_to_es"]["correct_count"] + sides["es_to_ja"]["correct_count"],
                "miss_count": sides["ja_to_es"]["miss_count"] + sides["es_to_ja"]["miss_count"],
                "threshold": limit,
                "mastered": sides["ja_to_es"]["mastered"] or sides["es_to_ja"]["mastered"],
                "ja_to_es": sides["ja_to_es"],
                "es_to_ja": sides["es_to_ja"],
            }
        )
    return rows
