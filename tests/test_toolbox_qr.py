"""Toolbox の教室向け QR ツール。"""
from __future__ import annotations

import base64
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from tests.flask_test_app import get_test_app

import toolbox.config as tb_config
import toolbox.storage as storage
from toolbox.tools.qr.files import purge_expired
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


class QrFileRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self._saved = {
            "USERS_FILE": storage.USERS_FILE,
            "RECENT_TOOLS_FILE": storage.RECENT_TOOLS_FILE,
            "TOOL_SETTINGS_FILE": storage.TOOL_SETTINGS_FILE,
            "APP_SETTINGS_FILE": storage.APP_SETTINGS_FILE,
            "FAVORITES_FILE": storage.FAVORITES_FILE,
            "QR_FILES_DIR": tb_config.QR_FILES_DIR,
        }
        storage.USERS_FILE = root / "users.json"
        storage.RECENT_TOOLS_FILE = root / "recent.json"
        storage.TOOL_SETTINGS_FILE = root / "tools.json"
        storage.APP_SETTINGS_FILE = root / "app.json"
        storage.FAVORITES_FILE = root / "favorites.json"
        tb_config.QR_FILES_DIR = root / "qr_files"
        self.app = get_test_app()
        self.client = self.app.test_client()
        self.device = "ipad-class-1"

    def tearDown(self):
        for name, value in self._saved.items():
            if name == "QR_FILES_DIR":
                tb_config.QR_FILES_DIR = value
            else:
                setattr(storage, name, value)
        self.tmp.cleanup()

    def _csrf(self):
        page = self.client.get("/toolbox/qr")
        self.assertEqual(page.status_code, 200)
        match = re.search(r'window\.TOOLBOX_CSRF = ("(?:\\.|[^"])*"|null);', page.get_data(as_text=True))
        self.assertIsNotNone(match)
        return json.loads(match.group(1))

    def _upload(self, data, filename, token, ttl="7", device=None, csrf=True):
        headers = {}
        if device is not None:
            headers["X-Toolbox-Device"] = device
        if csrf and token:
            headers["X-CSRF-Token"] = token
        return self.client.post(
            "/toolbox/api/qr/files",
            data={"file": (io.BytesIO(data), filename), "ttl_days": ttl},
            headers=headers,
        )

    def test_upload_list_and_public_download(self):
        token = self._csrf()
        pdf = b"%PDF-1.4\n% toolbox qr\n"
        res = self._upload(pdf, "配布プリント.pdf", token, device=self.device)
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        body = res.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["file"]["name"], "配布プリント.pdf")
        self.assertIn("/toolbox/f/", body["file"]["url"])
        self.assertTrue(body["qr"].startswith("data:image/png;base64,"))

        listed = self.client.get(
            "/toolbox/api/qr/files",
            headers={"X-Toolbox-Device": self.device},
        )
        self.assertEqual(listed.status_code, 200)
        files = listed.get_json()["files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["id"], body["file"]["id"])
        self.assertTrue(files[0]["qr"].startswith("data:image/png;base64,"))

        guest = self.app.test_client()
        users_before = storage.list_users()
        path = "/toolbox/f/" + body["file"]["url"].rstrip("/").split("/toolbox/f/")[-1]
        downloaded = guest.get(path)
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.data, pdf)
        self.assertEqual(downloaded.mimetype, "application/pdf")
        self.assertEqual(downloaded.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("private", downloaded.headers.get("Cache-Control", ""))
        self.assertIn("filename*=UTF-8''", downloaded.headers.get("Content-Disposition", ""))
        self.assertIn("inline", downloaded.headers.get("Content-Disposition", ""))
        self.assertEqual(storage.list_users(), users_before)

    def test_rejects_bad_ext_magic_size_and_csrf(self):
        token = self._csrf()
        bad_ext = self._upload(b"hello", "notes.exe", token, device=self.device)
        self.assertEqual(bad_ext.status_code, 400)

        mismatch = self._upload(b"not a pdf", "notes.pdf", token, device=self.device)
        self.assertEqual(mismatch.status_code, 400)
        self.assertIn("一致", mismatch.get_json()["error"])

        huge = b"%PDF" + b"a" * (tb_config.QR_FILE_MAX_BYTES)
        too_big = self._upload(huge, "big.pdf", token, device=self.device)
        self.assertEqual(too_big.status_code, 413)

        no_csrf = self._upload(b"%PDF-1.4\n", "ok.pdf", token, device=self.device, csrf=False)
        self.assertEqual(no_csrf.status_code, 403)

    def test_expired_is_404_and_purge_removes_files(self):
        token = self._csrf()
        pdf = b"%PDF-1.4\nexpired\n"
        res = self._upload(pdf, "old.pdf", token, ttl="1", device=self.device)
        self.assertEqual(res.status_code, 200)
        file_id = res.get_json()["file"]["id"]
        meta_path = tb_config.QR_FILES_DIR / f"{file_id}.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["expires_at"] = "2000-01-01T00:00:00+09:00"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        public_path = "/toolbox/f/" + meta["token"]
        missing = self.app.test_client().get(public_path)
        self.assertEqual(missing.status_code, 404)
        self.assertIn("期限", missing.get_data(as_text=True))
        self.assertTrue(meta_path.is_file())
        removed = purge_expired()
        self.assertGreaterEqual(removed, 1)
        self.assertFalse(meta_path.is_file())
        self.assertFalse((tb_config.QR_FILES_DIR / f"{file_id}.pdf").is_file())

    def test_other_device_cannot_list_or_delete(self):
        token = self._csrf()
        res = self._upload(b"%PDF-1.4\nmine\n", "mine.pdf", token, device=self.device)
        self.assertEqual(res.status_code, 200)
        file_id = res.get_json()["file"]["id"]
        other = "other-device"
        listed = self.client.get("/toolbox/api/qr/files", headers={"X-Toolbox-Device": other})
        self.assertEqual(listed.get_json()["files"], [])
        denied = self.client.delete(
            f"/toolbox/api/qr/files/{file_id}",
            headers={"X-CSRF-Token": token, "X-Toolbox-Device": other},
        )
        self.assertEqual(denied.status_code, 404)
        still = self.client.get("/toolbox/api/qr/files", headers={"X-Toolbox-Device": self.device})
        self.assertEqual(len(still.get_json()["files"]), 1)


if __name__ == "__main__":
    unittest.main()
