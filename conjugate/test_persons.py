"""tú → él/ella/usted 自動導出と人称出題の単体テスト。"""
import unittest

from conjugate.data.conjugations import CONJ_EXTRA, build_forms, derived_person_rows
from conjugate.data.gustar import GUSTAR_EXAMPLES
from conjugate.data.persons import pret_tu_to_el, resolve_person, tu_form_to_el
from conjugate.data.verbs import VERBS_BY_ID, drillable_verbs
from conjugate.judge import grade_gustar, grade_regular
from conjugate.session_logic import build_session_questions, public_question


class TuToElDerivationTests(unittest.TestCase):
    def test_regular_and_stem_changing_present(self):
        self.assertEqual(tu_form_to_el("hablas"), "habla")
        self.assertEqual(tu_form_to_el("vienes"), "viene")
        self.assertEqual(tu_form_to_el("tienes"), "tiene")
        self.assertEqual(tu_form_to_el("estás"), "está")
        self.assertEqual(tu_form_to_el("vas"), "va")
        self.assertEqual(tu_form_to_el("ves"), "ve")
        self.assertEqual(tu_form_to_el("eres"), "es")
        self.assertEqual(tu_form_to_el("Eres"), "Es")

    def test_reflexive_present(self):
        self.assertEqual(tu_form_to_el("te quedas"), "se queda")
        self.assertEqual(tu_form_to_el("te sientes"), "se siente")

    def test_all_drillable_present_forms_drop_final_s(self):
        rows = derived_person_rows()
        self.assertEqual(len(rows), len(drillable_verbs()))
        self.assertEqual(set(CONJ_EXTRA), {v["id"] for v in drillable_verbs()})
        for row in rows:
            el = row["el_present"]
            if row["infinitive"] == "ser":
                self.assertEqual(el, "es")
                continue
            self.assertFalse(el.endswith("s"), msg=f"{row['infinitive']}: {row['tu_present']} → {el}")
            if row["reflexive"]:
                self.assertTrue(el.startswith("se "), msg=row["infinitive"])
        ser = next(row for row in rows if row["infinitive"] == "ser")
        self.assertEqual(ser["tu_present"], "eres")
        self.assertEqual(ser["el_present"], "es")

    def test_known_preterite_irregulars(self):
        cases = {
            1: "fue",
            101: "fue",
            2: "vino",
            105: "puso",
            109: "dio",
            102: "supo",
            107: "oyó",
            14: "siguió",
            18: "cayó",
            22: "leyó",
            26: "estuvo",
            28: "sintió",
            34: "prefirió",
            38: "creyó",
            52: "dijo",
            57: "pidió",
            78: "durmió",
            87: "condujo",
            91: "tuvo",
            92: "hizo",
            95: "vio",
            98: "pudo",
            15: "empezó",
            79: "jugó",
        }
        for vid, expected in cases.items():
            verb = VERBS_BY_ID[vid]
            extra = CONJ_EXTRA[vid]
            _yo_present, _gerundio, pret_yo, pret_tu = extra
            self.assertEqual(
                pret_tu_to_el(pret_tu, pret_yo, verb.get("stem_change"), verb["infinitive"]),
                expected,
                msg=verb["infinitive"],
            )

    def test_progressive_and_near_future_auxiliary(self):
        hablar = build_forms(VERBS_BY_ID[51])
        self.assertEqual(hablar["progressive"]["el_ella_usted"], "Está hablando.")
        self.assertEqual(hablar["near_future"]["el_ella_usted"], "Va a hablar.")
        quedarse = build_forms(VERBS_BY_ID[100])
        self.assertEqual(quedarse["progressive"]["el_ella_usted"], "Está quedándose.")
        self.assertEqual(quedarse["near_future"]["el_ella_usted"], "Va a quedarse.")
        self.assertEqual(quedarse["present"]["el_ella_usted"], "Se queda.")
        self.assertEqual(quedarse["preterite"]["el_ella_usted"], "Se quedó.")
        self.assertEqual(hablar["imperfect"]["yo"], "Hablaba.")
        self.assertEqual(hablar["imperfect"]["tu"], "Hablabas.")
        self.assertEqual(hablar["imperfect"]["el_ella_usted"], "Hablaba.")
        self.assertEqual(quedarse["imperfect"]["tu"], "Te quedabas.")
        self.assertEqual(quedarse["imperfect"]["el_ella_usted"], "Se quedaba.")
        ser = build_forms(VERBS_BY_ID[101])
        self.assertEqual(ser["present"]["yo"], "Yo soy.")
        self.assertEqual(ser["present"]["tu"], "Eres.")
        self.assertEqual(ser["present"]["el_ella_usted"], "Es.")
        self.assertEqual(ser["preterite"]["yo"], "Fui.")
        self.assertEqual(ser["preterite"]["tu"], "Fuiste.")
        self.assertEqual(ser["preterite"]["el_ella_usted"], "Fue.")
        llamarse = build_forms(VERBS_BY_ID[108])
        self.assertEqual(llamarse["present"]["el_ella_usted"], "Se llama.")
        self.assertEqual(llamarse["near_future"]["el_ella_usted"], "Va a llamarse.")

    def test_imperfect_regular_and_irregular(self):
        cases = {
            51: ("Hablaba.", "Hablabas.", "Hablaba."),
            76: ("Comía.", "Comías.", "Comía."),
            21: ("Escribía.", "Escribías.", "Escribía."),
            1: ("Iba.", "Ibas.", "Iba."),
            101: ("Era.", "Eras.", "Era."),
            95: ("Veía.", "Veías.", "Veía."),
            14: ("Seguía.", "Seguías.", "Seguía."),
            78: ("Dormía.", "Dormías.", "Dormía."),
            42: ("Me sentía.", "Te sentías.", "Se sentía."),
        }
        for vid, expected in cases.items():
            forms = build_forms(VERBS_BY_ID[vid])["imperfect"]
            self.assertEqual(
                (forms["yo"], forms["tu"], forms["el_ella_usted"]),
                expected,
                msg=VERBS_BY_ID[vid]["infinitive"],
            )

    def test_every_drillable_verb_has_all_tenses(self):
        from conjugate.data.conjugations import TENSE_ORDER

        rows = derived_person_rows()
        for row in rows:
            for tense in TENSE_ORDER:
                self.assertIn(tense, row["tenses"], msg=f"{row['infinitive']} {tense}")
                self.assertTrue(row["tenses"][tense]["tu"])
                self.assertTrue(row["tenses"][tense]["el_ella_usted"])


class GustarPersonTests(unittest.TestCase):
    def test_le_gusta_patterns_exist(self):
        self.assertGreaterEqual(len(GUSTAR_EXAMPLES), 10)
        for item in GUSTAR_EXAMPLES:
            self.assertTrue(item["el_ella_usted_sentence"].startswith("Le gust"))
            self.assertTrue(item["tu_sentence"].startswith("Te gust"))

    def test_grade_gustar_el_form(self):
        item = GUSTAR_EXAMPLES[0]
        ok = grade_gustar(item, "Le gusta el café.", source="typed", person="el_ella_usted")
        self.assertEqual(ok["level"], "correct")
        te = grade_gustar(item, "Te gusta el café.", source="typed", person="el_ella_usted")
        self.assertEqual(te["level"], "pronoun_error")


class GradingPersonTests(unittest.TestCase):
    def test_el_present_is_correct(self):
        verb = VERBS_BY_ID[51]
        result = grade_regular(verb, "present", "habla", source="typed", person="el_ella_usted")
        self.assertEqual(result["level"], "correct")
        tu = grade_regular(verb, "present", "hablas", source="typed", person="el_ella_usted")
        self.assertEqual(tu["level"], "conjugation_error")

    def test_ser_eres_to_es(self):
        verb = VERBS_BY_ID[101]
        tu = grade_regular(verb, "present", "eres", source="typed", person="tu")
        self.assertEqual(tu["level"], "correct")
        el = grade_regular(verb, "present", "es", source="typed", person="el_ella_usted")
        self.assertEqual(el["level"], "correct")
        wrong = grade_regular(verb, "present", "eres", source="typed", person="el_ella_usted")
        self.assertEqual(wrong["level"], "conjugation_error")

    def test_reflexive_se_is_required(self):
        verb = VERBS_BY_ID[100]
        ok = grade_regular(verb, "present", "se queda", source="typed", person="el_ella_usted")
        self.assertEqual(ok["level"], "correct")
        te = grade_regular(verb, "present", "te queda", source="typed", person="el_ella_usted")
        self.assertEqual(te["level"], "pronoun_error")

    def test_imperfect_tu_and_el(self):
        verb = VERBS_BY_ID[51]
        tu = grade_regular(verb, "imperfect", "hablabas", source="typed", person="tu")
        self.assertEqual(tu["level"], "correct")
        el = grade_regular(verb, "imperfect", "hablaba", source="typed", person="el_ella_usted")
        self.assertEqual(el["level"], "correct")
        wrong = grade_regular(verb, "imperfect", "hablaste", source="typed", person="tu")
        self.assertEqual(wrong["level"], "conjugation_error")


class SessionPersonTests(unittest.TestCase):
    def test_resolve_person(self):
        self.assertEqual(resolve_person("tu", "el_ella_usted"), "tu")
        self.assertEqual(resolve_person("el_ella_usted", "all"), "el_ella_usted")
        self.assertEqual(resolve_person("mix", "tu"), "tu")
        self.assertEqual(resolve_person("mix", "all"), "mix")

    def test_el_only_session_uses_el_person(self):
        questions = build_session_questions(
            categories=["communication"],
            tenses=["present"],
            count=5,
            targets_per_question=1,
            gustar_enabled=False,
            gustar_count=0,
            prioritize_weak=False,
            person_mode="el_ella_usted",
        )
        self.assertTrue(all(q["person"] == "el_ella_usted" for q in questions))
        public = public_question(questions[0])
        self.assertEqual(public["person"], "el_ella_usted")
        self.assertNotIn("tu", public["forms"]["present"])
        self.assertNotIn("el_ella_usted", public["forms"]["present"])

    def test_mix_all_uses_both_persons(self):
        questions = build_session_questions(
            categories=["communication"],
            tenses=["present"],
            count=30,
            targets_per_question=1,
            gustar_enabled=False,
            gustar_count=0,
            prioritize_weak=False,
            person_mode="mix",
            person_filter="all",
        )
        self.assertEqual({q["person"] for q in questions}, {"tu", "el_ella_usted"})

    def test_mix_filter_forces_tu_review(self):
        questions = build_session_questions(
            categories=["communication"],
            tenses=["present"],
            count=8,
            targets_per_question=1,
            gustar_enabled=False,
            gustar_count=0,
            prioritize_weak=False,
            person_mode="mix",
            person_filter="tu",
        )
        self.assertTrue(all(q["person"] == "tu" for q in questions))


if __name__ == "__main__":
    unittest.main()
