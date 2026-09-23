"""発音の採点と、読み取りミスを習得カウントから外す処理のテスト。"""
import unittest
from unittest.mock import patch

from conjugate.data.verbs import VERBS_BY_ID
from conjugate.judge import grade_regular
from conjugate.session_logic import grade_candidates, grade_target

HABLAR = VERBS_BY_ID[51]


class SpeechMatchTests(unittest.TestCase):
    def test_silent_h_counts_as_correct_for_speech(self):
        result = grade_regular(HABLAR, "present", "ablas", source="speech", person="tu")
        self.assertEqual(result["level"], "correct")

    def test_silent_h_does_not_count_as_correct_when_typed(self):
        result = grade_regular(HABLAR, "present", "ablas", source="typed", person="tu")
        self.assertNotEqual(result["level"], "correct")

    def test_missing_final_s_stays_incorrect(self):
        result = grade_regular(HABLAR, "present", "habla", source="speech", person="tu")
        self.assertNotEqual(result["level"], "correct")

    def test_different_ending_stays_incorrect(self):
        result = grade_regular(HABLAR, "imperfect", "hablaban", source="speech", person="tu")
        self.assertNotEqual(result["level"], "correct")

    def test_exact_speech_is_correct(self):
        result = grade_regular(HABLAR, "present", "Hablas.", source="speech", person="tu")
        self.assertEqual(result["level"], "correct")


class SpeechMasteryTests(unittest.TestCase):
    def setUp(self):
        self.question = {"kind": "verb", "verb_id": 51, "person": "tu"}

    @patch("conjugate.session_logic.record_progress")
    @patch("conjugate.session_logic.record_answer_result")
    def test_speech_miss_skips_mastery_and_weak_count(self, record_answer, record_progress):
        record_progress.return_value = {"newly_mastered": False}
        result = grade_target(self.question, "present", "xyzzy", False, source="speech")
        self.assertNotEqual(result["level"], "correct")
        self.assertFalse(result["counts_toward_mastery"])
        record_answer.assert_not_called()
        record_progress.assert_called_once()
        self.assertFalse(record_progress.call_args.kwargs["track_mastery"])
        self.assertFalse(record_progress.call_args.kwargs["is_correct"])
        self.assertEqual(record_progress.call_args.kwargs["tense"], "present")

    @patch("conjugate.session_logic.record_progress")
    @patch("conjugate.session_logic.record_answer_result")
    def test_speech_correct_counts_toward_streak(self, record_answer, record_progress):
        record_progress.return_value = {"newly_mastered": False}
        result = grade_target(self.question, "present", "Hablas", False, source="speech")
        self.assertEqual(result["level"], "correct")
        self.assertTrue(result["counts_toward_mastery"])
        record_answer.assert_called_once()
        self.assertTrue(record_progress.call_args.kwargs["track_mastery"])
        self.assertTrue(record_progress.call_args.kwargs["is_correct"])

    @patch("conjugate.session_logic.record_progress")
    @patch("conjugate.session_logic.record_answer_result")
    def test_typed_wrong_still_counts(self, record_answer, record_progress):
        record_progress.return_value = {"newly_mastered": False}
        result = grade_target(self.question, "present", "habla", False, source="typed")
        self.assertNotEqual(result["level"], "correct")
        self.assertTrue(result["counts_toward_mastery"])
        record_answer.assert_called_once()
        self.assertTrue(record_progress.call_args.kwargs["track_mastery"])
        self.assertFalse(record_progress.call_args.kwargs["is_correct"])

    @patch("conjugate.session_logic.record_progress")
    @patch("conjugate.session_logic.record_answer_result")
    def test_web_speech_alternative_can_be_the_correct_one(self, record_answer, record_progress):
        record_progress.return_value = {"newly_mastered": False}
        result = grade_candidates(self.question, "present", ["xyzzy", "Hablas"], False, source="speech")
        self.assertEqual(result["level"], "correct")
        self.assertEqual(result["transcript"], "Hablas")
        record_answer.assert_called_once()
        record_progress.assert_called_once()
        self.assertTrue(record_progress.call_args.kwargs["is_correct"])


if __name__ == "__main__":
    unittest.main()
