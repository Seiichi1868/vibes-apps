"""語彙4択・タイプ解答まわりの単体テスト。"""
import unittest
from unittest.mock import patch

from conjugate.judge import grade_regular
from conjugate.vocab import (
    build_vocab_questions,
    build_vocab_summary,
    public_vocab_question,
    vocab_verbs,
)
from conjugate.data.verbs import VERBS_BY_ID


class TypedGradingTests(unittest.TestCase):
    def test_typed_present_form_is_correct(self):
        verb = VERBS_BY_ID[51]  # hablar
        result = grade_regular(verb, "present", "hablas", source="typed")
        self.assertEqual(result["level"], "correct")

    def test_typed_empty_uses_type_message(self):
        verb = VERBS_BY_ID[1]
        result = grade_regular(verb, "present", "   ", source="typed")
        self.assertEqual(result["level"], "way_off")
        self.assertIn("タイプ", result["message"])

    def test_speech_empty_uses_speech_message(self):
        verb = VERBS_BY_ID[1]
        result = grade_regular(verb, "present", "", source="speech")
        self.assertIn("発話", result["message"])


class VocabQuizTests(unittest.TestCase):
    def test_ja_to_es_has_four_unique_choices(self):
        questions = build_vocab_questions("ja_to_es", count=8)
        self.assertEqual(len(questions), 8)
        for q in questions:
            labels = [c["label"] for c in q["choices"]]
            self.assertEqual(len(labels), 4)
            self.assertEqual(len(set(labels)), 4)
            correct = next(c for c in q["choices"] if c["id"] == q["correct_choice_id"])
            self.assertEqual(correct["label"], q["infinitive"])
            self.assertEqual(q["prompt"], q["meaning_ja"])

    def test_es_to_ja_has_four_unique_choices(self):
        questions = build_vocab_questions("es_to_ja", count=8)
        self.assertEqual(len(questions), 8)
        for q in questions:
            labels = [c["label"] for c in q["choices"]]
            self.assertEqual(len(labels), 4)
            self.assertEqual(len(set(labels)), 4)
            correct = next(c for c in q["choices"] if c["id"] == q["correct_choice_id"])
            self.assertEqual(correct["label"], q["meaning_ja"])
            self.assertEqual(q["prompt"], q["infinitive"])

    def test_public_question_hides_answer_until_graded(self):
        questions = build_vocab_questions("ja_to_es", count=4)
        public = public_vocab_question(questions[0])
        self.assertNotIn("correct_choice_id", public)
        self.assertIsNone(public["answer"])

    @patch("conjugate.vocab.record_progress", return_value={"current_streak": 1})
    def test_summary_counts_correct_and_wrong(self, _progress):
        from conjugate.vocab import grade_vocab_choice

        questions = build_vocab_questions("es_to_ja", count=4)
        q = questions[0]
        wrong_id = next(c["id"] for c in q["choices"] if c["id"] != q["correct_choice_id"])
        q["answer"] = grade_vocab_choice(q, wrong_id)
        questions[1]["answer"] = grade_vocab_choice(questions[1], questions[1]["correct_choice_id"])
        summary = build_vocab_summary({"direction": "es_to_ja", "questions": questions})
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["correct"], 1)
        self.assertEqual(len(summary["weak_items"]), 1)
        self.assertEqual(summary["weak_items"][0]["verb_id"], q["verb_id"])
        self.assertEqual(summary["weak_items"][0]["miss_count"], 0)

    def test_vocab_pool_includes_registered_verbs(self):
        pool = vocab_verbs()
        self.assertGreaterEqual(len(pool), 4)
        self.assertTrue(any(v["infinitive"] == "gustar" for v in pool))
        self.assertTrue(any(v["infinitive"] == "ser" for v in pool))


if __name__ == "__main__":
    unittest.main()
