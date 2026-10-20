"""Toolbox の教室向け QR ツール。"""
from __future__ import annotations

import base64
import json
import re
import tempfile
import unittest
from pathlib import Path

from tests.flask_test_app import get_test_app

import toolbox.storage as storage
from toolbox.tools.qr.make import normalize_url, png_data_uri


class QrNormalizeTests(unittest.TestCase):
    def test_adds_https_and_strips_paste_wrappers(self):
        link, error = normalize_url("  <https://vibes-app-auz1.onrender.com/debate> \n")
        self.assertIsNone(error)
        self.assertEqual(link, "https://vibes-app-auz1.onrender.com/debate")

        link, error = normalize_url("vibes-lab.com/debate")
        self.assertIsNone(error)
        self.assertEqual(link, "https://vibes-lab.com/debate")

        link, error = normalize_url("localhost:5001/debate")
        self.assertIsNone(error)
        self.assertEqual(link, "https://localhost:5001/debate")

    def test_rejects_empty_and_non_http(self):
        self.assertEqual(normalize_url("   ")[1], "URLを入力してください。")
        self.assertEqual(normalize_url("javascript:alert(1)")[1], "http または https のURLだけ使えます。")
        self.assertEqual(normalize_url("ftp://example.com")[1], "http または https のURLだけ使えます。")


class QrToolRouteTests(unittest.TestCase):
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

    def _csrf(self):
        page = self.client.get("/toolbox/qr")
        self.assertEqual(page.status_code, 200)
        match = re.search(r'window\.TOOLBOX_CSRF = ("(?:\\.|[^"])*"|null);', page.get_data(as_text=True))
        self.assertIsNotNone(match)
        return json.loads(match.group(1))

    def test_page_lists_tool_and_renders_input(self):
        launcher = self.client.get("/toolbox/")
        self.assertEqual(launcher.status_code, 200)
        html = launcher.get_data(as_text=True)
        self.assertIn("/toolbox/qr", html)
        self.assertIn("QRコード", html)

        page = self.client.get("/toolbox/qr")
        self.assertEqual(page.status_code, 200)
        body = page.get_data(as_text=True)
        self.assertIn('id="tb-qr-input"', body)
        self.assertIn('id="tb-qr-image"', body)
        self.assertIn("大きく表示", body)
        self.assertIn("toolbox/js/qr.js", body)

    def test_api_returns_png_matching_news_segno_style(self):
        url = "https://vibes-app-auz1.onrender.com/debate"
        token = self._csrf()
        res = self.client.post(
            "/toolbox/api/qr",
            json={"url": url},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["link"], url)
        self.assertTrue(data["qr"].startswith("data:image/png;base64,"))
        self.assertEqual(data["qr"], png_data_uri(url))
        raw = base64.b64decode(data["qr"].split(",", 1)[1])
        self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_api_rejects_bad_url(self):
        token = self._csrf()
        res = self.client.post(
            "/toolbox/api/qr",
            json={"url": "javascript:alert(1)"},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
