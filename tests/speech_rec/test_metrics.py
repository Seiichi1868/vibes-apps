"""語数・間の計算と、文字起こし後に音声が残らないこと。"""
import os
import tempfile
import unittest
from pathlib import Path

from speech_rec.delivery import delivery_level, delivery_reason
from speech_rec.metrics import measure, wpm_points
from speech_rec.settings import DEFAULT_DELIVERY_RULES
from speech_rec.store import read_json, write_json


class MetricsTests(unittest.TestCase):
    def test_counts_words_pauses_and_drops_fillers(self):
        words = [
            ("I", 0.0, 0.2),
            ("um,", 0.3, 0.5),
            ("like", 2.0, 2.3),
            ("summer.", 2.4, 2.8),
            ("Late", 70.0, 70.4),
        ]
        row = measure(words, speak_sec=60, grace_sec=3, pause_gap_sec=0.8, exclude_fillers=True)
        self.assertEqual(row["words_all"], 4)
        self.assertEqual(row["nonlexical_fillers"], 1)
        self.assertEqual(row["words_counted"], 3)
        self.assertGreaterEqual(row["pause_n"], 1)
        self.assertGreater(row["pause_max"], 1)
        self.assertEqual(wpm_points(row["words_counted"], {"w_wpm": 1, "wpm_cap": None}), 3)
        self.assertEqual(wpm_points(120, {"w_wpm": 1, "wpm_cap": 100}), 100)

    def test_tail_silence_is_inside_the_window(self):
        row = measure([("Hello", 0.0, 1.0)], speak_sec=10, grace_sec=0, pause_gap_sec=0.8, exclude_fillers=True)
        self.assertEqual(row["pause_max"], 0)
        self.assertEqual(row["silent_ratio"], 0)


def _utterance(words_per_sentence, sentences, sentence_gap, mid_gap=0.05, word_sec=0.25):
    words = []
    text = []
    clock = 0.0
    for sentence in range(sentences):
        for index in range(words_per_sentence):
            end = clock + word_sec
            last = index == words_per_sentence - 1
            mark = "." if last else ""
            words.append((f"word{mark}", clock, end))
            text.append(f"word{mark}")
            clock = end + (sentence_gap if last and sentence < sentences - 1 else 0 if last else mid_gap)
    return words, " ".join(text)


class DeliveryGapTests(unittest.TestCase):
    def level(self, words, text, speak_sec=60):
        row = measure(
            words, speak_sec=speak_sec, grace_sec=3, pause_gap_sec=0.8, exclude_fillers=True, text=text,
        )
        return delivery_level(row, DEFAULT_DELIVERY_RULES), row

    def test_fluent_sentence_gaps_stay_level_six(self):
        words, text = _utterance(12, 9, 0.9)
        extra, extra_text = _utterance(8, 1, 0.9)
        # 9*12+8 = 116。文間 0.9 秒は文末の自然な間。
        shift = words[-1][2] + 0.9
        extra = [(token, start + shift, end + shift) for token, start, end in extra]
        level, row = self.level(words + extra, text + " " + extra_text)
        self.assertEqual(row["words_counted"], 116)
        self.assertEqual(level, 6)
        words, text = _utterance(12, 9, 1.5)
        extra = [(token, start + words[-1][2] + 1.5, end + words[-1][2] + 1.5) for token, start, end in extra]
        level, _row = self.level(words + extra, text + " " + extra_text)
        self.assertEqual(level, 6)

    def test_long_sentence_gap_and_mid_pause(self):
        words, text = _utterance(12, 10, 2.5, word_sec=0.2)
        level, row = self.level(words, text)
        self.assertEqual(row["pause_n"], 9)
        self.assertEqual(level, 2)
        words = []
        clock = 0.0
        for index in range(80):
            gap = 3.5 if index == 20 else 0.05
            end = clock + 0.45
            words.append(("word", clock, end))
            clock = end + gap
        text = " ".join("word" for _ in words)
        level, row = self.level(words, text)
        self.assertEqual(level, 3)
        self.assertGreater(row["pause_max"], 3)
        words = []
        clock = 0.0
        for index in range(40):
            gap = 0.6 if index < 15 else 0.05
            end = clock + 0.55
            words.append(("word", clock, end))
            clock = end + (0 if index == 39 else gap)
        text = " ".join("word" for _ in words)
        level, row = self.level(words, text)
        self.assertEqual(row["pause_n"], 0)
        self.assertEqual(level, 4)

    def test_tail_is_ignored_and_unknown_punctuation_raises_the_floor(self):
        level, row = self.level([("Hello.", 0.0, 1.0)], "Hello.")
        self.assertEqual(row["pause_max"], 0)
        self.assertEqual(level, 6)
        words = [("alpha", 0.0, 0.4), ("beta", 1.5, 1.9), ("gamma", 2.5, 2.9)]
        row = measure(words, speak_sec=60, grace_sec=0, pause_gap_sec=0.8, exclude_fillers=True, text="totally different words here")
        self.assertEqual(row["boundary_info"], "unaligned")
        self.assertEqual(row["pause_n"], 1)
        reason = delivery_reason({"pause_n": 0, "pause_max": 0.2, "silent_ratio": 0.02}, DEFAULT_DELIVERY_RULES, 6)
        self.assertIn("ほとんど止まらず", reason["text"])
        self.assertNotIn("発音", reason["text"])


class JobTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="speech-rec-job-"))
        self.audio = Path(tempfile.mkdtemp(prefix="speech-rec-job-aud-"))
        os.environ["SPEECH_REC_DATA_DIR"] = str(self.dir)
        os.environ["ADMIN_PASSWORD"] = "test-admin-pass"
        import speech_rec.config as config
        import speech_rec.jobs as jobs
        import speech_rec.submissions as submissions

        self.jobs = jobs
        self._orig_audio = config.audio_tmp_dir
        self._orig_transcribe = jobs._transcribe
        self._orig_eval = jobs._evaluate
        config.audio_tmp_dir = lambda: self.audio
        submissions.audio_tmp_dir = lambda: self.audio
        jobs.audio_tmp_dir = lambda: self.audio
        jobs.enabled = False
        (self.dir / "assignments").mkdir()
        write_json(self.dir / "assignments" / "asg1.json", {"id": "asg1", "speak_sec": 60, "status": "open"})
        (self.dir / "records" / "asg1").mkdir(parents=True)
        write_json(
            self.dir / "records" / "asg1" / "rec1.json",
            {
                "id": "rec1",
                "assignment_id": "asg1",
                "status": "received",
                "metrics": {"snr_db": 10, "duration_ms": 20000, "rms_p10": 0.01, "rms_p90": 0.2},
            },
        )
        (self.audio / "rec1.m4a").write_bytes(b"not-real-audio-but-long-enough")

    def tearDown(self):
        import speech_rec.config as config
        import speech_rec.submissions as submissions

        config.audio_tmp_dir = self._orig_audio
        submissions.audio_tmp_dir = self._orig_audio
        self.jobs.audio_tmp_dir = self._orig_audio
        self.jobs._transcribe = self._orig_transcribe
        self.jobs._evaluate = self._orig_eval
        self.jobs.enabled = True
        for root in (self.dir, self.audio):
            for path in sorted(root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            if root.exists():
                root.rmdir()

    def test_transcribe_deletes_audio_and_keeps_numbers_only(self):
        def fake(_path, **_kwargs):
            words = [{"word": f"word{i}", "start": i * 0.4, "end": i * 0.4 + 0.3} for i in range(12)]
            return {"text": "word " * 12, "words": words, "duration": 20}

        self.jobs._transcribe = fake

        def fake_eval(*_args, **_kwargs):
            return {
                "on_topic": True,
                "levels": {"general_description": 4, "language_use": 3, "topic_development": 4},
                "oreo": {"opinion_open": True, "reason": True, "example": False, "opinion_close": True},
                "flags": ["no_example"],
                "cost_usd": 0.001,
                "model": "gpt-4o-mini",
                "prompt_version": "ms-eval-v1",
                "view": {"comments": {"general_description": "よい"}, "evidence": {"example": "secret quote"}, "sentences": [], "student_feedback": {"next_step": "例を足そう"}},
            }

        self.jobs._evaluate = fake_eval
        self.jobs.process("asg1", "rec1")
        record = read_json(self.dir / "records" / "asg1" / "rec1.json")
        self.assertEqual(record["status"], "done")
        self.assertNotIn("evidence", record)
        self.assertNotIn("comment", record)
        self.assertNotIn("student_feedback", record)
        self.assertEqual(record["metrics"]["words_counted"], 12)
        self.assertEqual(record["scores"]["wpm_points"], 12)
        self.assertIn("noisy", record["flags"])
        self.assertNotIn("transcript", record)
        self.assertFalse((self.audio / "rec1.m4a").exists())
        view = read_json(self.audio / "rec1.view.json")
        self.assertIn("word", view["transcript"])

    def test_few_words_do_not_count_as_done(self):
        def fake(_path, **_kwargs):
            return {"text": "hi", "words": [{"word": "hi", "start": 1, "end": 1.2}], "duration": 20}

        self.jobs._transcribe = fake
        self.jobs.process("asg1", "rec1")
        record = read_json(self.dir / "records" / "asg1" / "rec1.json")
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error_code"], "too_short")
        self.assertFalse((self.audio / "rec1.m4a").exists())


if __name__ == "__main__":
    unittest.main()
