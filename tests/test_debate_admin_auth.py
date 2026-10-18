"""Debate 管理ログイン・試行制限・生徒ルートの開放を url_map から検証する。"""
from __future__ import annotations

import os
import re
import tempfile
import time
import unittest
from unittest.mock import patch

_ENV_KEYS = (
    "ADMIN_PASSWORD",
    "DEBATE_ADMIN_PASSWORD",
    "DEBATE_PREVIEW_SECRET",
    "DEBATE_DATA_DIR",
    "DEBATE_ADMIN_SESSION_TTL_SEC",
    "RENDER",
)

_CONFIGURED = "test-admin-password"
_OVERRIDE = "test-app-override"
_WRONG = "wrong-password"

_OPEN_ADMIN_ENDPOINTS = frozenset(
    {
        "debate_admin.admin_login",
        "debate_admin.admin_logout",
        "debate_admin.admin_status",
        "debate_admin.web_app_manifest",
        "debate_admin.admin_page",
    }
)

_PATH_ARGS = {
    "session_id": "sess-test",
    "affiliation_id": "aff-test",
    "script_id": "script-test",
    "part": "PM",
}

_STUDENT_GETS = (
    "/debate/",
    "/debate/watch",
    "/debate/watch/not-a-real-script",
    "/debate/session/not-a-real-session",
    "/debate/session/not-a-real-session/judge",
    "/debate/session/not-a-real-session/parts/PM/review",
    "/debate/api/sessions/not-a-real-session",
    "/debate/manifest.json",
)


def _clear_env() -> None:
    for key in _ENV_KEYS:
        os.environ.pop(key, None)


def _rule_path(rule) -> str:
    def repl(match):
        name = match.group(1).split(":")[-1]
        return _PATH_ARGS.get(name, "x")

    return re.sub(r"<([^>]+)>", repl, rule.rule)


def _rule_methods(rule):
    return sorted(m for m in (rule.methods or ()) if m not in {"HEAD", "OPTIONS"})


class _EnvIsolation(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in _ENV_KEYS}
        _clear_env()
        self._data = tempfile.TemporaryDirectory()
        os.environ["DEBATE_DATA_DIR"] = self._data.name
        os.environ["ADMIN_PASSWORD"] = _CONFIGURED

    def tearDown(self):
        self._data.cleanup()
        _clear_env()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class DebateAdminAuthHttpTests(_EnvIsolation):
    @classmethod
    def setUpClass(cls):
        from tests.flask_test_app import get_test_app

        cls.app = get_test_app()

    def setUp(self):
        super().setUp()
        self.client = self.app.test_client()

    def _login(self, password=_CONFIGURED, headers=None):
        return self.client.post(
            "/debate/admin/api/login",
            json={"password": password},
            headers=headers or {},
        )

    def _admin_rules(self):
        return [
            rule
            for rule in self.app.url_map.iter_rules()
            if (rule.endpoint or "").startswith("debate_admin.")
        ]

    def test_login_page_is_reachable_without_session(self):
        response = self.client.get("/debate/admin/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("管理ログイン", body)
        self.assertNotIn(_CONFIGURED, body)
        self.assertNotIn(_WRONG, body)

    def test_login_sets_httponly_samesite_session_cookie(self):
        response = self._login()
        self.assertEqual(response.status_code, 200)
        self.assertTrue((response.get_json() or {}).get("logged_in"))
        cookie = response.headers.get("Set-Cookie") or ""
        self.assertIn("session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertRegex(cookie, r"SameSite=Lax")
        self.assertNotIn(_CONFIGURED, cookie)
        self.assertNotIn(_CONFIGURED, response.get_data(as_text=True))

    def test_login_rejects_wrong_password(self):
        response = self._login(_WRONG)
        self.assertEqual(response.status_code, 403)
        self.assertFalse((response.get_json() or {}).get("ok", True))

    def test_login_fails_closed_when_unset(self):
        os.environ.pop("ADMIN_PASSWORD", None)
        os.environ.pop("DEBATE_ADMIN_PASSWORD", None)
        response = self._login(_CONFIGURED)
        self.assertEqual(response.status_code, 503)
        self.assertIn("設定されていません", (response.get_json() or {}).get("error") or "")

    def test_per_app_override_is_used_for_login(self):
        os.environ["DEBATE_ADMIN_PASSWORD"] = _OVERRIDE
        self.assertEqual(self._login(_CONFIGURED).status_code, 403)
        self.assertEqual(self._login(_OVERRIDE).status_code, 200)

    def test_logout_clears_session(self):
        self.assertEqual(self._login().status_code, 200)
        self.assertTrue(
            (self.client.get("/debate/admin/api/status").get_json() or {}).get("logged_in")
        )
        logged_out = self.client.post("/debate/admin/api/logout")
        self.assertEqual(logged_out.status_code, 200)
        status = self.client.get("/debate/admin/api/status")
        self.assertEqual(status.status_code, 200)
        self.assertFalse((status.get_json() or {}).get("logged_in"))
        self.assertEqual(self.client.get("/debate/admin/api/settings").status_code, 401)

    def test_every_protected_admin_route_is_401_or_302_when_logged_out(self):
        seen = []
        for rule in self._admin_rules():
            if rule.endpoint in _OPEN_ADMIN_ENDPOINTS:
                continue
            path = _rule_path(rule)
            for method in _rule_methods(rule):
                seen.append((method, path))
                response = self.client.open(path, method=method, json={})
                self.assertIn(
                    response.status_code,
                    {401, 302},
                    msg=f"{method} {path} endpoint={rule.endpoint} -> {response.status_code}",
                )
                if response.status_code == 401:
                    body = response.get_json(silent=True) or {}
                    self.assertFalse(body.get("ok", True))
        self.assertGreater(len(seen), 10)

    def test_every_admin_route_works_when_logged_in(self):
        self.assertEqual(self._login().status_code, 200)
        auth_failures = {401, 403, 429, 503}
        skip = {"debate_admin.admin_login", "debate_admin.admin_logout"}
        for rule in self._admin_rules():
            path = _rule_path(rule)
            for method in _rule_methods(rule):
                if rule.endpoint in skip:
                    continue
                response = self.client.open(path, method=method, json={})
                self.assertNotIn(
                    response.status_code,
                    auth_failures,
                    msg=f"{method} {path} endpoint={rule.endpoint} -> {response.status_code}",
                )

    def test_student_routes_stay_open_without_admin_login(self):
        for path in _STUDENT_GETS:
            response = self.client.get(path)
            self.assertNotEqual(response.status_code, 401, msg=path)
            self.assertNotEqual(response.status_code, 302, msg=path)

        lookup = self.client.post("/debate/api/sessions/lookup", json={"session_ids": []})
        self.assertEqual(lookup.status_code, 200)
        self.assertIn("sessions", lookup.get_json() or {})

        create = self.client.post("/debate/api/sessions", json={"motion": "Should homework be abolished?"})
        self.assertNotEqual(create.status_code, 401)
        self.assertIn(create.status_code, {400, 201})

        watch_audio = self.client.get("/debate/watch/not-a-real-script/audio/PM")
        self.assertNotEqual(watch_audio.status_code, 401)

    def test_admin_password_check_accepts_configured_password(self):
        ok = self.client.post(
            "/debate/api/admin-password-check",
            json={"admin_password": _CONFIGURED},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertTrue((ok.get_json() or {}).get("ok"))

    def test_limiter_locks_ip_after_five_failures_and_resets_after_window(self):
        headers = {"X-Forwarded-For": "203.0.113.10"}
        clock = {"now": 1_700_000_000.0}

        def fake_time():
            return clock["now"]

        with patch("debate.admin_auth.time.time", side_effect=fake_time):
            for _ in range(4):
                response = self.client.post(
                    "/debate/admin/api/login",
                    json={"password": _WRONG},
                    headers=headers,
                )
                self.assertEqual(response.status_code, 403)
            fifth = self.client.post(
                "/debate/admin/api/login",
                json={"password": _WRONG},
                headers=headers,
            )
            self.assertEqual(fifth.status_code, 429)
            locked_login = self.client.post(
                "/debate/admin/api/login",
                json={"password": _CONFIGURED},
                headers=headers,
            )
            self.assertEqual(locked_login.status_code, 429)
            locked_check = self.client.post(
                "/debate/api/admin-password-check",
                json={"admin_password": _CONFIGURED},
                headers=headers,
            )
            self.assertEqual(locked_check.status_code, 429)

            clock["now"] += 15 * 60 + 1
            after_window = self.client.post(
                "/debate/admin/api/login",
                json={"password": _WRONG},
                headers=headers,
            )
            self.assertEqual(after_window.status_code, 403)
            recovered = self.client.post(
                "/debate/admin/api/login",
                json={"password": _CONFIGURED},
                headers=headers,
            )
            self.assertEqual(recovered.status_code, 200)

    def test_limiter_uses_rightmost_forwarded_for_hop(self):
        spoofed = {"X-Forwarded-For": "198.51.100.1, 203.0.113.44"}
        other = {"X-Forwarded-For": "203.0.113.44, 198.51.100.9"}
        for _ in range(5):
            self.client.post(
                "/debate/api/admin-password-check",
                json={"admin_password": _WRONG},
                headers=spoofed,
            )
        locked = self.client.post(
            "/debate/api/admin-password-check",
            json={"admin_password": _CONFIGURED},
            headers=spoofed,
        )
        self.assertEqual(locked.status_code, 429)
        other_ip = self.client.post(
            "/debate/api/admin-password-check",
            json={"admin_password": _CONFIGURED},
            headers=other,
        )
        self.assertEqual(other_ip.status_code, 200)

    def test_global_cap_does_not_permanently_lock_owner(self):
        clock = {"now": 1_700_100_000.0}

        def fake_time():
            return clock["now"]

        with patch("debate.admin_auth.time.time", side_effect=fake_time):
            for index in range(29):
                headers = {"X-Forwarded-For": f"203.0.113.{index}"}
                response = self.client.post(
                    "/debate/admin/api/login",
                    json={"password": _WRONG},
                    headers=headers,
                )
                self.assertEqual(response.status_code, 403)
            thirtieth = self.client.post(
                "/debate/admin/api/login",
                json={"password": _WRONG},
                headers={"X-Forwarded-For": "203.0.113.29"},
            )
            self.assertEqual(thirtieth.status_code, 429)
            blocked = self.client.post(
                "/debate/admin/api/login",
                json={"password": _CONFIGURED},
                headers={"X-Forwarded-For": "203.0.113.200"},
            )
            self.assertEqual(blocked.status_code, 429)
            clock["now"] += 15 * 60 + 1
            recovered = self.client.post(
                "/debate/admin/api/login",
                json={"password": _CONFIGURED},
                headers={"X-Forwarded-For": "203.0.113.200"},
            )
            self.assertEqual(recovered.status_code, 200)

    def test_session_cookie_config_secure_only_on_render(self):
        from debate.admin_auth import configure_debate_session_cookie

        class _App:
            def __init__(self):
                self.config = {}

        local_app = _App()
        configure_debate_session_cookie(local_app)
        self.assertTrue(local_app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(local_app.config["SESSION_COOKIE_SAMESITE"], "Lax")
        self.assertNotIn("SESSION_COOKIE_SECURE", local_app.config)

        os.environ["RENDER"] = "true"
        render_app = _App()
        configure_debate_session_cookie(render_app)
        self.assertTrue(render_app.config["SESSION_COOKIE_SECURE"])


if __name__ == "__main__":
    unittest.main()
