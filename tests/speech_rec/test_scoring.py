"""Delivery・点数・評価JSONの検証。"""
import json
import unittest

from speech_rec.delivery import delivery_level
from speech_rec.evaluate import interpret
from speech_rec.scoring import score
from speech_rec.settings import DEFAULT_DELIVERY_RULES, DEFAULT_SCORE_CONFIG


class DeliveryTests(unittest.TestCase):
    def test_uses_the_lowest_metric(self):
        rules = DEFAULT_DELIVERY_RULES
        self.assertEqual(delivery_level({"pause_n": 0, "pause_max": 0.4, "silent_ratio": 0.05}, rules), 6)
        # pause_n はレベル4、pause_max はレベル2、無音率はレベル5 → 2
        level = delivery_level({"pause_n": 5, "pause_max": 6.0, "silent_ratio": 0.15}, rules)
        self.assertEqual(level, 2)


class ScoringTests(unittest.TestCase):
    def test_formula(self):
        levels = {"general_description": 4, "delivery": 5, "language_use": 3, "topic_development": 4}
        row = score(levels, 92, True, DEFAULT_SCORE_CONFIG)
        self.assertEqual(row["points"]["delivery"], 35)
        self.assertEqual(row["points"]["language_use"], 25)
        self.assertEqual(row["wpm_points"], 92)
        self.assertEqual(row["total"], 30 + 35 + 25 + 30 + 92)

    def test_off_topic_multiplier(self):
        config = json.loads(json.dumps(DEFAULT_SCORE_CONFIG))
        config["off_topic_multiplier"] = 0.5
        row = score({"general_description": 1, "delivery": 1, "language_use": 1, "topic_development": 1}, 10, False, config)
        self.assertEqual(row["wpm_points"], 5)


class InterpretTests(unittest.TestCase):
    def test_clamps_levels_and_flags_without_storing_text_in_numbers(self):
        payload = {
            "on_topic": False,
            "oreo": {
                "opinion_open": {"present": False, "evidence": "I think winter"},
                "reason": {"present": True, "evidence": "because"},
                "example": {"present": False, "evidence": ""},
                "opinion_close": {"present": False, "evidence": ""},
            },
            "sentences": [
                {"text": "I like winter.", "role": "opinion"},
                {"text": "It is cold.", "role": "reason"},
            ],
            "levels": {
                "general_description": {"level": 9, "comment": "長いコメント"},
                "language_use": {"level": 0, "comment": ""},
                "topic_development": {"level": 3.6, "comment": ""},
            },
            "student_feedback": {"next_step": "例を一つ足そう"},
        }
        parsed = interpret(payload, words_counted=12)
        self.assertEqual(parsed["levels"]["general_description"], 6)
        self.assertEqual(parsed["levels"]["language_use"], 1)
        self.assertEqual(parsed["levels"]["topic_development"], 4)
        self.assertIn("no_open", parsed["flags"])
        self.assertIn("no_example", parsed["flags"])
        self.assertIn("off_topic", parsed["flags"])
        self.assertIn("short_speech", parsed["flags"])
        self.assertNotIn("evidence", parsed["oreo"])
        self.assertIn("I think winter", parsed["view"]["evidence"]["opinion_open"])


if __name__ == "__main__":
    unittest.main()
