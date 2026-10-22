"""出題の期限・上限と、音声が永続ディスクに残らないこと。"""
import io
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from speech_rec.assignments import availability, create_assignment, find_by_token, now, public_view
from speech_rec.config import audio_tmp_dir, data_dir
from speech_rec.settings import save_settings
from speech_rec.store import write_json


class AssignmentFlowTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="speech-rec-asg-"))
        self.audio = Path(tempfile.mkdtemp(prefix="speech-rec-aud-"))
        os.environ["SPEECH_REC_DATA_DIR"] = str(self.dir)
        os.environ["ADMIN_PASSWORD"] = "test-admin-pass"
        os.environ["FLASK_SECRET_KEY"] = "test-secret"
        self._orig_audio = audio_tmp_dir
        import speech_rec.config as config
        import speech_rec.submissions as submissions

        config.audio_tmp_dir = lambda: self.audio
        submissions.audio_tmp_dir = lambda: self.audio
        import speech_rec.jobs as jobs

        jobs.enabled = False
        jobs.audio_tmp_dir = lambda: self.audio
        from flask import Flask

        from speech_rec import create_blueprint

        root = Path(__file__).resolve().parents[2]
        self.app = Flask(
            "speech_rec_test",
            template_folder=str(root / "templates"),
            static_folder=str(root / "static"),
        )
        self.app.config["SECRET_KEY"] = "test-secret"
        self.app.register_blueprint(create_blueprint())
        self.client = self.app.test_client()
        save_settings({"student_enabled": True, "daily_limit_usd": 100})

    def tearDown(self):
        import speech_rec.config as config
        import speech_rec.submissions as submissions

        config.audio_tmp_dir = self._orig_audio
        submissions.audio_tmp_dir = self._orig_audio
        import speech_rec.jobs as jobs

        jobs.enabled = True
        jobs.audio_tmp_dir = self._orig_audio
        for root in (self.dir, self.audio):
            for path in sorted(root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()

    def _login(self):
        res = self.client.post(
            "/rec/admin/unlock",
            json={"password": "test-admin-pass"},
            headers={"X-Speech-Rec-Request": "1"},
        )
        self.assertEqual(res.status_code, 200)

    def _wav(self, n=8000):
        return io.BytesIO(b"RIFFxxxxWAVEfmt " + b"\x01" * n)

    def test_create_hides_label_and_stores_audio_outside_data(self):
        self._login()
        made = self.client.post(
            "/rec/api/t/assignments",
            json={"text": "Which is better, summer or winter?", "label": "1年3組", "ttl_hours": 24},
            headers={"X-Speech-Rec-Request": "1", "Content-Type": "application/json"},
        )
        self.assertEqual(made.status_code, 200)
        body = made.get_json()
        self.assertTrue(body["url"].startswith("https://vibes-lab.com/rec/"))
        self.assertTrue(body["qr"].startswith("data:image/png"))
        token = body["url"].rsplit("/", 1)[-1]
        info = self.client.get(f"/rec/api/a/{token}")
        self.assertEqual(info.status_code, 200)
        self.assertNotIn("1年3組", info.get_data(as_text=True))
        page = self.client.get(f"/rec/{token}")
        self.assertEqual(page.status_code, 200)
        posted = self.client.post(
            f"/rec/api/a/{token}/submit",
            data={
                "audio": (self._wav(), "speech.m4a"),
                "duration_ms": "8000",
                "device_id": "device-0001",
                "client_stats": '{"rms_p10": 0.01, "rms_p90": 0.2, "snr_db": 26}',
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(posted.status_code, 202)
        read = self.client.get(f"/rec/api/r/{posted.get_json()['read_token']}")
        self.assertEqual(read.get_json()["status"], "received")
        audio_files = [p for p in self.audio.iterdir() if p.is_file() and p.name != ".lock"]
        self.assertEqual(len(audio_files), 1)
        self.assertFalse(str(audio_files[0]).startswith(str(data_dir())))
        self.assertFalse(any(p.suffix in {".m4a", ".webm", ".bin", ".wav"} for p in data_dir().rglob("*") if p.is_file()))

    def test_preparing_expired_full_and_third_attempt(self):
        save_settings({"student_enabled": False})
        row = create_assignment({"text": "Talk about your town.", "max_submissions": 1})
        self.assertEqual(availability(row, student_enabled=False), "preparing")
        view = public_view(row, student_enabled=False, id_fields={"enabled": False})
        self.assertEqual(view["reason"], "preparing")
        save_settings({"student_enabled": True, "daily_limit_usd": 100})
        row = find_by_token(row["token"])
        row["expires_at"] = (now() - timedelta(minutes=1)).isoformat(timespec="seconds")
        write_json(data_dir() / "assignments" / f"{row['id']}.json", row)
        self.assertEqual(availability(row, student_enabled=True), "expired")
        fresh = create_assignment({"text": "One more topic.", "max_submissions": 1})
        token = fresh["token"]

        def send(device):
            return self.client.post(
                f"/rec/api/a/{token}/submit",
                data={"audio": (self._wav(), "a.m4a"), "duration_ms": "9000", "device_id": device},
                content_type="multipart/form-data",
            )

        self.assertEqual(send("device-aaaa").status_code, 202)
        blocked = send("device-bbbb")
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.get_json()["error"], "full")
        other = create_assignment({"text": "Attempts.", "max_submissions": 40})
        token = other["token"]
        self.assertEqual(send("same-device").status_code, 202)
        self.assertEqual(send("same-device").status_code, 202)
        third = send("same-device")
        self.assertEqual(third.status_code, 409)
        self.assertEqual(third.get_json()["error"], "attempts")
        short = self.client.post(
            f"/rec/api/a/{token}/submit",
            data={"audio": (self._wav(100), "a.m4a"), "duration_ms": "1000", "device_id": "same-device"},
            content_type="multipart/form-data",
        )
        self.assertEqual(short.get_json()["error"], "too_short")

    def test_prep_zero_is_allowed(self):
        row = create_assignment({"text": "No preparation.", "prep_sec": 0, "speak_sec": 60})
        self.assertEqual(row["prep_sec"], 0)


if __name__ == "__main__":
    unittest.main()
