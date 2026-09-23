"""ストリーク・習得ロジックの単体テスト。"""
import unittest
from datetime import date

from conjugate.progress import (
    apply_attempt,
    apply_guardian_purchase,
    apply_mastery,
    apply_streak,
    apply_vocab_mastery,
    can_afford_guardian,
    guardian_stage_info,
    learner_level,
    mastered_person_count,
    mastered_verb_count,
    normalize_progress,
    progress_view,
    tense_miss_view,
    total_vocab_master_count,
    verb_is_mastered,
    verb_progress_list,
    vocab_progress_list,
)


class StreakTests(unittest.TestCase):
    def test_first_practice_starts_at_one(self):
        progress = normalize_progress({})
        today = date(2026, 8, 15)
        result = apply_streak(progress, today)
        self.assertTrue(result["streak_incremented"])
        self.assertEqual(result["guardian_used"], 0)
        self.assertFalse(result["streak_broken"])
        self.assertEqual(progress["current_streak"], 1)
        self.assertEqual(progress["longest_streak"], 1)
        self.assertEqual(progress["last_practice_date"], "2026-08-15")
        self.assertEqual(progress["practice_dates"], ["2026-08-15"])

    def test_same_day_does_not_increment(self):
        progress = {
            "last_practice_date": "2026-08-15",
            "practice_dates": ["2026-08-15"],
            "current_streak": 4,
            "longest_streak": 6,
        }
        result = apply_streak(progress, date(2026, 8, 15))
        self.assertFalse(result["streak_incremented"])
        self.assertEqual(progress["current_streak"], 4)

    def test_yesterday_increments(self):
        progress = {
            "last_practice_date": "2026-08-14",
            "current_streak": 4,
            "longest_streak": 4,
        }
        result = apply_streak(progress, date(2026, 8, 15))
        self.assertTrue(result["streak_incremented"])
        self.assertEqual(progress["current_streak"], 5)
        self.assertEqual(progress["longest_streak"], 5)
        self.assertIn("2026-08-15", progress["practice_dates"])

    def test_gap_resets_to_one_without_guardian(self):
        progress = {
            "last_practice_date": "2026-08-10",
            "current_streak": 9,
            "longest_streak": 9,
            "guardian_count": 0,
        }
        result = apply_streak(progress, date(2026, 8, 15))
        self.assertTrue(result["streak_broken"])
        self.assertEqual(result["guardian_used"], 0)
        self.assertEqual(progress["current_streak"], 1)
        self.assertEqual(progress["longest_streak"], 9)


class GuardianStreakTests(unittest.TestCase):
    def test_single_day_gap_consumes_one_guardian_and_keeps_streak(self):
        progress = {
            "last_practice_date": "2026-08-14",
            "current_streak": 4,
            "longest_streak": 4,
            "guardian_count": 2,
        }
        result = apply_streak(progress, date(2026, 8, 16))
        self.assertTrue(result["streak_incremented"])
        self.assertFalse(result["streak_broken"])
        self.assertEqual(result["guardian_used"], 1)
        self.assertEqual(result["guardian_dates_used"], ["2026-08-15"])
        self.assertEqual(progress["current_streak"], 5)
        self.assertEqual(progress["guardian_count"], 1)
        self.assertEqual(progress["guardian_dates"], ["2026-08-15"])

    def test_two_day_gap_consumes_two_guardians(self):
        progress = {
            "last_practice_date": "2026-08-10",
            "current_streak": 3,
            "longest_streak": 3,
            "guardian_count": 2,
        }
        result = apply_streak(progress, date(2026, 8, 13))
        self.assertTrue(result["streak_incremented"])
        self.assertFalse(result["streak_broken"])
        self.assertEqual(result["guardian_used"], 2)
        self.assertEqual(result["guardian_dates_used"], ["2026-08-11", "2026-08-12"])
        self.assertEqual(progress["current_streak"], 4)
        self.assertEqual(progress["guardian_count"], 0)

    def test_insufficient_guardians_break_streak_but_spend_available(self):
        progress = {
            "last_practice_date": "2026-08-10",
            "current_streak": 3,
            "longest_streak": 3,
            "guardian_count": 1,
        }
        result = apply_streak(progress, date(2026, 8, 13))
        self.assertTrue(result["streak_broken"])
        self.assertEqual(result["guardian_used"], 1)
        self.assertEqual(result["guardian_dates_used"], ["2026-08-11"])
        self.assertEqual(progress["current_streak"], 1)
        self.assertEqual(progress["guardian_count"], 0)
        self.assertEqual(progress["guardian_dates"], ["2026-08-11"])

    def test_vocab_mastery_bonus_every_five_grants_guardian(self):
        progress = normalize_progress({})
        today = date(2026, 8, 19)
        verb_ids = [1, 2, 3, 4, 5]
        for verb_id in verb_ids:
            for _ in range(4):
                apply_attempt(
                    progress,
                    verb_id=verb_id,
                    is_correct=True,
                    today=today,
                    kind="vocab",
                    direction="ja_to_es",
                    threshold=5,
                )
            self.assertEqual(progress["guardian_count"], 0)
            delta = apply_attempt(
                progress,
                verb_id=verb_id,
                is_correct=True,
                today=today,
                kind="vocab",
                direction="ja_to_es",
                threshold=5,
            )
        self.assertEqual(progress["vocab_master_total"], 5)
        self.assertEqual(progress["guardian_count"], 1)
        self.assertEqual(delta["guardian_bonus_awarded"], 1)

    def test_vocab_mastery_bonus_counts_both_directions(self):
        progress = normalize_progress({})
        today = date(2026, 8, 19)
        for direction in ("ja_to_es", "es_to_ja"):
            for _ in range(5):
                apply_attempt(
                    progress,
                    verb_id=1,
                    is_correct=True,
                    today=today,
                    kind="vocab",
                    direction=direction,
                    threshold=5,
                )
        self.assertEqual(progress["vocab_master_total"], 2)
        self.assertEqual(total_vocab_master_count(progress, 5), 2)
        self.assertEqual(progress["guardian_count"], 0)

    def test_guardian_stage_info_thresholds(self):
        self.assertEqual(guardian_stage_info(0)["stage"], 1)
        self.assertEqual(guardian_stage_info(149)["stage"], 1)
        self.assertEqual(guardian_stage_info(150)["stage"], 2)
        self.assertEqual(guardian_stage_info(399)["stage"], 2)
        self.assertEqual(guardian_stage_info(400)["stage"], 3)


class MasteryTests(unittest.TestCase):
    def test_five_correct_on_one_person_masters_that_person_only(self):
        progress = normalize_progress({})
        for _ in range(4):
            self.assertFalse(apply_mastery(progress, 1, "present", True, threshold=5, person="tu"))
        self.assertTrue(apply_mastery(progress, 1, "present", True, threshold=5, person="tu"))
        entry = progress["verbs"]["1"]
        self.assertTrue(entry["persons"]["tu"]["mastered"])
        self.assertFalse(entry["persons"]["el_ella_usted"]["mastered"])
        self.assertFalse(entry["mastered"])
        self.assertEqual(entry["correct_count"], 5)
        self.assertEqual(mastered_person_count(progress, "tu", 5), 1)
        self.assertEqual(mastered_person_count(progress, "el_ella_usted", 5), 0)
        view = progress_view(progress, conjugation_threshold=5)
        self.assertEqual(view["mastered_tu_count"], 1)
        self.assertEqual(view["mastered_el_count"], 0)
        self.assertEqual(view["mastered_count"], 0)

    def test_both_persons_at_threshold_marks_mastered(self):
        progress = normalize_progress({})
        for _ in range(5):
            apply_mastery(progress, 1, "present", True, threshold=5, person="tu")
        self.assertFalse(verb_is_mastered(progress["verbs"]["1"], 5))
        for _ in range(4):
            self.assertFalse(apply_mastery(progress, 1, "present", True, threshold=5, person="el_ella_usted"))
        self.assertTrue(apply_mastery(progress, 1, "present", True, threshold=5, person="el_ella_usted"))
        self.assertTrue(verb_is_mastered(progress["verbs"]["1"], 5))
        self.assertEqual(mastered_verb_count(progress, 5), 1)

    def test_incorrect_resets_person_streak_but_not_other_person(self):
        progress = normalize_progress({})
        apply_mastery(progress, 1, "present", True, threshold=5, person="tu")
        apply_mastery(progress, 1, "present", True, threshold=5, person="tu")
        apply_mastery(progress, 1, "present", True, threshold=5, person="el_ella_usted")
        apply_mastery(progress, 1, "present", False, threshold=5, person="tu")
        entry = progress["verbs"]["1"]
        self.assertEqual(entry["correct_count"], 3)
        self.assertEqual(entry["persons"]["tu"]["consecutive_correct"], 0)
        self.assertEqual(entry["persons"]["el_ella_usted"]["consecutive_correct"], 1)
        self.assertEqual(entry["present"]["consecutive_correct"], 0)
        self.assertFalse(entry["mastered"])

    def test_gustar_and_unknown_tense_are_ignored_for_id(self):
        progress = normalize_progress({})
        self.assertFalse(apply_mastery(progress, "gustar", "present", True))
        self.assertFalse(apply_mastery(progress, 1, "gustar", True, threshold=5))
        self.assertEqual(progress["verbs"]["1"]["correct_count"], 1)

    def test_apply_attempt_increments_total_and_daily(self):
        progress = normalize_progress({})
        today = date(2026, 8, 15)
        apply_attempt(progress, verb_id=1, tense="present", is_correct=True, today=today, threshold=5)
        apply_attempt(progress, verb_id=1, tense="present", is_correct=True, today=today, threshold=5)
        self.assertEqual(progress["total_attempts"], 2)
        self.assertEqual(progress["current_streak"], 1)
        self.assertEqual(progress["daily_attempts"]["2026-08-15"], 2)
        self.assertEqual(progress["practice_dates"], ["2026-08-15"])

    def test_mastered_count_and_level(self):
        progress = normalize_progress({})
        for _ in range(5):
            apply_mastery(progress, 1, "present", True, threshold=5, person="tu")
            apply_mastery(progress, 1, "present", True, threshold=5, person="el_ella_usted")
        self.assertEqual(mastered_verb_count(progress, 5), 1)
        self.assertTrue(verb_is_mastered(progress["verbs"]["1"], 5))
        self.assertEqual(learner_level(0), 1)
        self.assertEqual(learner_level(23), 5)

    def test_old_conjugation_progress_is_reset(self):
        progress = normalize_progress(
            {
                "coins": 12,
                "current_streak": 4,
                "verbs": {
                    "1": {"present": {"consecutive_correct": 3, "mastered": True}},
                },
                "vocab": {
                    "1": {"ja_to_es": {"consecutive_correct": 2, "miss_count": 1, "mastered": False}},
                },
            }
        )
        self.assertEqual(progress["verbs"], {})
        self.assertEqual(progress["conjugation_progress_version"], 1)
        self.assertEqual(progress["coins"], 12)
        self.assertEqual(progress["current_streak"], 4)
        self.assertEqual(progress["vocab"]["1"]["ja_to_es"]["consecutive_correct"], 2)
        self.assertEqual(progress["vocab"]["1"]["ja_to_es"]["miss_count"], 1)

    def test_current_conjugation_progress_is_kept(self):
        progress = normalize_progress(
            {
                "conjugation_progress_version": 1,
                "verbs": {
                    "1": {
                        "correct_count": 2,
                        "persons": {
                            "tu": {"consecutive_correct": 2, "mastered": False},
                            "el_ella_usted": {"consecutive_correct": 1, "mastered": False},
                        },
                        "present": {
                            "consecutive_correct": 1,
                            "correct_count": 1,
                            "miss_count": 4,
                            "mastered": False,
                        },
                    }
                },
            }
        )
        entry = progress["verbs"]["1"]
        self.assertEqual(entry["persons"]["tu"]["consecutive_correct"], 2)
        self.assertEqual(entry["persons"]["el_ella_usted"]["consecutive_correct"], 1)
        self.assertEqual(entry["present"]["miss_count"], 4)
        self.assertFalse(verb_is_mastered(entry, 5))

    def test_conjugation_miss_counts_are_kept_per_tense(self):
        progress = normalize_progress({})
        apply_mastery(progress, 1, "present", False, threshold=3, person="tu")
        apply_mastery(progress, 1, "present", False, threshold=3, person="el_ella_usted")
        apply_mastery(progress, 1, "preterite", False, threshold=3, person="tu")
        for _ in range(6):
            apply_mastery(progress, 1, "imperfect", False, threshold=3, person="el_ella_usted")
        apply_mastery(progress, 1, "imperfect", True, threshold=3, person="tu")
        entry = progress["verbs"]["1"]
        self.assertEqual(entry["present"]["miss_count"], 2)
        self.assertEqual(entry["preterite"]["miss_count"], 1)
        self.assertEqual(entry["imperfect"]["miss_count"], 6)
        self.assertEqual(entry["persons"]["tu"]["consecutive_correct"], 1)
        self.assertEqual(entry["persons"]["el_ella_usted"]["consecutive_correct"], 0)
        row = next(item for item in verb_progress_list(progress, 3) if item["id"] == 1)
        misses = {item["id"]: item for item in row["tense_misses"]}
        self.assertEqual([item["label"] for item in row["tense_misses"]], ["現在", "点過去", "線過去"])
        self.assertEqual(misses["present"]["miss_count"], 2)
        self.assertFalse(misses["present"]["alert"])
        self.assertEqual(misses["preterite"]["miss_count"], 1)
        self.assertFalse(tense_miss_view(entry)[1]["alert"])
        self.assertEqual(misses["imperfect"]["miss_count"], 6)
        self.assertTrue(misses["imperfect"]["alert"])
        self.assertEqual(row["miss_total"], 9)

    def test_vocab_mastery_uses_threshold(self):
        progress = normalize_progress({})
        for _ in range(4):
            self.assertFalse(apply_vocab_mastery(progress, 1, True, threshold=5, direction="ja_to_es"))
        self.assertTrue(apply_vocab_mastery(progress, 1, True, threshold=5, direction="ja_to_es"))
        self.assertFalse(apply_vocab_mastery(progress, 1, False, threshold=5, direction="ja_to_es"))
        self.assertEqual(progress["vocab"]["1"]["ja_to_es"]["consecutive_correct"], 0)
        self.assertTrue(progress["vocab"]["1"]["ja_to_es"]["mastered"])
        self.assertEqual(progress["vocab"]["1"]["es_to_ja"]["correct_count"], 0)
        rows = vocab_progress_list(progress, 5)
        mastered = [row for row in rows if row["id"] == 1][0]
        self.assertTrue(mastered["ja_to_es"]["mastered"])
        self.assertFalse(mastered["es_to_ja"]["mastered"])

    def test_vocab_wrong_answer_resets_streak(self):
        progress = normalize_progress({})
        for _ in range(4):
            apply_vocab_mastery(progress, 1, True, threshold=5, direction="ja_to_es")
        apply_vocab_mastery(progress, 1, False, threshold=5, direction="ja_to_es")
        self.assertEqual(progress["vocab"]["1"]["ja_to_es"]["consecutive_correct"], 0)
        self.assertEqual(progress["vocab"]["1"]["ja_to_es"]["miss_count"], 1)
        self.assertFalse(progress["vocab"]["1"]["ja_to_es"]["mastered"])
        for _ in range(4):
            self.assertFalse(apply_vocab_mastery(progress, 1, True, threshold=5, direction="ja_to_es"))
        self.assertTrue(apply_vocab_mastery(progress, 1, True, threshold=5, direction="ja_to_es"))
        self.assertEqual(progress["vocab"]["1"]["ja_to_es"]["miss_count"], 1)

    def test_vocab_miss_count_accumulates_across_answers(self):
        progress = normalize_progress({})
        apply_vocab_mastery(progress, 1, False, threshold=5, direction="ja_to_es")
        apply_vocab_mastery(progress, 1, False, threshold=5, direction="ja_to_es")
        apply_vocab_mastery(progress, 1, True, threshold=5, direction="ja_to_es")
        apply_vocab_mastery(progress, 1, False, threshold=5, direction="es_to_ja")
        self.assertEqual(progress["vocab"]["1"]["ja_to_es"]["miss_count"], 2)
        self.assertEqual(progress["vocab"]["1"]["ja_to_es"]["consecutive_correct"], 1)
        self.assertEqual(progress["vocab"]["1"]["es_to_ja"]["miss_count"], 1)
        self.assertEqual(progress["vocab"]["1"]["miss_count"], 3)
        rows = vocab_progress_list(progress, 5)
        row = [item for item in rows if item["id"] == 1][0]
        self.assertEqual(row["ja_to_es"]["miss_count"], 2)
        self.assertEqual(row["es_to_ja"]["miss_count"], 1)
        self.assertEqual(row["miss_count"], 3)

    def test_vocab_directions_are_independent(self):
        progress = normalize_progress({})
        for _ in range(3):
            apply_vocab_mastery(progress, 1, True, threshold=5, direction="es_to_ja")
        self.assertEqual(progress["vocab"]["1"]["es_to_ja"]["correct_count"], 3)
        self.assertEqual(progress["vocab"]["1"]["ja_to_es"]["correct_count"], 0)
        for _ in range(2):
            apply_vocab_mastery(progress, 1, True, threshold=5, direction="es_to_ja")
        self.assertTrue(progress["vocab"]["1"]["es_to_ja"]["mastered"])
        self.assertFalse(progress["vocab"]["1"]["ja_to_es"]["mastered"])
        rows = vocab_progress_list(progress, 5)
        row = [item for item in rows if item["id"] == 1][0]
        self.assertEqual(row["es_to_ja"]["correct_count"], 5)
        self.assertEqual(row["ja_to_es"]["correct_count"], 0)
        self.assertTrue(row["es_to_ja"]["mastered"])
        self.assertFalse(row["ja_to_es"]["mastered"])
        view = progress_view(progress)
        self.assertEqual(view["vocab_mastered_es_to_ja"], 1)
        self.assertEqual(view["vocab_mastered_ja_to_es"], 0)

    def test_vocab_missing_direction_does_not_update_either_side(self):
        progress = normalize_progress({})
        self.assertFalse(apply_vocab_mastery(progress, 1, True, threshold=5, direction=None))
        self.assertFalse(apply_vocab_mastery(progress, 1, True, threshold=5, direction="both"))
        self.assertNotIn("1", progress.get("vocab") or {})

    def test_vocab_legacy_counts_become_streaks(self):
        progress = normalize_progress(
            {
                "vocab": {
                    "1": {"ja_to_es": {"correct_count": 3, "mastered": False}},
                }
            }
        )
        self.assertEqual(progress["vocab"]["1"]["ja_to_es"]["consecutive_correct"], 3)
        self.assertEqual(progress["vocab"]["1"]["ja_to_es"]["miss_count"], 0)
        self.assertFalse(progress["vocab"]["1"]["ja_to_es"]["mastered"])

    def test_vocab_legacy_miss_count_is_preserved(self):
        progress = normalize_progress(
            {
                "vocab": {
                    "1": {"ja_to_es": {"correct_count": 2, "miss_count": 4, "mastered": False}},
                }
            }
        )
        self.assertEqual(progress["vocab"]["1"]["ja_to_es"]["miss_count"], 4)
        self.assertEqual(progress["vocab"]["1"]["es_to_ja"]["miss_count"], 0)
        self.assertEqual(progress["vocab"]["1"]["miss_count"], 4)

    def test_progress_view_includes_calendar_fields(self):
        progress = normalize_progress({})
        apply_attempt(
            progress,
            verb_id=1,
            tense="present",
            is_correct=True,
            today=date(2026, 8, 17),
            threshold=5,
        )
        view = progress_view(progress, conjugation_threshold=5, vocab_threshold=5)
        self.assertEqual(view["practice_dates"], ["2026-08-17"])
        self.assertEqual(view["daily_attempts"]["2026-08-17"], 1)
        self.assertEqual(view["conjugation_threshold"], 5)
        self.assertEqual(view["vocab_threshold"], 5)


class CoinEconomyTests(unittest.TestCase):
    def test_correct_answer_earns_one_coin(self):
        progress = normalize_progress({})
        today = date(2026, 8, 19)
        apply_attempt(progress, verb_id=1, tense="present", is_correct=True, today=today, threshold=5)
        self.assertEqual(progress["coins"], 1)
        apply_attempt(progress, verb_id=1, tense="present", is_correct=True, today=today, threshold=5)
        self.assertEqual(progress["coins"], 2)

    def test_wrong_answer_earns_no_coin(self):
        progress = normalize_progress({})
        today = date(2026, 8, 19)
        apply_attempt(progress, verb_id=1, tense="present", is_correct=False, today=today, threshold=5)
        self.assertEqual(progress["coins"], 0)
        self.assertEqual(progress["total_attempts"], 1)

    def test_vocab_correct_answer_also_earns_coin(self):
        progress = normalize_progress({})
        today = date(2026, 8, 19)
        apply_attempt(
            progress,
            verb_id=1,
            is_correct=True,
            today=today,
            kind="vocab",
            direction="ja_to_es",
            threshold=5,
        )
        self.assertEqual(progress["coins"], 1)

    def test_apply_attempt_delta_reports_coins(self):
        progress = normalize_progress({})
        delta = apply_attempt(progress, verb_id=1, tense="present", is_correct=True, threshold=5)
        self.assertEqual(delta["coins"], 1)
        self.assertTrue(delta["coin_earned"])
        self.assertEqual(delta["guardian_count"], 0)

    def test_guardian_purchase_requires_enough_coins(self):
        progress = normalize_progress({"coins": 49})
        self.assertFalse(can_afford_guardian(progress, price=50))
        self.assertFalse(apply_guardian_purchase(progress, price=50))
        self.assertEqual(progress["coins"], 49)
        self.assertEqual(progress["guardian_count"], 0)

    def test_guardian_purchase_spends_coins_and_grants_one(self):
        progress = normalize_progress({"coins": 120})
        self.assertTrue(can_afford_guardian(progress, price=50))
        self.assertTrue(apply_guardian_purchase(progress, price=50))
        self.assertEqual(progress["coins"], 70)
        self.assertEqual(progress["guardian_count"], 1)

    def test_progress_view_includes_coin_and_guardian_fields(self):
        progress = normalize_progress({"coins": 30, "guardian_count": 2})
        view = progress_view(progress, guardian_price=50)
        self.assertEqual(view["coins"], 30)
        self.assertEqual(view["guardian_count"], 2)
        self.assertEqual(view["guardian_price"], 50)
        self.assertEqual(view["guardian_coins_needed"], 20)
        self.assertFalse(view["can_afford_guardian"])


if __name__ == "__main__":
    unittest.main()
