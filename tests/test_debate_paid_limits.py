"""Debate 有料APIの1日上限。"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from debate.paid_limits import LIMIT_MESSAGE, PaidLimitError, consume, refresh_paid_limit_toggle

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=JST)


class DebatePaidLimitTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        import debate.config as config
        import debate.paid_limits as paid
        import debate.settings as settings

        self._mods = (config, settings, paid)
        self._saved = {
            "config": config.DATA_DIR,
            "settings_data": settings.DATA_DIR,
            "settings_file": settings.SETTINGS_FILE,
            "paid": paid.DATA_DIR,
        }
        config.DATA_DIR = root
        settings.DATA_DIR = root
        settings.SETTINGS_FILE = root / "settings.json"
        paid.DATA_DIR = root
        (root / "locks").mkdir()

    def tearDown(self):
        config, settings, paid = self._mods
        config.DATA_DIR = self._saved["config"]
        settings.DATA_DIR = self._saved["settings_data"]
        settings.SETTINGS_FILE = self._saved["settings_file"]
        paid.DATA_DIR = self._saved["paid"]
        self._tmp.cleanup()

    def test_limit_blocks_without_counting_past_cap(self):
        for _ in range(20):
            consume("judge", now=NOW)
        with self.assertRaises(PaidLimitError) as caught:
            consume("judge", now=NOW)
        self.assertEqual(str(caught.exception), LIMIT_MESSAGE)
        usage = json.loads((Path(self._tmp.name) / "paid_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["counts"]["judge"], 20)
        consume("tts", now=NOW)
        self.assertEqual(json.loads((Path(self._tmp.name) / "paid_usage.json").read_text(encoding="utf-8"))["counts"]["tts"], 1)

    def test_toggle_off_allows_calls_and_keeps_other_settings(self):
        from debate.settings import update_settings

        update_settings(background_id="ocean", background_opacity=0.5)
        update_settings(
            paid_daily_limit_enabled=False,
            paid_daily_limit_disabled_at=NOW.isoformat(timespec="seconds"),
        )
        for _ in range(21):
            consume("script", now=NOW)
        from debate.settings import load_settings

        settings = load_settings()
        self.assertEqual(settings["background_id"], "ocean")
        self.assertEqual(settings["background_opacity"], 0.5)
        self.assertFalse(settings["paid_daily_limit_enabled"])

    def test_off_expires_after_24_hours(self):
        from debate.settings import update_settings

        disabled = NOW - timedelta(hours=24)
        update_settings(
            paid_daily_limit_enabled=False,
            paid_daily_limit_disabled_at=disabled.isoformat(timespec="seconds"),
        )
        refreshed = refresh_paid_limit_toggle(NOW)
        self.assertTrue(refreshed["paid_daily_limit_enabled"])
        self.assertIsNone(refreshed["paid_daily_limit_disabled_at"])
        for _ in range(20):
            consume("script", now=NOW)
        with self.assertRaises(PaidLimitError):
            consume("script", now=NOW)

    def test_get_tts_does_not_consume(self):
        from tests.flask_test_app import get_test_app

        audio = Path(self._tmp.name) / "clip.mp3"
        audio.write_bytes(b"not-really-audio")
        app = get_test_app()
        session = {
            "parts": [
                {
                    "part": "LO",
                    "speaker": "ai",
                    "tts_audio_file": "clip.mp3",
                }
            ]
        }
        with app.test_client() as client:
            with patch("debate.routes.load_session", return_value=session), patch(
                "debate.routes.part_is_ai", return_value=True
            ), patch("debate.routes.tts_path", return_value=audio), patch(
                "debate.paid_limits.consume"
            ) as consume_mock, patch("debate.routes.send_file", return_value=app.response_class(b"ok")):
                res = client.get("/debate/api/sessions/sess/parts/LO/tts")
        self.assertEqual(res.status_code, 200)
        consume_mock.assert_not_called()
