"""Toolbox ランダム座席のクイック（保存なし）。"""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from tests.flask_test_app import get_test_app

import toolbox.storage as storage
from toolbox.storage import update_app_settings


class RandomSeatsQuickTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self._saved = {
            "USERS_FILE": storage.USERS_FILE,
            "RECENT_TOOLS_FILE": storage.RECENT_TOOLS_FILE,
            "TOOL_SETTINGS_FILE": storage.TOOL_SETTINGS_FILE,
            "APP_SETTINGS_FILE": storage.APP_SETTINGS_FILE,
            "FAVORITES_FILE": storage.FAVORITES_FILE,
        }
        storage.USERS_FILE = root / "users.json"
        storage.RECENT_TOOLS_FILE = root / "recent.json"
        storage.TOOL_SETTINGS_FILE = root / "tools.json"
        storage.APP_SETTINGS_FILE = root / "app.json"
        storage.FAVORITES_FILE = root / "favorites.json"
        self.app = get_test_app()
        self.client = self.app.test_client()

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(storage, name, value)
        self.tmp.cleanup()

    def test_logged_in_page_has_quick_controls(self):
        page = self.client.get("/toolbox/random-seats")
        self.assertEqual(page.status_code, 200)
        body = page.get_data(as_text=True)
        self.assertIn("__quick__", body)
        self.assertEqual(body.count('id="tb-quick"'), 1)
        self.assertIn('id="tb-popout"', body)
        self.assertIn('class="tb-seat-quick"', body)
        self.assertIn('<select id="tb-quick-count"', body)
        self.assertIn(">60</option>", body)
        self.assertNotIn("番号の範囲", body)
        self.assertNotIn("tb-quick-names", body)
        self.assertNotIn("tb-quick-from", body)
        self.assertIn("random_seats.js", body)
        js = Path("static/toolbox/js/random_seats.js").read_text(encoding="utf-8")
        self.assertIn('.tb-stage-setup #tb-quick', js)
        self.assertIn('"tb-room-save"', js)
        css = Path("static/toolbox/css/app.css").read_text(encoding="utf-8")
        self.assertIn("#tb-quick[hidden]", css)
        self.assertIn("display: none !important", css)
        sw = Path("static/toolbox/sw.js").read_text(encoding="utf-8")
        self.assertIn('const VERSION = "toolbox-v9"', sw)
        self.assertNotIn("tb-quick-mode-range", js)
        self.assertNotIn("quickNames", js)

    def test_logged_out_redirects_like_other_tools(self):
        update_app_settings({"login_required_enabled": True})
        page = self.client.get("/toolbox/random-seats")
        self.assertEqual(page.status_code, 302)
        self.assertIn("/toolbox/login", page.headers.get("Location", ""))
        self.assertIn("next=/toolbox/random-seats", page.headers.get("Location", ""))

    def test_quick_script_does_not_store_names(self):
        js = Path("static/toolbox/js/random_seats.js").read_text(encoding="utf-8")
        self.assertIn("toolbox.random_seats.quick.v1", js)
        match = re.search(r"function persistQuick\(\) \{([\s\S]*?)\n  \}", js)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("localStorage.setItem(QUICK_KEY", body)
        self.assertNotIn("names", body)
        self.assertNotIn("quickNames", body)
        self.assertNotIn("from:", body)
        saved = re.search(r"const saved = \{([\s\S]*?)\};", body)
        self.assertIsNotNone(saved)
        keys = re.findall(r"^\s*([A-Za-z0-9_]+)\s*:", saved.group(1), re.M)
        self.assertEqual(keys, ["count", "rows", "cols", "blocked", "absent", "seats"])
        json.dumps(keys)
