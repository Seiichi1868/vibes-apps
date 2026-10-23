"""413、端末IDのハッシュ、止まった受付の復旧。"""
import io
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from speech_rec.assignments import now
from speech_rec.config import audio_tmp_dir
from speech_rec.jobs import recover_stalled
from speech_rec.settings import save_settings
from speech_rec.store import read_json, write_json
from speech_rec.submissions import device_hash


class FixTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="speech-rec-fix-"))
        self.audio = Path(tempfile.mkdtemp(prefix="speech-rec-fix-aud-"))
        os.environ["SPEECH_REC_DATA_DIR"] = str(self.dir)
        os.environ["ADMIN_PASSWORD"] = "test-admin-pass"
        os.environ["FLASK_SECRET_KEY"] = "test-secret"
        import speech_rec.config as config
        import speech_rec.jobs as jobs
        import speech_rec.submissions as submissions

        self.jobs = jobs
        self._orig_audio = audio_tmp_dir
        config.audio_tmp_dir = lambda: self.audio
        submissions.audio_tmp_dir = lambda: self.audio
        jobs.audio_tmp_dir = lambda: self.audio
        jobs.enabled = False
        from flask import Flask

        from speech_rec import create_blueprint

        root = Path(__file__).resolve().parents[2]
        self.app = Flask("speech_fix", template_folder=str(root / "templates"), static_folder=str(root / "static"))
        self.app.config["SECRET_KEY"] = "test-secret"
        self.app.register_blueprint(create_blueprint())
        self.client = self.app.test_client()
        save_settings({"student_enabled": True, "daily_limit_usd": 100})
        self.client.post(
            "/rec/admin/unlock",
            json={"password": "test-admin-pass"},
            headers={"X-Speech-Rec-Request": "1"},
        )
        made = self.client.post(
            "/rec/api/t/assignments",
            json={"text": "Talk about a season.", "max_submissions": 40},
            headers={"X-Speech-Rec-Request": "1", "Content-Type": "application/json"},
        )
        self.token = made.get_json()["url"].rsplit("/", 1)[-1]
        self.assignment_id = made.get_json()["id"]

    def tearDown(self):
        import speech_rec.config as config
        import speech_rec.submissions as submissions

        config.audio_tmp_dir = self._orig_audio
        submissions.audio_tmp_dir = self._orig_audio
        self.jobs.audio_tmp_dir = self._orig_audio
        self.jobs.enabled = True
        for root in (self.dir, self.audio):
            for path in sorted(root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()

    def _send(self, device="device-0001", size=8000):
        return self.client.post(
            f"/rec/api/a/{self.token}/submit",
            data={
                "audio": (io.BytesIO(b"RIFFxxxxWAVEfmt " + b"\x01" * size), "speech.m4a"),
                "duration_ms": "9000",
                "device_id": device,
            },
            content_type="multipart/form-data",
        )

    def test_forty_megabytes_is_rejected_immediately(self):
        huge = io.BytesIO(b"x" * (40 * 1024 * 1024))
        res = self.client.post(
            f"/rec/api/a/{self.token}/submit",
            data={"audio": (huge, "big.m4a"), "duration_ms": "9000", "device_id": "device-0001"},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 413)

    def test_device_id_is_stored_as_hmac(self):
        res = self._send("plain-device-id")
        self.assertEqual(res.status_code, 202)
        record = next((self.dir / "records" / self.assignment_id).glob("*.json"))
        text = record.read_text(encoding="utf-8")
        self.assertNotIn("plain-device-id", text)
        with self.app.app_context():
            digest = device_hash("plain-device-id")
        self.assertIn(digest, text)
        self.assertEqual(len(digest), 64)

    def test_stale_received_with_audio_is_requeued(self):
        record_id = "stuck1"
        write_json(
            self.dir / "records" / self.assignment_id / f"{record_id}.json",
            {
                "id": record_id,
                "assignment_id": self.assignment_id,
                "status": "received",
                "created_at": (now() - timedelta(seconds=180)).isoformat(timespec="seconds"),
                "device_id": "abc",
            },
        )
        (self.audio / f"{record_id}.m4a").write_bytes(b"audio-still-here")
        recover_stalled()
        row = read_json(self.dir / "records" / self.assignment_id / f"{record_id}.json")
        self.assertEqual(row["status"], "queued")
        self.assertEqual(row["stall_requeues"], 1)

    def test_six_errors_block_the_next_submit(self):
        with self.app.app_context():
            digest = device_hash("device-errors")
        folder = self.dir / "records" / self.assignment_id
        for index in range(10):
            write_json(folder / f"err{index}.json", {"id": f"err{index}", "status": "error", "device_id": digest})
        res = self._send("device-errors")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.get_json()["error"], "attempts")

    def test_queue_over_sixty_is_busy(self):
        import speech_rec.submissions as submissions

        original = submissions.pending_count
        submissions.pending_count = lambda: 60
        try:
            res = self._send("device-queue9")
        finally:
            submissions.pending_count = original
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.get_json()["error"], "busy")


if __name__ == "__main__":
    unittest.main()
