import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import server


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_db_path = server.DB_PATH
        server.DB_PATH = Path(self.temp_dir.name) / "stock-records.sqlite3"
        server.ensure_database()

    def tearDown(self):
        server.DB_PATH = self.original_db_path

    def set_env(self, **values):
        original = {key: os.environ.get(key) for key in values}
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        def restore():
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(restore)

    def test_create_authenticated_session_persists_user_and_returns_session_cookie(self):
        profile = {
            "sub": "google-user-123",
            "email": "user@example.com",
            "email_verified": True,
            "name": "測試使用者",
            "picture": "https://example.com/avatar.png",
        }

        session = server.create_authenticated_session(profile)

        self.assertEqual(session["email"], "user@example.com")
        self.assertIn("Set-Cookie", session)
        self.assertIn("stock_journal_session=", session["Set-Cookie"])
        self.assertIn("HttpOnly", session["Set-Cookie"])
        user = server.get_authenticated_user_from_cookie(session["Set-Cookie"])
        self.assertEqual(user["email"], "user@example.com")
        self.assertEqual(user["name"], "測試使用者")

    def test_verify_google_identity_requires_configured_audience_and_verified_email(self):
        def fake_tokeninfo(_credential):
            return {
                "sub": "abc",
                "aud": "client-123.apps.googleusercontent.com",
                "email": "user@example.com",
                "email_verified": "true",
                "name": "User",
            }

        profile = server.verify_google_identity(
            "credential-token",
            client_id="client-123.apps.googleusercontent.com",
            tokeninfo_fetcher=fake_tokeninfo,
        )

        self.assertEqual(profile["email"], "user@example.com")

        with self.assertRaises(ValueError):
            server.verify_google_identity(
                "credential-token",
                client_id="other-client-id",
                tokeninfo_fetcher=fake_tokeninfo,
            )

    def test_api_paths_are_protected_except_health_and_auth_endpoints(self):
        self.assertFalse(server.requires_authentication("/api/health"))
        self.assertFalse(server.requires_authentication("/api/auth/config"))
        self.assertFalse(server.requires_authentication("/api/auth/google/start"))
        self.assertFalse(server.requires_authentication("/api/auth/google/callback"))
        self.assertFalse(server.requires_authentication("/api/auth/google"))
        self.assertFalse(server.requires_authentication("/login.html"))
        self.assertTrue(server.requires_authentication("/api/trades"))
        self.assertTrue(server.requires_authentication("/"))
        self.assertTrue(server.requires_authentication("/index.html"))

    def test_http_requests_require_login_and_google_login_sets_cookie(self):
        original_verify = server.verify_google_identity
        server.verify_google_identity = lambda credential: {
            "sub": "google-user-456",
            "email": "web-user@example.com",
            "email_verified": True,
            "name": "Web User",
            "picture": "",
        }
        self.addCleanup(lambda: setattr(server, "verify_google_identity", original_verify))

        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.StockRequestHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(httpd.shutdown)
        host, port = httpd.server_address

        conn = http.client.HTTPConnection(host, port, timeout=5)
        self.addCleanup(conn.close)

        conn.request("GET", "/api/health")
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        response.read()

        conn.request("GET", "/login.html")
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        login_html = response.read().decode("utf-8")
        self.assertIn("Log in with Google", login_html)
        self.assertIn("google-login-button", login_html)
        self.assertIn('href="/api/auth/google/start"', login_html)
        self.assertNotIn("auth-status", login_html)
        self.assertNotIn("尚未設定 GOOGLE_CLIENT_ID", login_html)
        self.assertNotIn("disabled", login_html)

        conn.request("GET", "/auth.js")
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        auth_js = response.read().decode("utf-8")
        self.assertIn("aria-busy", auth_js)

        self.set_env(
            GOOGLE_CLIENT_ID="client-123.apps.googleusercontent.com",
            GOOGLE_CLIENT_SECRET="secret-123",
            REDIRECT_URI="http://127.0.0.1/callback",
        )
        conn.request("GET", "/api/auth/google/start")
        response = conn.getresponse()
        self.assertEqual(response.status, 302)
        location = response.getheader("Location")
        self.assertTrue(location.startswith("https://accounts.google.com/o/oauth2/v2/auth?"))
        query = parse_qs(urlparse(location).query)
        self.assertEqual(query["response_type"], ["code"])
        self.assertIn("client_id=client-123.apps.googleusercontent.com", location)
        self.assertIn("redirect_uri=http%3A%2F%2F127.0.0.1%2Fcallback", location)
        self.assertIn("oauth_state=", response.getheader("Set-Cookie"))
        response.read()

        conn.request("GET", "/api/trades")
        response = conn.getresponse()
        self.assertEqual(response.status, 401)
        response.read()

        body = json.dumps({"credential": "fake-google-id-token"})
        conn.request(
            "POST",
            "/api/auth/google",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        cookie = response.getheader("Set-Cookie")
        self.assertIn("stock_journal_session=", cookie)
        response.read()

        conn.request("GET", "/api/me", headers={"Cookie": cookie})
        response = conn.getresponse()
        self.assertEqual(response.status, 404)
        response.read()

        conn.request("GET", "/api/auth/me", headers={"Cookie": cookie})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["user"]["email"], "web-user@example.com")

    def test_google_start_reports_missing_env_with_fix_hint(self):
        self.set_env(GOOGLE_CLIENT_ID=None, GOOGLE_CLIENT_SECRET=None, REDIRECT_URI=None)

        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.StockRequestHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(httpd.shutdown)
        host, port = httpd.server_address

        conn = http.client.HTTPConnection(host, port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/api/auth/google/start")
        response = conn.getresponse()

        self.assertEqual(response.status, 503)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertIn("GOOGLE_CLIENT_ID", payload["error"])
        self.assertIn(".env.example", payload["fix"])

    def test_google_callback_exchanges_code_creates_session_and_returns_user_info(self):
        self.set_env(
            GOOGLE_CLIENT_ID="client-123.apps.googleusercontent.com",
            GOOGLE_CLIENT_SECRET="secret-123",
            REDIRECT_URI="http://localhost:8000/api/auth/google/callback",
        )

        original_exchange = server.exchange_google_code
        original_profile = server.fetch_google_userinfo

        def fake_exchange(code, redirect_uri):
            self.assertEqual(code, "auth-code-123")
            self.assertEqual(redirect_uri, "http://localhost:8000/api/auth/google/callback")
            return {"access_token": "access-token-123"}

        def fake_profile(access_token):
            self.assertEqual(access_token, "access-token-123")
            return {
                "sub": "google-sub-789",
                "email": "oauth-user@example.com",
                "email_verified": True,
                "name": "OAuth User",
                "picture": "https://example.com/picture.png",
            }

        server.exchange_google_code = fake_exchange
        server.fetch_google_userinfo = fake_profile
        self.addCleanup(lambda: setattr(server, "exchange_google_code", original_exchange))
        self.addCleanup(lambda: setattr(server, "fetch_google_userinfo", original_profile))

        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.StockRequestHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(httpd.shutdown)
        host, port = httpd.server_address

        conn = http.client.HTTPConnection(host, port, timeout=5)
        self.addCleanup(conn.close)
        conn.request(
            "GET",
            "/api/auth/google/callback?code=auth-code-123&return=json",
            headers={"Cookie": "oauth_state=test-state"},
        )
        response = conn.getresponse()

        self.assertEqual(response.status, 200)
        self.assertIn("stock_journal_session=", response.getheader("Set-Cookie"))
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["user"]["email"], "oauth-user@example.com")
        self.assertEqual(payload["user"]["name"], "OAuth User")


if __name__ == "__main__":
    unittest.main()
