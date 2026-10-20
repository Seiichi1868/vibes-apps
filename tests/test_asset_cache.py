"""HTML/JSON の no-cache と、JS/CSS の内容ハッシュ版付け。"""
from __future__ import annotations

import re
import unittest

from flask import render_template_string

from tests.flask_test_app import get_test_app


class AssetCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_test_app()
        cls.client = cls.app.test_client()

    def test_url_for_replaces_manual_version_with_content_hash(self):
        with self.app.test_request_context("/"):
            html = render_template_string(
                "{{ url_for('static', filename='css/style.css', v='manual-version') }}"
            )
        self.assertRegex(html, r"/static/css/style\.css\?v=[0-9a-f]{10}")
        self.assertNotIn("manual-version", html)

    def test_blueprint_static_is_hashed(self):
        with self.app.test_request_context("/conjugate/"):
            html = render_template_string(
                "{{ url_for('conjugate.static', filename='js/quiz.js', v='20260101a') }}"
            )
        self.assertRegex(html, r"/conjugate/static/js/quiz\.js\?v=[0-9a-f]{10}")
        self.assertNotIn("20260101a", html)

    def test_audio_url_keeps_caller_query(self):
        with self.app.test_request_context("/"):
            html = render_template_string(
                "{{ url_for('static', filename='audio/conjugate/sfx-tap.mp3', v='keep-me') }}"
            )
        self.assertIn("v=keep-me", html)

    def test_html_and_json_are_not_cached(self):
        page = self.client.get("/conjugate/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers.get("Cache-Control"), "no-cache")
        health = self.client.get("/conjugate/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.mimetype, "application/json")
        self.assertEqual(health.headers.get("Cache-Control"), "no-cache")

    def test_hashed_css_is_immutable_and_plain_css_is_revalidated(self):
        with self.app.test_request_context("/"):
            hashed = render_template_string("{{ url_for('static', filename='css/style.css') }}")
        match = re.search(r"\?v=([0-9a-f]{10})", hashed)
        self.assertIsNotNone(match)
        versioned = self.client.get(hashed)
        self.assertEqual(versioned.status_code, 200)
        self.assertIn("immutable", versioned.headers.get("Cache-Control", ""))
        plain = self.client.get("/static/css/style.css")
        self.assertEqual(plain.headers.get("Cache-Control"), "no-cache")

    def test_manifest_is_revalidated(self):
        manifest = self.client.get("/static/manifest.json")
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest.headers.get("Cache-Control"), "no-cache")


if __name__ == "__main__":
    unittest.main()
