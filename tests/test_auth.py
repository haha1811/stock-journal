import http.client
import json
import os
import ssl
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
        self.assertFalse(server.requires_authentication("/"))
        self.assertFalse(server.requires_authentication("/index.html"))

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
        self.assertIn('href="#"', login_html)
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

    def test_firebase_auth_helper_requests_are_proxied_before_app_routes(self):
        calls = []
        sentinel = object()
        original_proxy = getattr(server, "proxy_firebase_auth_helper", sentinel)

        def fake_proxy(handler, parsed):
            calls.append((handler.command, parsed.path, parsed.query))
            handler.send_response(200)
            handler.send_header("Content-Type", "text/plain")
            handler.send_header("Content-Length", str(len("firebase-helper")))
            handler.end_headers()
            handler.wfile.write(b"firebase-helper")

        server.proxy_firebase_auth_helper = fake_proxy

        def restore_proxy():
            if original_proxy is sentinel:
                delattr(server, "proxy_firebase_auth_helper")
            else:
                server.proxy_firebase_auth_helper = original_proxy

        self.addCleanup(restore_proxy)

        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.StockRequestHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(httpd.shutdown)
        host, port = httpd.server_address

        conn = http.client.HTTPConnection(host, port, timeout=5)
        self.addCleanup(conn.close)

        conn.request("GET", "/__/auth/handler?apiKey=test")
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.read(), b"firebase-helper")

        conn.request(
            "POST",
            "/__/auth/handler",
            body="state=abc",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.read(), b"firebase-helper")

        self.assertEqual(
            calls,
            [
                ("GET", "/__/auth/handler", "apiKey=test"),
                ("POST", "/__/auth/handler", ""),
            ],
        )

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

    def test_bearer_token_auth_is_accepted_for_protected_api(self):
        original_verify_firebase = server.verify_firebase_id_token
        server.verify_firebase_id_token = lambda token: {
            "uid": "firebase-user-1",
            "email": "firebase-user@example.com",
            "email_verified": True,
            "name": "Firebase User",
            "picture": "https://example.com/avatar.png",
        } if token == "valid-firebase-token" else None
        self.addCleanup(lambda: setattr(server, "verify_firebase_id_token", original_verify_firebase))

        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.StockRequestHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(httpd.shutdown)
        host, port = httpd.server_address

        conn = http.client.HTTPConnection(host, port, timeout=5)
        self.addCleanup(conn.close)

        conn.request("GET", "/api/trades")
        response = conn.getresponse()
        self.assertEqual(response.status, 401)
        response.read()

        conn.request("GET", "/api/trades", headers={"Authorization": "Bearer valid-firebase-token"})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertIn("items", payload)

    def test_accounts_and_trades_are_isolated_by_firebase_uid(self):
        claims = {
            "token-a": {"uid": "uid-A", "email": "a@example.com", "email_verified": True, "name": "A", "picture": ""},
            "token-b": {"uid": "uid-B", "email": "b@example.com", "email_verified": True, "name": "B", "picture": ""},
        }
        original_verify_firebase = server.verify_firebase_id_token
        server.verify_firebase_id_token = lambda token: claims.get(token)
        self.addCleanup(lambda: setattr(server, "verify_firebase_id_token", original_verify_firebase))

        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.StockRequestHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(httpd.shutdown)
        host, port = httpd.server_address

        conn = http.client.HTTPConnection(host, port, timeout=5)
        self.addCleanup(conn.close)

        conn.request("GET", "/api/accounts", headers={"Authorization": "Bearer token-a"})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        default_accounts = json.loads(response.read().decode("utf-8"))["items"]
        self.assertTrue(any(x["name"] == "主帳戶" for x in default_accounts))

        conn.request("POST", "/api/accounts", body=json.dumps({"name": "A帳戶"}), headers={"Authorization": "Bearer token-a", "Content-Type": "application/json"})
        response = conn.getresponse()
        self.assertEqual(response.status, 201)
        response.read()

        trade = {
            "settlement": "Y", "side": "買入", "date": "2026-04-30", "symbol": "0050", "name": "元大台灣50",
            "quantity": 1, "price": 100, "fee": 0, "tax": 0, "note": "A only", "account": "A帳戶"
        }
        conn.request("POST", "/api/trades", body=json.dumps(trade), headers={"Authorization": "Bearer token-a", "Content-Type": "application/json"})
        response = conn.getresponse()
        self.assertEqual(response.status, 201)
        response.read()

        conn.request("GET", "/api/accounts", headers={"Authorization": "Bearer token-a"})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        a_accounts = json.loads(response.read().decode("utf-8"))["items"]
        self.assertTrue(any(x["name"] == "A帳戶" for x in a_accounts))

        conn.request("GET", "/api/accounts", headers={"Authorization": "Bearer token-b"})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        b_accounts = json.loads(response.read().decode("utf-8"))["items"]
        self.assertTrue(any(x["name"] == "主帳戶" for x in b_accounts))
        self.assertFalse(any(x["name"] == "A帳戶" for x in b_accounts))

        conn.request("GET", "/api/trades", headers={"Authorization": "Bearer token-a"})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(len(json.loads(response.read().decode("utf-8"))["items"]), 1)

        conn.request("GET", "/api/trades", headers={"Authorization": "Bearer token-b"})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(len(json.loads(response.read().decode("utf-8"))["items"]), 0)

    def test_refresh_quotes_updates_symbols_across_all_user_inventories(self):
        now = server.current_iso_now()
        with server.get_connection() as connection:
            connection.executemany(
                """
                INSERT INTO trades (
                    id, owner_uid, account, settlement, side, date, year, symbol, name,
                    quantity, price, amount, fee, tax, note, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "trade-uid-a-0050",
                        "uid-A",
                        "主帳戶",
                        "Y",
                        "買入",
                        "2026-04-30",
                        "2026",
                        "0050",
                        "ETF 50",
                        10,
                        100,
                        1000,
                        0,
                        0,
                        "",
                        now,
                        now,
                    ),
                    (
                        "trade-uid-b-2330",
                        "uid-B",
                        "主帳戶",
                        "Y",
                        "買入",
                        "2026-04-30",
                        "2026",
                        "2330",
                        "TSMC",
                        2,
                        800,
                        1600,
                        0,
                        0,
                        "",
                        now,
                        now,
                    ),
                ],
            )
            connection.commit()

        original_fetch = server.fetch_twse_daily_prices
        server.fetch_twse_daily_prices = lambda _query_date: {
            "0050": {"symbol": "0050", "name": "ETF 50", "price": 120.5},
            "2330": {"symbol": "2330", "name": "TSMC", "price": 900.0},
        }
        self.addCleanup(lambda: setattr(server, "fetch_twse_daily_prices", original_fetch))

        result = server.refresh_quotes(force=True)

        self.assertEqual(result["updated_count"], 2)
        uid_a_inventory = server.list_inventory("ALL", "uid-A")["items"]
        uid_b_inventory = server.list_inventory("ALL", "uid-B")["items"]
        self.assertEqual(uid_a_inventory[0]["latest_price"], 120.5)
        self.assertEqual(uid_b_inventory[0]["latest_price"], 900.0)

    def test_refresh_dividends_migrates_legacy_dividend_events_without_source(self):
        server.DB_PATH = Path(self.temp_dir.name) / "legacy-dividend-events.sqlite3"
        server.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with server.sqlite3.connect(server.DB_PATH) as connection:
            connection.execute(
                """
                CREATE TABLE dividend_events (
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    ex_dividend_date TEXT NOT NULL,
                    payment_date TEXT NOT NULL,
                    cash_dividend_per_unit REAL NOT NULL,
                    PRIMARY KEY (symbol, ex_dividend_date, payment_date)
                )
                """
            )
            connection.commit()

        server.ensure_database()

        original_fetch = server.fetch_twse_dividend_list
        server.fetch_twse_dividend_list = lambda: [
            {
                "symbol": "0050",
                "name": "ETF 50",
                "ex_dividend_date": "2026-07-21",
                "payment_date": "2026-08-15",
                "cash_dividend_per_unit": 1.25,
                "source": "TWSE ETF dividend list",
            }
        ]
        self.addCleanup(lambda: setattr(server, "fetch_twse_dividend_list", original_fetch))

        result = server.refresh_dividend_events(force=True)

        self.assertEqual(result["updated_count"], 1)
        with server.get_connection() as connection:
            row = connection.execute(
                "SELECT source, updated_at FROM dividend_events WHERE symbol = '0050'"
            ).fetchone()
        self.assertEqual(row["source"], "TWSE ETF dividend list")
        self.assertTrue(row["updated_at"])

    def test_twse_ssl_context_keeps_verification_without_python_313_strict_mode(self):
        context = server.create_twse_ssl_context()

        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            self.assertFalse(context.verify_flags & ssl.VERIFY_X509_STRICT)


if __name__ == "__main__":
    unittest.main()
