"""語数・間の計算と、文字起こし後に音声が残らないこと。"""
import os
import tempfile
import unittest
from pathlib import Path

from speech_rec.metrics import measure, wpm_points
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
        self.assertEqual(row["pause_max"], 9)
        self.assertAlmostEqual(row["silent_ratio"], 0.9, places=2)


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
        self.jobs.process("asg1", "rec1")
        record = read_json(self.dir / "records" / "asg1" / "rec1.json")
        self.assertEqual(record["status"], "done")
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
