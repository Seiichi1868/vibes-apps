"""スピーチ理解度チェックの引き継ぎコード取り込み。"""
from __future__ import annotations

import base64
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.flask_test_app import get_test_app

import toolbox.storage as storage
from toolbox.auth import _serializer
from toolbox.config import COOKIE_NAME


def _code(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return "TBTALK1:" + base64.b64encode(raw).decode("ascii")


class TalkImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self._saved = {
            "USERS_FILE": storage.USERS_FILE,
            "TALK_SESSIONS_DIR": storage.TALK_SESSIONS_DIR,
            "RECENT_TOOLS_FILE": storage.RECENT_TOOLS_FILE,
            "TOOL_SETTINGS_FILE": storage.TOOL_SETTINGS_FILE,
            "APP_SETTINGS_FILE": storage.APP_SETTINGS_FILE,
            "FAVORITES_FILE": storage.FAVORITES_FILE,
        }
        storage.USERS_FILE = root / "users.json"
        storage.TALK_SESSIONS_DIR = root / "talk_sessions"
        storage.RECENT_TOOLS_FILE = root / "recent.json"
        storage.TOOL_SETTINGS_FILE = root / "tools.json"
        storage.APP_SETTINGS_FILE = root / "app.json"
        storage.FAVORITES_FILE = root / "favorites.json"
        storage.TALK_SESSIONS_DIR.mkdir()
        self.app = get_test_app()
        self.client = self.app.test_client()
        self.generate = patch("toolbox.tools.talk_check.generate.generate_questions", side_effect=AssertionError("openai"))
        self.generate.start()

    def tearDown(self):
        self.generate.stop()
        for name, value in self._saved.items():
            setattr(storage, name, value)
        self.tmp.cleanup()

    def _csrf(self, client):
        page = client.get("/toolbox/talk-check")
        self.assertEqual(page.status_code, 200)
        match = re.search(r'window\.TOOLBOX_CSRF = ("(?:\\.|[^"])*"|null);', page.get_data(as_text=True))
        self.assertIsNotNone(match)
        return json.loads(match.group(1))

    def _user_id(self, client):
        with self.app.app_context():
            raw = client.get_cookie(COOKIE_NAME, path="/toolbox")
            self.assertIsNotNone(raw)
            data = _serializer().loads(raw.value)
        return data["uid"]

    def _post(self, client, code, device):
        token = self._csrf(client)
        return client.post(
            "/toolbox/api/talk/import",
            json={"code": code},
            headers={"X-CSRF-Token": token, "X-Toolbox-Device": device},
        )

    def test_import_creates_session_without_audio(self):
        long_q = "Q" * 500
        code = _code({
            "title": "授業A",
            "level": "B1",
            "transcript": "Hello class. " * 3,
            "browser_transcript": "hello",
            "questions": [{
                "question": long_q,
                "model_answer": "Because it rained.",
                "type": "inference",
                "included": True,
            }],
            "wait_prompt": "Talk.",
            "notes": "note",
            "include_inference": True,
            "count_requested": 4,
            "keywords": "rain",
            "audio_file": "secret.webm",
        })
        res = self._post(self.client, code, "device-a")
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        body = res.get_json()
        session = body["session"]
        self.assertEqual(session["source"], "import")
        self.assertEqual(session["title"], "授業A")
        self.assertEqual(session["status"], "ready")
        self.assertFalse(session["has_audio"])
        self.assertEqual(len(session["questions"][0]["question"]), 400)
        self.assertEqual(session["questions"][0]["type"], "inference")
        stored = storage.load_talk_session(session["id"])
        self.assertEqual(stored["user_id"], self._user_id(self.client))
        self.assertEqual(stored["device_id"], "device-a")
        self.assertNotIn("audio_file", stored)
        self.assertEqual(stored["keywords"], "rain")
        self.assertTrue(stored["include_inference"])
        self.assertEqual(stored["count_requested"], 4)
        self.assertLessEqual(len(stored["transcript"]), 60000)

    def test_import_rejects_bad_code(self):
        res = self._post(self.client, "not-a-code", "device-a")
        self.assertEqual(res.status_code, 400)
        self.assertIn("読み取れ", res.get_json()["error"])
        broken = self._post(self.client, "TBTALK1:%%%", "device-a")
        self.assertEqual(broken.status_code, 400)
        self.assertIn("読み取れ", broken.get_json()["error"])
        listed = self._post(self.client, "TBTALK1:" + base64.b64encode(b"[1,2]").decode("ascii"), "device-a")
        self.assertEqual(listed.status_code, 400)
        self.assertIn("読み取れ", listed.get_json()["error"])

    def test_import_accepts_messy_paste(self):
        payload = {"title": "iPad", "transcript": "Pasted speech.", "questions": [], "level": "A2"}
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        standard = base64.b64encode(raw).decode("ascii")
        urlsafe = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

        cases = [
            standard,
            "tbtalk1：" + standard,
            "Tbtalk1:" + standard,
            '\n"TBTALK1:' + standard + '"\n',
            "メモ\u200b「TBTALK1:" + standard + "」",
            "TBTALK1:" + urlsafe,
            urlsafe,
        ]
        for code in cases:
            with self.subTest(code=code[:24]):
                res = self._post(self.client, code, "device-a")
                self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
                session = res.get_json()["session"]
                self.assertEqual(session["title"], "iPad")
                self.assertEqual(session["source"], "import")

    def test_import_on_other_device_and_user(self):
        code = _code({
            "title": "共有",
            "transcript": "A short speech about weather.",
            "questions": [],
            "level": "A2",
        })
        first = self._post(self.client, code, "phone-1")
        self.assertEqual(first.status_code, 200)
        owner_a = self._user_id(self.client)
        other = self.app.test_client()
        second = self._post(other, code, "pc-9")
        self.assertEqual(second.status_code, 200, second.get_data(as_text=True))
        session = second.get_json()["session"]
        self.assertEqual(session["status"], "transcribed")
        self.assertNotEqual(session["id"], first.get_json()["session"]["id"])
        stored = storage.load_talk_session(session["id"])
        self.assertEqual(stored["device_id"], "pc-9")
        self.assertEqual(stored["user_id"], self._user_id(other))
        self.assertNotEqual(stored["user_id"], owner_a)
        self.assertEqual(stored["source"], "import")
        self.assertFalse(stored.get("audio_file"))

    def test_import_keeps_original_created_at(self):
        code = _code({
            "title": "元の授業",
            "transcript": "Original speech.",
            "questions": [],
            "created_at": "2024-03-15T09:30:00+09:00",
            "duration_sec": 95,
            "source": "record",
        })
        res = self._post(self.client, code, "device-a")
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        session = res.get_json()["session"]
        self.assertEqual(session["created_at"], "2024-03-15T09:30:00+09:00")
        self.assertEqual(session["duration_sec"], 95)
        self.assertEqual(session["source"], "import")
        stored = storage.load_talk_session(session["id"])
        self.assertEqual(stored["created_at"], "2024-03-15T09:30:00+09:00")
        self.assertEqual(stored["duration_sec"], 95)
        self.assertEqual(stored["source"], "import")
        self.assertTrue(stored.get("imported_at"))
        self.assertNotEqual(stored["imported_at"], stored["created_at"])

    def test_import_invalid_created_at_uses_now(self):
        frozen = "2026-10-20T12:00:00+09:00"
        code = _code({
            "title": "不正日時",
            "transcript": "Speech.",
            "created_at": "yesterday",
            "duration_sec": -3,
        })
        with patch("toolbox.tools.talk_check.routes.now_iso", return_value=frozen):
            res = self._post(self.client, code, "device-a")
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        stored = storage.load_talk_session(res.get_json()["session"]["id"])
        self.assertEqual(stored["created_at"], frozen)
        self.assertEqual(stored["imported_at"], frozen)
        self.assertEqual(stored["duration_sec"], 0)
        self.assertEqual(stored["source"], "import")

        missing = _code({"title": "日時なし", "transcript": "Speech."})
        with patch("toolbox.tools.talk_check.routes.now_iso", return_value=frozen):
            res = self._post(self.client, missing, "device-a")
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        stored = storage.load_talk_session(res.get_json()["session"]["id"])
        self.assertEqual(stored["created_at"], frozen)
        self.assertEqual(stored["source"], "import")

    def test_import_truncates_transcript(self):
        code = _code({"transcript": "x" * 70000, "title": "長い"})
        res = self._post(self.client, code, "device-a")
        self.assertEqual(res.status_code, 200)
        stored = storage.load_talk_session(res.get_json()["session"]["id"])
        self.assertEqual(len(stored["transcript"]), 60000)
        self.assertEqual(stored["status"], "transcribed")


if __name__ == "__main__":
    unittest.main()
