import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SNIPER_API_KEY", "test-key-for-tests")
os.environ.setdefault("SNIPER_CONTROL_API_KEY", "test-control-key-for-tests")

# Importing the API must not initialize a production database in tests.
with patch("tools.intelligence.storage.ensure_intelligence_tables"):
    from tools import dashboard_api_server as api


def asgi_request(
    app,
    method,
    path,
    headers=None,
    cookies=None,
    body=None,
    client=("203.0.113.5", 50000),
):
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if cookies:
        hdrs.append(
            (b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode())
        )
    raw = b""
    if body is not None:
        raw = json.dumps(body).encode()
        hdrs.append((b"content-type", b"application/json"))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": hdrs,
        "client": client,
        "server": ("127.0.0.1", 8000),
    }
    messages = [{"type": "http.request", "body": raw, "more_body": False}]
    sent = []

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    payload = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    set_cookies = [v.decode() for k, v in start["headers"] if k == b"set-cookie"]
    return start["status"], set_cookies, payload


class DashboardAuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, value in (("CMD_DIR", self.tmp.name), ("_rate_limit_state", {})):
            patcher = patch.object(api, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def request(self, method, path, **kwargs):
        return asgi_request(api.app, method, path, **kwargs)

    def assert_unauthorized(self, response):
        status, cookies, payload = response
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(payload), {"detail": "Unauthorized"})
        self.assertEqual(cookies, [])
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_index_never_grants_control(self):
        status, cookies, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertTrue(any(api.READ_SESSION_COOKIE in c for c in cookies))
        self.assertFalse(any(api.CONTROL_SESSION_COOKIE in c for c in cookies))

    def test_loopback_read_cookie_cannot_control_even_with_equal_keys(self):
        for client in (("203.0.113.5", 50000), ("127.0.0.1", 50000)):
            self.assert_unauthorized(
                self.request(
                    "POST", "/api/v1/command", body={"action": "/panic"}, client=client
                )
            )
            with patch.object(api, "CONTROL_API_KEY", api.API_KEY):
                self.assert_unauthorized(
                    self.request(
                        "POST",
                        "/api/v1/command",
                        body={"action": "/panic"},
                        cookies={api.READ_SESSION_COOKIE: api.READ_SESSION_TOKEN},
                        client=client,
                    )
                )
        self.assert_unauthorized(
            self.request(
                "POST",
                "/api/v1/command",
                body={"action": "/panic"},
                headers={"X-API-Key": api.API_KEY},
            )
        )

    def test_control_session_requires_header_even_with_valid_cookie(self):
        for headers in ({}, {"X-Control-API-Key": "wrong"}, {"X-API-Key": api.API_KEY}):
            self.assert_unauthorized(
                self.request("POST", "/api/v1/session/control", headers=headers)
            )
        status, cookies, _ = self.request(
            "POST",
            "/api/v1/session/control",
            headers={"X-Control-API-Key": api.CONTROL_API_KEY},
        )
        self.assertEqual(status, 200)
        self.assertTrue(
            any(
                api.CONTROL_SESSION_COOKIE in c
                and "HttpOnly" in c
                and "SameSite=strict" in c
                for c in cookies
            )
        )
        cookie = {api.CONTROL_SESSION_COOKIE: api.CONTROL_SESSION_TOKEN}
        self.assert_unauthorized(
            self.request("POST", "/api/v1/session/control", cookies=cookie)
        )
        self.assertEqual(
            self.request(
                "POST", "/api/v1/command", cookies=cookie, body={"action": "/panic"}
            )[0],
            200,
        )

    def test_read_header_and_read_cookie_preserved(self):
        self.assertEqual(self.request("GET", "/api/v1/config/env")[0], 401)
        for credentials in (
            {"headers": {"X-API-Key": api.API_KEY}},
            {"cookies": {api.READ_SESSION_COOKIE: api.READ_SESSION_TOKEN}},
        ):
            status, _, payload = self.request(
                "GET", "/api/v1/config/env", **credentials
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(payload), {"status": "ok", "configs": {}})

    def test_read_session_cannot_generate_intelligence(self):
        with patch.object(api, "generate_full_intelligence_cycle") as generate:
            response = self.request(
                "POST",
                "/api/v1/intelligence/generate",
                cookies={api.READ_SESSION_COOKIE: api.READ_SESSION_TOKEN},
            )
        self.assert_unauthorized(response)
        generate.assert_not_called()

    def test_control_header_can_generate_intelligence(self):
        with patch.object(
            api,
            "generate_full_intelligence_cycle",
            return_value={"daily_path": "daily", "weekly_path": "weekly"},
        ) as generate:
            status, cookies, payload = self.request(
                "POST",
                "/api/v1/intelligence/generate",
                headers={"X-Control-API-Key": api.CONTROL_API_KEY},
            )
        self.assertEqual(status, 200)
        self.assertEqual(cookies, [])
        self.assertEqual(
            json.loads(payload),
            {
                "ok": True,
                "daily_path": "daily",
                "weekly_path": "weekly",
                "advisories": 0,
            },
        )
        generate.assert_called_once_with(db_path=api.DB_PATH)

    def test_ui_control_requests_share_auth_retry_and_visible_errors(self):
        html = (Path(api.STATIC_DIR) / "index.html").read_text()
        self.assertTrue("async function controlRequest(" in html)
        helper = html.split("async function controlRequest(")[-1].split(
            "function switchTab"
        )[0]
        for token in (
            "response.status === 401",
            "window.prompt(",
            "localStorage.setItem('sniper_control_key', key)",
            "if (!response.ok)",
            "showToast(",
        ):
            self.assertTrue(token in helper, token)
        self.assertEqual(helper.count("window.prompt("), 1)
        self.assertEqual(helper.count("await fetch("), 2)
        for route in (
            "/command",
            "/trade/close",
            "/trade/breakeven",
            "/intelligence/generate",
        ):
            self.assertTrue("controlRequest(API + '" + route + "'" in html, route)

    def test_ui_sends_matching_control_header(self):
        html = (Path(api.STATIC_DIR) / "index.html").read_text()
        self.assertIn("headers['X-Control-API-Key'] = k;", html)
        self.assertNotIn("headers['X-Control-Key']", html)
