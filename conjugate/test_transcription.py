"""Whisper プロンプトエコー除去の単体テスト。"""
import unittest

from conjugate.transcription import (
    glossary_sentences,
    keep_spanish_transcript,
    looks_like_glossary_echo,
    looks_like_prompt_echo,
    sanitize_transcript,
    strip_prompt_echo,
)


class PromptEchoTests(unittest.TestCase):
    def test_example_dump_is_detected(self):
        leaked = "Puedes. Hablas. Estás comiendo. Vas a estudiar. Te gusta el café. Pudiste."
        self.assertTrue(looks_like_prompt_echo(leaked))
        self.assertEqual(strip_prompt_echo(leaked), "")

    def test_real_short_answer_is_kept(self):
        self.assertEqual(strip_prompt_echo("Llegaste."), "Llegaste.")
        self.assertFalse(looks_like_prompt_echo("Llegaste."))

    def test_gustar_answer_matching_one_example_is_kept(self):
        spoken = "Te gusta el café."
        self.assertFalse(looks_like_prompt_echo(spoken))
        self.assertEqual(strip_prompt_echo(spoken), spoken)

    def test_echo_plus_real_answer_keeps_the_answer(self):
        mixed = "Puedes. Hablas. Estás comiendo. Vas a estudiar. Llegaste. Pudiste."
        self.assertTrue(looks_like_prompt_echo(mixed))
        self.assertEqual(strip_prompt_echo(mixed), "Llegaste")

    def test_sanitize_drops_non_spanish_and_echo(self):
        self.assertEqual(sanitize_transcript("مرحبا"), "")
        self.assertEqual(
            sanitize_transcript("Puedes. Hablas. Estás comiendo. Vas a estudiar. Te gusta el café. Pudiste."),
            "",
        )

    def test_keep_spanish_transcript_allows_spanish(self):
        self.assertEqual(keep_spanish_transcript("Estás llegando."), "Estás llegando.")


class GlossaryPromptTests(unittest.TestCase):
    def test_glossary_lists_this_tense_only(self):
        question = {
            "kind": "verb",
            "infinitive": "hablar",
            "forms": {
                "present": {"yo": "Hablo.", "tu": "Hablas.", "el_ella_usted": "Habla."},
                "preterite": {"yo": "Hablé.", "tu": "Hablaste.", "el_ella_usted": "Habló."},
            },
        }
        self.assertEqual(
            glossary_sentences(question, "present"),
            ["hablar", "Hablo", "Hablas", "Habla"],
        )

    def test_one_matching_form_is_not_an_echo(self):
        glossary = ["hablar", "Yo hablo", "Tú hablas", "Él habla"]
        self.assertFalse(looks_like_glossary_echo("Hablas.", glossary))

    def test_full_glossary_dump_is_an_echo(self):
        glossary = ["hablar", "Yo hablo", "Tú hablas", "Él habla"]
        echoed = "hablar. Yo hablo. Tú hablas. Él habla."
        self.assertTrue(looks_like_glossary_echo(echoed, glossary))


if __name__ == "__main__":
    unittest.main()
