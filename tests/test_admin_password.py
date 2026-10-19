"""Admin passwords come from env vars, fail closed, and are compared in constant time."""
from __future__ import annotations

import os
import unittest

_ENV_KEYS = (
    "ADMIN_PASSWORD",
    "GTEC_ADMIN_PASSWORD",
    "TRIGGER_ADMIN_PASSWORD",
    "CONJUGATE_ADMIN_PASSWORD",
    "LEVEL_CHECK_ADMIN_PASSWORD",
    "DEBATE_ADMIN_PASSWORD",
    "TOOLBOX_ADMIN_PASSWORD",
    "DEBATE_PREVIEW_SECRET",
)

_CONFIGURED = "test-admin-password"
_OVERRIDE = "test-app-override"


def _clear_admin_env() -> None:
    for key in _ENV_KEYS:
        os.environ.pop(key, None)


class _EnvIsolation(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in _ENV_KEYS}
        _clear_admin_env()

    def tearDown(self):
        _clear_admin_env()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class AdminPasswordConfigTests(_EnvIsolation):
    def test_common_password_is_used_when_per_app_unset(self):
        os.environ["ADMIN_PASSWORD"] = _CONFIGURED
        from conjugate.config import admin_password_matches
        from debate.admin import admin_password_matches as debate_matches
        from gtec_app.admin import _password_ok
        from level_check.config import admin_password_matches as level_matches
        from toolbox.auth import verify_admin_panel_password
        from trigger.config import admin_password_matches as trigger_matches

        self.assertTrue(admin_password_matches(_CONFIGURED))
        self.assertTrue(debate_matches(_CONFIGURED))
        self.assertTrue(_password_ok({"admin_password": _CONFIGURED}))
        self.assertTrue(level_matches(_CONFIGURED))
        self.assertTrue(verify_admin_panel_password(_CONFIGURED))
        self.assertTrue(trigger_matches(_CONFIGURED))
        self.assertFalse(admin_password_matches("wrong-password"))

    def test_per_app_env_overrides_common(self):
        os.environ["ADMIN_PASSWORD"] = _CONFIGURED
        os.environ["GTEC_ADMIN_PASSWORD"] = _OVERRIDE
        os.environ["DEBATE_ADMIN_PASSWORD"] = _OVERRIDE
        os.environ["TOOLBOX_ADMIN_PASSWORD"] = _OVERRIDE
        from debate.admin import admin_password_matches
        from gtec_app.admin import _password_ok
        from toolbox.auth import verify_admin_panel_password

        self.assertTrue(_password_ok({"admin_password": _OVERRIDE}))
        self.assertFalse(_password_ok({"admin_password": _CONFIGURED}))
        self.assertTrue(admin_password_matches(_OVERRIDE))
        self.assertFalse(admin_password_matches(_CONFIGURED))
        self.assertTrue(verify_admin_panel_password(_OVERRIDE))
        self.assertFalse(verify_admin_panel_password(_CONFIGURED))

    def test_unset_matches_nothing(self):
        from conjugate.config import admin_password_matches, get_admin_password
        from debate.admin import admin_password_matches as debate_matches
        from toolbox.auth import verify_admin_panel_password

        self.assertEqual(get_admin_password(), "")
        self.assertFalse(admin_password_matches(""))
        self.assertFalse(admin_password_matches(None))
        self.assertFalse(debate_matches(""))
        self.assertFalse(verify_admin_panel_password(""))

    def test_blank_env_value_is_treated_as_unset(self):
        os.environ["ADMIN_PASSWORD"] = "   "
        from conjugate.config import admin_password_matches, get_admin_password

        self.assertEqual(get_admin_password(), "")
        self.assertFalse(admin_password_matches("   "))

    def test_preview_secret_fail_closed(self):
        from debate.script_storage import issue_preview_token, preview_token_valid

        with self.assertRaises(RuntimeError):
            issue_preview_token("script-id")
        self.assertFalse(preview_token_valid("script-id", "anything"))

    def test_preview_token_roundtrip_with_secret(self):
        os.environ["DEBATE_PREVIEW_SECRET"] = "preview-secret-for-tests"
        from debate.script_storage import issue_preview_token, preview_token_valid

        token = issue_preview_token("script-id")
        self.assertTrue(preview_token_valid("script-id", token))
        self.assertFalse(preview_token_valid("other-id", token))


class AdminPasswordHttpTests(_EnvIsolation):
    @classmethod
    def setUpClass(cls):
        from tests.flask_test_app import get_test_app

        cls.app = get_test_app()

    def setUp(self):
        super().setUp()
        os.environ["ADMIN_PASSWORD"] = _CONFIGURED
        self.client = self.app.test_client()

    def test_app_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_password_check_accepts_configured_password(self):
        response = self.client.post(
            "/api/admin/login",
            json={"password": _CONFIGURED},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue((response.get_json() or {}).get("ok"))

    def test_password_check_rejects_wrong_password(self):
        response = self.client.post(
            "/api/admin/login",
            json={"password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 403)

    def test_password_check_fails_closed_when_unset(self):
        os.environ.pop("ADMIN_PASSWORD", None)
        response = self.client.post(
            "/api/admin/login",
            json={"password": _CONFIGURED},
        )
        self.assertEqual(response.status_code, 503)
        body = response.get_json() or {}
        self.assertIn("設定されていません", body.get("error") or "")

    def test_news_password_check(self):
        ok = self.client.post(
            "/news/admin/api/login",
            json={"password": _CONFIGURED},
        )
        self.assertEqual(ok.status_code, 200)
        bad = self.client.post(
            "/news/admin/api/login",
            json={"password": "wrong-password"},
        )
        self.assertEqual(bad.status_code, 403)
        os.environ.pop("ADMIN_PASSWORD", None)
        unset = self.client.post(
            "/news/admin/api/login",
            json={"password": _CONFIGURED},
        )
        self.assertEqual(unset.status_code, 503)

    def test_debate_and_gtec_password_checks(self):
        debate_ok = self.client.post(
            "/debate/api/admin-password-check",
            json={"admin_password": _CONFIGURED},
        )
        self.assertEqual(debate_ok.status_code, 200)
        gtec_ok = self.client.post(
            "/gtec/admin/api/login",
            json={"password": _CONFIGURED},
        )
        self.assertEqual(gtec_ok.status_code, 200)
        debate_bad = self.client.post(
            "/debate/api/admin-password-check",
            json={"admin_password": "wrong-password"},
        )
        self.assertEqual(debate_bad.status_code, 403)


if __name__ == "__main__":
    unittest.main()
