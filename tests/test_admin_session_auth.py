"""管理ログインが無いとき、各アプリの管理ルートは拒否される。"""
from __future__ import annotations

import os
import re
import tempfile
import time
import unittest
from unittest.mock import patch

_ENV_KEYS = (
    "ADMIN_PASSWORD",
    "GTEC_ADMIN_PASSWORD",
    "TRIGGER_ADMIN_PASSWORD",
    "CONJUGATE_ADMIN_PASSWORD",
    "LEVEL_CHECK_ADMIN_PASSWORD",
    "DEBATE_ADMIN_PASSWORD",
    "TOOLBOX_ADMIN_PASSWORD",
    "PRONOUNCE_DATA_DIR",
    "NEWS_DATA_DIR",
    "GTEC_DATA_DIR",
    "LEVEL_CHECK_DATA_DIR",
    "TRIGGER_DATA_DIR",
    "CONJUGATE_DATA_DIR",
    "TOOLBOX_DATA_DIR",
    "DEBATE_DATA_DIR",
    "RENDER",
)

_CONFIGURED = "test-admin-password"
_WRONG = "wrong-password"

_OPEN_ENDPOINTS = frozenset(
    {
        "admin.admin_login",
        "admin.admin_logout",
        "admin.admin_status",
        "main.admin_page",
        "main.admin_web_app_manifest",
        "news_admin.admin_login",
        "news_admin.admin_logout",
        "news_admin.admin_status",
        "news_admin.web_app_manifest",
        "news_admin.admin_index",
        "gtec_admin.admin_login",
        "gtec_admin.admin_logout",
        "gtec_admin.admin_status",
        "gtec_admin.web_app_manifest",
        "gtec_admin.admin_page",
        "level_check_admin.admin_login",
        "level_check_admin.admin_logout",
        "level_check_admin.admin_status",
        "level_check_admin.web_app_manifest",
        "level_check_admin.admin_page",
        "trigger_admin.admin_login",
        "trigger_admin.admin_logout",
        "trigger_admin.admin_status",
        "trigger_admin.web_app_manifest",
        "trigger_admin.admin_page",
        "conjugate_admin.admin_login",
        "conjugate_admin.admin_logout",
        "conjugate_admin.admin_status",
        "conjugate_admin.web_app_manifest",
        "conjugate_admin.admin_page",
        "toolbox.admin_page",
        "toolbox.admin_unlock",
        "toolbox.admin_web_app_manifest",
    }
)

_ADMIN_PREFIXES = (
    "admin.",
    "news_admin.",
    "gtec_admin.",
    "level_check_admin.",
    "trigger_admin.",
    "conjugate_admin.",
    "toolbox.",
)

_STUDENT_GETS = (
    "/",
    "/news/",
    "/news/api/roster/demo-class",
    "/news/api/youtube-transcript",
    "/api/gate/today",
    "/gtec",
    "/conjugate/",
    "/level_check/",
    "/trigger/",
    "/toolbox/",
    "/debate/",
)

_LOGIN_PATHS = (
    "/api/admin/login",
    "/news/admin/api/login",
    "/gtec/admin/api/login",
    "/level_check/admin/api/login",
    "/trigger/admin/api/login",
    "/conjugate/admin/api/login",
)


def _clear_env() -> None:
    for key in _ENV_KEYS:
        os.environ.pop(key, None)


def _rule_path(rule) -> str:
    return re.sub(r"<([^>]+)>", "x", rule.rule)


def _rule_methods(rule):
    return sorted(m for m in (rule.methods or ()) if m not in {"HEAD", "OPTIONS"})


def _is_admin_rule(rule) -> bool:
    endpoint = rule.endpoint or ""
    path = rule.rule or ""
    if endpoint.startswith("debate_admin."):
        return False
    if not any(endpoint.startswith(prefix) for prefix in _ADMIN_PREFIXES):
        return False
    return "/admin" in path


class _EnvIsolation(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in _ENV_KEYS}
        _clear_env()
        self._data = tempfile.TemporaryDirectory()
        for key in (
            "PRONOUNCE_DATA_DIR",
            "NEWS_DATA_DIR",
            "GTEC_DATA_DIR",
            "LEVEL_CHECK_DATA_DIR",
            "TRIGGER_DATA_DIR",
            "CONJUGATE_DATA_DIR",
            "TOOLBOX_DATA_DIR",
            "DEBATE_DATA_DIR",
        ):
            os.environ[key] = os.path.join(self._data.name, key.lower())
        os.environ["ADMIN_PASSWORD"] = _CONFIGURED

    def tearDown(self):
        self._data.cleanup()
        _clear_env()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class AdminSessionHttpTests(_EnvIsolation):
    @classmethod
    def setUpClass(cls):
        from tests.flask_test_app import get_test_app

        cls.app = get_test_app()

    def setUp(self):
        super().setUp()
        self.client = self.app.test_client()

    def test_admin_pages_show_login_without_session(self):
        pages = (
            "/admin",
            "/news/admin/",
            "/gtec/admin",
            "/level_check/admin/",
            "/trigger/admin/",
            "/conjugate/admin/",
            "/toolbox/admin/",
        )
        for path in pages:
            response = self.client.get(path)
            self.assertIn(response.status_code, {200, 302}, msg=path)
            self.assertNotIn(_CONFIGURED, response.get_data(as_text=True))

    def test_every_protected_admin_route_is_401_or_302_when_logged_out(self):
        seen = []
        for rule in self.app.url_map.iter_rules():
            if not _is_admin_rule(rule):
                continue
            if rule.endpoint in _OPEN_ENDPOINTS:
                continue
            path = _rule_path(rule)
            for method in _rule_methods(rule):
                seen.append((method, path, rule.endpoint))
                response = self.client.open(path, method=method, json={})
                self.assertIn(
                    response.status_code,
                    {401, 302},
                    msg=f"{method} {path} endpoint={rule.endpoint} -> {response.status_code}",
                )
        self.assertGreater(len(seen), 20)

    def test_student_routes_stay_open(self):
        roster = self.client.get("/news/api/roster/demo-class")
        self.assertEqual(roster.status_code, 200)
        self.assertIn("students", roster.get_json() or {})
        for path in _STUDENT_GETS:
            response = self.client.get(path)
            self.assertNotIn(response.status_code, {401, 302}, msg=path)

    def test_login_cookie_and_then_admin_api(self):
        response = self.client.post("/api/admin/login", json={"password": _CONFIGURED})
        self.assertEqual(response.status_code, 200)
        cookie = response.headers.get("Set-Cookie") or ""
        self.assertIn("HttpOnly", cookie)
        self.assertRegex(cookie, r"SameSite=Lax")
        self.assertNotIn(_CONFIGURED, cookie)
        settings = self.client.get("/api/admin/languages")
        self.assertNotEqual(settings.status_code, 401)

    def test_login_fails_closed_when_unset(self):
        os.environ.pop("ADMIN_PASSWORD", None)
        response = self.client.post("/news/admin/api/login", json={"password": _CONFIGURED})
        self.assertEqual(response.status_code, 503)

    def test_per_app_password_override(self):
        os.environ["GTEC_ADMIN_PASSWORD"] = "gtec-only-password"
        self.assertEqual(
            self.client.post("/gtec/admin/api/login", json={"password": _CONFIGURED}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/gtec/admin/api/login", json={"password": "gtec-only-password"}).status_code,
            200,
        )

    def test_limiter_locks_after_five_failures(self):
        headers = {"X-Forwarded-For": "203.0.113.20"}
        clock = {"now": 1_700_000_000.0}

        def fake_time():
            return clock["now"]

        with patch("news_app.admin_auth.time.time", side_effect=fake_time):
            for _ in range(4):
                response = self.client.post(
                    "/news/admin/api/login",
                    json={"password": _WRONG},
                    headers=headers,
                )
                self.assertEqual(response.status_code, 403)
            fifth = self.client.post(
                "/news/admin/api/login",
                json={"password": _WRONG},
                headers=headers,
            )
            self.assertEqual(fifth.status_code, 429)
            clock["now"] += 15 * 60 + 1
            recovered = self.client.post(
                "/news/admin/api/login",
                json={"password": _CONFIGURED},
                headers=headers,
            )
            self.assertEqual(recovered.status_code, 200)

    def test_toolbox_admin_api_is_401_and_limiter_applies(self):
        closed = self.client.get("/toolbox/admin/api/talk/sessions")
        self.assertEqual(closed.status_code, 401)
        headers = {"X-Forwarded-For": "203.0.113.77"}
        clock = {"now": time.time()}

        def fake_time():
            return clock["now"]

        page = self.client.get("/toolbox/admin/")
        token = ""
        match = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True))
        if match:
            token = match.group(1)

        with patch("toolbox.admin_auth.time.time", side_effect=fake_time):
            for _ in range(5):
                self.client.post(
                    "/toolbox/admin/unlock",
                    data={"password": _WRONG, "csrf_token": token},
                    headers=headers,
                )
            locked = self.client.post(
                "/toolbox/admin/unlock",
                data={"password": _CONFIGURED, "csrf_token": token},
                headers=headers,
            )
            self.assertEqual(locked.status_code, 429)
            self.assertIn("試行回数", locked.get_data(as_text=True))

    def test_each_login_path_rejects_wrong_password(self):
        for path in _LOGIN_PATHS:
            response = self.client.post(path, json={"password": _WRONG})
            self.assertEqual(response.status_code, 403, msg=path)


if __name__ == "__main__":
    unittest.main()
