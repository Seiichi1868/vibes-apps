"""未ログイン時の見本クラス表示と、保存操作の拒否。"""
from __future__ import annotations

import os
import tempfile
import unittest

_ENV_KEYS = ("ADMIN_PASSWORD", "NEWS_DATA_DIR", "RENDER")
_OWNER = "test-admin-password"


def _clear_env() -> None:
    for key in _ENV_KEYS:
        os.environ.pop(key, None)


class NewsSamplePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.flask_test_app import get_test_app

        cls.app = get_test_app()

    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in _ENV_KEYS}
        _clear_env()
        self._data = tempfile.TemporaryDirectory()
        os.environ["NEWS_DATA_DIR"] = self._data.name
        os.environ["ADMIN_PASSWORD"] = _OWNER
        import news_app.services.storage as storage
        from pathlib import Path

        data = Path(self._data.name)
        self._storage_paths = {
            "DATA_DIR": storage.DATA_DIR,
            "STATE_FILE": storage.STATE_FILE,
            "ROSTER_FILE": storage.ROSTER_FILE,
            "SUBMISSIONS_FILE": storage.SUBMISSIONS_FILE,
        }
        storage.DATA_DIR = data
        storage.STATE_FILE = data / "app_state.json"
        storage.ROSTER_FILE = data / "roster.json"
        storage.SUBMISSIONS_FILE = data / "submissions.json"
        self.client = self.app.test_client()
        self.storage = storage

    def tearDown(self):
        for key, value in self._storage_paths.items():
            setattr(self.storage, key, value)
        self._data.cleanup()
        _clear_env()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _login_owner(self):
        res = self.client.post("/news/admin/api/login", json={"password": _OWNER})
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))

    def _make_sample(self):
        created = self.storage.create_class("test1")
        class_id = created["id"]
        self.storage.update_class_current(
            class_id,
            {
                "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "title": "Sample Video",
                "lesson_name": "Sample Lesson",
                "script": "SAMPLE-SCRIPT-XYZ",
                "start_seconds": 10,
                "end_seconds": 40,
            },
        )
        self.storage.archive_class_current(class_id, title="SAMPLE-ARCHIVE", lesson_name="Sample Lesson")
        return class_id

    def test_anonymous_sees_sample_without_stored_name(self):
        class_id = self._make_sample()
        anon = self.app.test_client()
        page = anon.get("/news/admin/")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn("SAMPLE-SCRIPT-XYZ", html)
        self.assertIn("SAMPLE-ARCHIVE", html)
        self.assertIn("クラス未設定", html)
        self.assertIn("見本の授業です", html)
        self.assertIn('data-support-id="vocab"', html)
        self.assertIn("news/js/admin.js?v=20261019c", html)
        self.assertNotIn(">test1<", html)
        self.assertNotIn('data-tab="results"', html)
        self.assertEqual(self.storage.get_class(class_id)["name"], "test1")
        self.assertNotIn("SAMPLE-STUDENT", html)

    def test_anonymous_cannot_mutate_sample_or_read_students(self):
        from news_app.services.storage import save_submission

        class_id = self._make_sample()
        before = self.storage.get_active_class_id()
        script_before = self.storage.get_class(class_id)["current"]["script"]
        save_submission(
            class_id=class_id,
            class_name="test1",
            student_hr_class="1",
            student_number="1",
            student_name="SAMPLE-STUDENT",
            transcript="hello",
            feedback="ok",
            level="A2",
            lesson_title="Sample",
            lesson_key_value="k",
            lesson_video_id="dQw4w9WgXcQ",
        )
        anon = self.app.test_client()
        page = anon.get("/news/admin/")
        self.assertNotIn("SAMPLE-STUDENT", page.get_data(as_text=True))
        saved = anon.post(
            "/news/admin/api/class/lesson",
            json={"class_id": class_id, "script": "hacked", "url": "https://youtu.be/dQw4w9WgXcQ", "start_time": "0:01", "end_time": "0:02"},
        )
        self.assertEqual(saved.status_code, 401)
        selected = anon.post("/news/admin/api/classes/select", json={"class_id": class_id})
        self.assertEqual(selected.status_code, 401)
        self.assertEqual(anon.get("/news/admin/api/submissions").status_code, 401)
        self.assertEqual(anon.get(f"/news/admin/api/roster/{class_id}").status_code, 401)
        self.assertEqual(anon.get("/news/admin/api/access-settings").status_code, 401)
        self.assertEqual(anon.post("/news/admin/api/class/archive/delete", json={"class_id": class_id, "archive_index": 0}).status_code, 401)
        self.assertEqual(self.storage.get_active_class_id(), before)
        self.assertEqual(self.storage.get_class(class_id)["current"]["script"], script_before)
        self.assertEqual(self.storage.get_class(class_id)["name"], "test1")
        public = anon.get(f"/news/api/roster/{class_id}")
        self.assertEqual(public.status_code, 200)

    def test_missing_sample_falls_back_and_login_required_redirects(self):
        anon = self.app.test_client()
        empty = anon.get("/news/admin/")
        self.assertEqual(empty.status_code, 200)
        self.assertNotIn("見本の授業です", empty.get_data(as_text=True))
        self.assertIn("クラス未作成", empty.get_data(as_text=True))

        self._make_sample()
        self._login_owner()
        self.client.post("/news/admin/api/access-settings", json={"require_teacher_login": True})
        gated = self.app.test_client().get("/news/admin/")
        self.assertEqual(gated.status_code, 302)
        self.assertIn("/news/admin/login", gated.headers.get("Location", ""))

    def test_owner_still_sees_stored_class_name(self):
        self._make_sample()
        self._login_owner()
        page = self.client.get("/news/admin/")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn(">test1<", html)
        self.assertNotIn("見本の授業です", html)
        self.assertIn('data-tab="results"', html)
        self.assertIn("window.ADMIN_SAMPLE_READONLY = false", html)
