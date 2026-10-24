"""本番の SECRET_KEY と Toolbox ゲスト利用量。"""
from __future__ import annotations

import os
import unittest
from datetime import timedelta
from unittest.mock import patch

from flask_app.config import resolve_flask_secret_key
from toolbox.storage import now_dt


class SecretKeyTests(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in ("FLASK_SECRET_KEY", "RENDER", "FLASK_ENV", "ENV")}
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_production_without_key_fails(self):
        os.environ["RENDER"] = "true"
        with self.assertRaises(RuntimeError):
            resolve_flask_secret_key()

    def test_production_rejects_known_fallback(self):
        os.environ["FLASK_ENV"] = "production"
        os.environ["FLASK_SECRET_KEY"] = "your-secret-key-here"
        with self.assertRaises(RuntimeError):
            resolve_flask_secret_key()

    def test_local_uses_explicit_dev_fallback(self):
        self.assertEqual(resolve_flask_secret_key(), "local-dev-flask-secret")

    def test_configured_key_is_used(self):
        os.environ["RENDER"] = "true"
        os.environ["FLASK_SECRET_KEY"] = "real-production-secret"
        self.assertEqual(resolve_flask_secret_key(), "real-production-secret")


class GuestUsageTests(unittest.TestCase):
    def test_guest_windows_ignore_registered_users(self):
        from toolbox.usage import guest_usage_summary

        now = now_dt()
        users = [
            {"id": "guest-1", "is_guest": True},
            {"id": "teacher", "is_guest": False},
        ]
        rows = [
            {"user_id": "guest-1", "kind": "llm", "est_cost_usd": 0.2, "ts": now.isoformat(timespec="seconds")},
            {"user_id": "guest-1", "kind": "llm", "est_cost_usd": 0.3, "ts": (now - timedelta(days=3)).isoformat(timespec="seconds")},
            {"user_id": "guest-1", "kind": "llm", "est_cost_usd": 1.0, "ts": (now - timedelta(days=10)).isoformat(timespec="seconds")},
            {"user_id": "guest-1", "kind": "llm", "est_cost_usd": 4.0, "ts": (now - timedelta(days=40)).isoformat(timespec="seconds")},
            {"user_id": "teacher", "kind": "llm", "est_cost_usd": 9.0, "ts": now.isoformat(timespec="seconds")},
        ]
        with patch("toolbox.usage.list_users", return_value=users), patch("toolbox.usage.list_usage", return_value=rows):
            summary = guest_usage_summary(now)
        self.assertEqual(summary["day"]["count"], 1)
        self.assertEqual(summary["day"]["est_cost_usd"], 0.2)
        self.assertEqual(summary["week"]["count"], 2)
        self.assertEqual(summary["week"]["est_cost_usd"], 0.5)
        self.assertEqual(summary["month"]["count"], 3)
        self.assertEqual(summary["month"]["est_cost_usd"], 1.5)
