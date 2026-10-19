"""News の教員アカウント、CNN10 検索の公開切替、アーカイブと提出の範囲。"""
from __future__ import annotations

import os
import tempfile
import unittest

_ENV_KEYS = ("ADMIN_PASSWORD", "NEWS_DATA_DIR", "RENDER")
_OWNER = "test-admin-password"


def _clear_env() -> None:
    for key in _ENV_KEYS:
        os.environ.pop(key, None)


class NewsTeacherAccountTests(unittest.TestCase):
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

    def tearDown(self):
        import news_app.services.storage as storage

        for key, value in self._storage_paths.items():
            setattr(storage, key, value)
        self._data.cleanup()
        _clear_env()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _login_owner(self, client=None):
        client = client or self.client
        res = client.post("/news/admin/api/login", json={"password": _OWNER})
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertEqual(res.get_json()["role"], "owner")

    def _issue(self, account_id="teacher1", password="pass-1234"):
        res = self.client.post("/news/admin/api/teachers", json={"id": account_id, "password": password})
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        return res.get_json()

    def _login_teacher(self, client, account_id="teacher1", password="pass-1234"):
        res = client.post(
            "/news/admin/api/login",
            json={"teacher_id": account_id, "password": password},
        )
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertEqual(res.get_json()["role"], "teacher")

    def _set_toggles(self, *, require=None, share=None):
        body = {}
        if require is not None:
            body["require_teacher_login"] = require
        if share is not None:
            body["share_archives"] = share
        res = self.client.post("/news/admin/api/access-settings", json=body)
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))

    def test_cnn10_search_is_public_until_teacher_login_required(self):
        anon = self.client.get("/news/admin/api/cnn10/library/search?q=mars")
        self.assertEqual(anon.status_code, 200, anon.get_data(as_text=True))
        page = self.client.get("/news/admin/")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(_OWNER, page.get_data(as_text=True))

        self._login_owner()
        self._set_toggles(require=True)
        logged_out = self.app.test_client()
        denied = logged_out.get("/news/admin/api/cnn10/library/search?q=mars")
        self.assertEqual(denied.status_code, 401)
        gated = logged_out.get("/news/admin/")
        self.assertEqual(gated.status_code, 302)
        self.assertIn("/news/admin/login", gated.headers.get("Location", ""))
        login_page = logged_out.get("/news/admin/login")
        self.assertEqual(login_page.status_code, 200)

    def test_issue_stop_resume_delete_and_session_invalidation(self):
        self._login_owner()
        issued = self._issue()
        self.assertIn("pass-1234", issued["copy_text"])
        self.assertIn("/news/admin/login", issued["copy_text"])
        listed = self.client.get("/news/admin/api/access-settings")
        self.assertEqual(listed.get_json()["accounts"][0]["password"], "pass-1234")

        short = self.client.post("/news/admin/api/teachers", json={"id": "ab", "password": "no"})
        self.assertEqual(short.status_code, 400)
        dup = self.client.post("/news/admin/api/teachers", json={"id": "teacher1", "password": "other-pass"})
        self.assertEqual(dup.status_code, 400)

        teacher = self.app.test_client()
        self._login_teacher(teacher)
        self.assertEqual(teacher.get("/news/admin/api/classes").status_code, 200)

        stopped = self.client.post("/news/admin/api/teachers/stop", json={"id": "teacher1"})
        self.assertEqual(stopped.status_code, 200)
        self.assertTrue(stopped.get_json()["accounts"][0]["disabled"])
        self.assertEqual(teacher.get("/news/admin/api/classes").status_code, 401)
        rejected = teacher.post(
            "/news/admin/api/login",
            json={"teacher_id": "teacher1", "password": "pass-1234"},
        )
        self.assertEqual(rejected.status_code, 403)

        resumed = self.client.post("/news/admin/api/teachers/resume", json={"id": "teacher1"})
        self.assertEqual(resumed.status_code, 200)
        self.assertFalse(resumed.get_json()["accounts"][0]["disabled"])
        self._login_teacher(teacher)
        self.assertEqual(teacher.get("/news/admin/api/status").get_json()["role"], "teacher")

        deleted = self.client.post("/news/admin/api/teachers/delete", json={"id": "teacher1"})
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(teacher.get("/news/admin/api/classes").status_code, 401)
        self.assertEqual(
            teacher.post(
                "/news/admin/api/login",
                json={"teacher_id": "teacher1", "password": "pass-1234"},
            ).status_code,
            403,
        )

    def test_archive_scope_share_and_submissions_stay_own_only(self):
        from news_app.services.storage import save_submission, update_class_current

        self._login_owner()
        self._issue("owner-teacher", "pass-1234")
        self._issue("other-teacher", "pass-9999")
        owner_class = self.client.post("/news/admin/api/classes", json={"name": "Owner Class"})
        self.assertEqual(owner_class.status_code, 200, owner_class.get_data(as_text=True))
        owner_id = owner_class.get_json()["class"]["id"]
        self.assertEqual(owner_class.get_json()["class"]["created_by"], "owner")

        teacher = self.app.test_client()
        other = self.app.test_client()
        self._login_teacher(teacher, "owner-teacher", "pass-1234")
        self._login_teacher(other, "other-teacher", "pass-9999")
        made = teacher.post("/news/admin/api/classes", json={"name": "Teacher Class"})
        self.assertEqual(made.status_code, 200, made.get_data(as_text=True))
        teacher_class_id = made.get_json()["class"]["id"]
        self.assertEqual(made.get_json()["class"]["created_by"], "owner-teacher")
        update_class_current(
            teacher_class_id,
            {"video_id": "dQw4w9WgXcQ", "script": "Hello class", "source_url": "https://youtu.be/dQw4w9WgXcQ"},
        )
        archived = teacher.post(
            "/news/admin/api/class/archive",
            json={"class_id": teacher_class_id, "title": "Lesson A"},
        )
        self.assertEqual(archived.status_code, 200, archived.get_data(as_text=True))
        self.assertEqual(archived.get_json()["class"]["archive"][0]["created_by"], "owner-teacher")

        own_made = other.post("/news/admin/api/classes", json={"name": "Other Class"})
        self.assertEqual(own_made.status_code, 200, own_made.get_data(as_text=True))
        other_class_id = own_made.get_json()["class"]["id"]

        hidden = other.get("/news/admin/api/classes")
        self.assertEqual([c["id"] for c in hidden.get_json()["classes"]], [other_class_id])
        self.assertEqual(other.get(f"/news/admin/api/classes/{teacher_class_id}").status_code, 403)
        active_before = self.client.get("/news/admin/api/classes").get_json()["active_class_id"]
        self.assertEqual(other.post("/news/admin/api/classes/select", json={"class_id": teacher_class_id}).status_code, 403)
        self.assertEqual(self.client.get("/news/admin/api/classes").get_json()["active_class_id"], active_before)
        self.assertEqual(other.get(f"/news/admin/api/submissions?class_id={teacher_class_id}").status_code, 403)
        self.assertEqual(
            other.post(
                "/news/admin/api/class/archive/copy",
                json={"class_id": teacher_class_id, "archive_index": 0, "target_class_id": other_class_id},
            ).status_code,
            403,
        )

        self._set_toggles(share=True)
        shared = other.get("/news/admin/api/classes")
        by_id = {c["id"]: c for c in shared.get_json()["classes"]}
        self.assertIn(teacher_class_id, by_id)
        self.assertIn(owner_id, by_id)
        self.assertFalse(by_id[teacher_class_id]["can_manage"])
        self.assertTrue(by_id[other_class_id]["can_manage"])
        viewed = other.get(f"/news/admin/api/classes/{teacher_class_id}")
        self.assertEqual(viewed.status_code, 200)
        self.assertEqual(viewed.get_json()["class"]["archive"][0]["title"], "Lesson A")
        self.assertFalse(viewed.get_json()["can_manage"])
        self.assertEqual(other.post("/news/admin/api/classes/select", json={"class_id": teacher_class_id}).status_code, 403)
        self.assertEqual(self.client.get("/news/admin/api/classes").get_json()["active_class_id"], active_before)
        copied = other.post(
            "/news/admin/api/class/archive/copy",
            json={"class_id": teacher_class_id, "archive_index": 0, "target_class_id": other_class_id},
        )
        self.assertEqual(copied.status_code, 200, copied.get_data(as_text=True))
        self.assertEqual(copied.get_json()["target_class"]["archive"][0]["title"], "Lesson A")
        rejected_dest = other.post(
            "/news/admin/api/class/archive/copy",
            json={"class_id": teacher_class_id, "archive_index": 0, "target_class_id": owner_id},
        )
        self.assertEqual(rejected_dest.status_code, 403)
        self.assertEqual(
            other.post("/news/admin/api/class/lesson/reset", json={"class_id": teacher_class_id}).status_code,
            403,
        )

        save_submission(
            class_id=teacher_class_id,
            class_name="Teacher Class",
            student_hr_class="1",
            student_number="2",
            student_name="Student",
            transcript="hello",
            feedback="ok",
            level="A2",
            lesson_title="Lesson A",
            lesson_key_value="k",
            lesson_video_id="dQw4w9WgXcQ",
        )
        save_submission(
            class_id=owner_id,
            class_name="Owner Class",
            student_hr_class="1",
            student_number="3",
            student_name="Owner Student",
            transcript="owner",
            feedback="ok",
            level="A2",
            lesson_title="Owner",
            lesson_key_value="o",
            lesson_video_id="dQw4w9WgXcQ",
        )
        own_only = other.get("/news/admin/api/submissions")
        self.assertEqual(own_only.status_code, 200)
        self.assertEqual(own_only.get_json()["submissions"], [])
        self.assertEqual(other.get(f"/news/admin/api/submissions?class_id={teacher_class_id}").status_code, 403)
        teacher_subs = teacher.get("/news/admin/api/submissions")
        self.assertEqual(
            [s.get("student_name") for s in teacher_subs.get_json()["submissions"] if s.get("class_id") == teacher_class_id],
            ["Student"],
        )
        self.assertEqual(teacher_subs.get_json()["submissions"][0]["student_name"], "Student")
        owner_subs = self.client.get("/news/admin/api/submissions")
        self.assertEqual(len(owner_subs.get_json()["submissions"]), 2)

        self.assertEqual(teacher.post("/news/admin/api/access-settings", json={"share_archives": False}).status_code, 403)
        self.assertEqual(teacher.get("/news/admin/api/access-settings").status_code, 403)
        self.assertEqual(teacher.post("/news/admin/api/settings", json={}).status_code, 403)

        roster = self.client.get(f"/news/api/roster/{teacher_class_id}")
        self.assertEqual(roster.status_code, 200)

    def test_teacher_login_uses_shared_lockout(self):
        self._login_owner()
        self._issue()
        attacker = self.app.test_client()
        for _ in range(5):
            res = attacker.post(
                "/news/admin/api/login",
                json={"teacher_id": "teacher1", "password": "wrong-pass"},
            )
            self.assertIn(res.status_code, {403, 429})
        locked = attacker.post("/news/admin/api/login", json={"password": _OWNER})
        self.assertEqual(locked.status_code, 429)
        locked_teacher = attacker.post(
            "/news/admin/api/login",
            json={"teacher_id": "teacher1", "password": "pass-1234"},
        )
        self.assertEqual(locked_teacher.status_code, 429)
