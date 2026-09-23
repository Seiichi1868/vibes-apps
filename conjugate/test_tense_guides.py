"""時制解説と線過去の選択ロジック。"""
import unittest

from conjugate.data.conjugations import (
    TENSE_ORDER,
    default_selected_tenses,
    selectable_tenses,
)
from conjugate.data.tense_guides import get_tense_guide, list_tense_guides


class TenseSelectionTests(unittest.TestCase):
    def test_past_tenses_are_always_selectable(self):
        self.assertEqual(selectable_tenses(["present"]), ["present", "preterite", "imperfect"])
        self.assertEqual(
            selectable_tenses(["present", "preterite"]),
            ["present", "preterite", "imperfect"],
        )

    def test_imperfect_defaults_on_when_preterite_is_enabled(self):
        self.assertEqual(default_selected_tenses(["present"]), ["present"])
        self.assertEqual(
            default_selected_tenses(["present", "preterite"]),
            ["present", "preterite", "imperfect"],
        )


class TenseGuideTests(unittest.TestCase):
    def test_all_tenses_have_guides_and_examples(self):
        rows = list_tense_guides()
        self.assertEqual([row["id"] for row in rows], TENSE_ORDER)
        for tense_id in TENSE_ORDER:
            guide = get_tense_guide(tense_id)
            self.assertIsNotNone(guide)
            self.assertTrue(guide["examples"])
            for ex in guide["examples"]:
                self.assertTrue(ex["yo"])
                self.assertTrue(ex["tu"])
                self.assertTrue(ex["el"])

    def test_unknown_tense_returns_none(self):
        self.assertIsNone(get_tense_guide("future"))

    def test_imperfect_guide_mentions_three_irregulars(self):
        guide = get_tense_guide("imperfect")
        text = " ".join(guide["irregulars"])
        self.assertIn("iba", text)
        self.assertIn("era", text)
        self.assertIn("veía", text)
        self.assertIn("ir（行く）", text)
        self.assertIn("ser（〜である）", text)
        self.assertIn("ver（見る）", text)
        self.assertNotIn("未収録", text)
        self.assertTrue(guide["contrast"])
        self.assertTrue(any(ex["infinitive"] == "ser" for ex in guide["examples"]))

    def test_irregular_lines_include_registered_meanings(self):
        present = " ".join(get_tense_guide("present")["irregulars"])
        self.assertIn("tener（持つ）", present)
        self.assertIn("hacer（する・作る）", present)
        preterite = " ".join(get_tense_guide("preterite")["irregulars"])
        self.assertIn("ir（行く）", preterite)
        self.assertIn("ser（〜である）", preterite)
        self.assertIn("decir（言う）", preterite)
        progressive = " ".join(get_tense_guide("progressive")["irregulars"])
        self.assertIn("leer（読む）", progressive)
        self.assertIn("poder（できる）", progressive)


if __name__ == "__main__":
    unittest.main()
