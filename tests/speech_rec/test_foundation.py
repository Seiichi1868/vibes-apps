"""保存の排他、費用集計、管理画面のログイン。"""
import json
import multiprocessing
import os
import unittest
from pathlib import Path

from speech_rec.pricing import estimate_eval_usd, estimate_whisper_usd
from speech_rec.settings import get_settings, save_settings
from speech_rec.store import append_line, write_json
from speech_rec.usage import daily_limit_reached, record_cost, summarize


def _append_many(path: str, prefix: str, count: int) -> None:
    target = Path(path)
    for i in range(count):
        append_line(target, json.dumps({"n": f"{prefix}-{i}"}))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(os.environ.get("TMPDIR") or "/tmp") / f"speech-rec-test-{os.getpid()}.jsonl"
        if self.path.exists():
            self.path.unlink()

    def tearDown(self):
        if self.path.exists():
            self.path.unlink()

    def test_two_processes_do_not_drop_lines(self):
        count = 40
        procs = [
            multiprocessing.Process(target=_append_many, args=(str(self.path), "a", count)),
            multiprocessing.Process(target=_append_many, args=(str(self.path), "b", count)),
        ]
        for proc in procs:
            proc.start()
        for proc in procs:
            proc.join(10)
            self.assertEqual(proc.exitcode, 0)
        lines = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(lines), count * 2)
        seen = {json.loads(line)["n"] for line in lines}
        self.assertEqual(len(seen), count * 2)

    def test_atomic_json_roundtrip(self):
        path = self.path.with_suffix(".json")
        write_json(path, {"ok": True, "n": 1})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["n"], 1)
        path.unlink()


class PricingTests(unittest.TestCase):
    def test_design_estimates(self):
        self.assertAlmostEqual(estimate_whisper_usd(70), 0.007, places=6)
        self.assertAlmostEqual(estimate_eval_usd("gpt-4o-mini", 2500, 600), 0.000735, places=6)


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(os.environ.get("TMPDIR") or "/tmp") / f"speech-rec-usage-{os.getpid()}"
        self.dir.mkdir(parents=True, exist_ok=True)
        os.environ["SPEECH_REC_DATA_DIR"] = str(self.dir)
        os.environ["ADMIN_PASSWORD"] = "test-admin-pass"

    def tearDown(self):
        for path in self.dir.glob("*"):
            path.unlink()
        self.dir.rmdir()

    def test_daily_sum_and_limit(self):
        self.assertFalse(daily_limit_reached())
        record_cost(1.25, kind="eval", model="gpt-4o-mini")
        record_cost(0.75, kind="whisper", model="whisper-1")
        summary = summarize()
        self.assertAlmostEqual(summary["today_usd"], 2.0, places=4)
        self.assertTrue(summary["over_daily_limit"])
        save_settings({"daily_limit_usd": 5})
        self.assertEqual(get_settings()["daily_limit_usd"], 5)
        self.assertFalse(daily_limit_reached())
        self.assertFalse(get_settings()["student_enabled"])


class AdminPageTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(os.environ.get("TMPDIR") or "/tmp") / f"speech-rec-admin-{os.getpid()}"
        self.dir.mkdir(parents=True, exist_ok=True)
        os.environ["SPEECH_REC_DATA_DIR"] = str(self.dir)
        os.environ["ADMIN_PASSWORD"] = "test-admin-pass"
        os.environ["FLASK_SECRET_KEY"] = "test-secret"
        from flask_app import create_app

        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        for path in self.dir.glob("*"):
            path.unlink()
        self.dir.rmdir()

    def test_admin_requires_password_and_has_no_student_entry(self):
        page = self.client.get("/rec/admin")
        self.assertEqual(page.status_code, 200)
        self.assertIn("管理パスワード", page.get_data(as_text=True))
        missing = self.client.get("/rec/not-a-student-token")
        self.assertEqual(missing.status_code, 404)
        denied = self.client.post("/rec/admin/unlock", json={"password": "test-admin-pass"})
        self.assertEqual(denied.status_code, 403)
        bad = self.client.post(
            "/rec/admin/unlock",
            json={"password": "nope"},
            headers={"X-Speech-Rec-Request": "1"},
        )
        self.assertEqual(bad.status_code, 401)
        ok = self.client.post(
            "/rec/admin/unlock",
            json={"password": "test-admin-pass"},
            headers={"X-Speech-Rec-Request": "1"},
        )
        self.assertEqual(ok.status_code, 200)
        opened = self.client.get("/rec/admin")
        self.assertIn("今日", opened.get_data(as_text=True))
        usage = self.client.get("/rec/api/t/usage", headers={"X-Speech-Rec-Request": "1"})
        self.assertEqual(usage.status_code, 200)
        self.assertIn("today_usd", usage.get_json())


if __name__ == "__main__":
    unittest.main()
