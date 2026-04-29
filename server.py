import hashlib
import json
import mimetypes
import os
import secrets
import sqlite3
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    from firebase_admin import credentials as firebase_credentials
except ImportError:
    firebase_admin = None
    firebase_auth = None
    firebase_credentials = None


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "stock-records.sqlite3"
HOST = "127.0.0.1"
PORT = 8000
TAIPEI_TZ = ZoneInfo("Asia/Taipei") if ZoneInfo else timezone(timedelta(hours=8), name="Asia/Taipei")
PRICE_REFRESH_HOUR = 15
DIVIDEND_REFRESH_HOUR = 6
SESSION_COOKIE_NAME = "stock_journal_session"
SESSION_DAYS = 14
PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/config",
    "/api/auth/google/start",
    "/api/auth/google/callback",
    "/api/auth/google",
    "/api/auth/logout",
    "/login.html",
    "/auth.js",
    "/firebase-auth-bridge.js",
    "/styles.css",
    "/favicon.ico",
}
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/login.html": "login.html",

    "/inventory.html": "inventory.html",
    "/dividends.html": "dividends.html",
    "/dividend-stats.html": "dividend-stats.html",
    "/dividend-calendar.html": "dividend-calendar.html",
    "/favicon.ico": "favicon.ico",
    "/app.js": "app.js",
    "/auth.js": "auth.js",
    "/firebase-auth-bridge.js": "firebase-auth-bridge.js",

    "/dividend-calendar.js": "dividend-calendar.js",
    "/dividend-stats.js": "dividend-stats.js",
    "/dividends.js": "dividends.js",
    "/inventory.js": "inventory.js",
    "/styles.css": "styles.css",
}


def load_dotenv(path=BASE_DIR / ".env"):
    """Load simple KEY=value pairs from .env without overriding real env vars."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


load_dotenv()


def get_env_host():
    return os.getenv("STOCK_APP_HOST", HOST).strip() or HOST


def get_env_port():
    raw = os.getenv("STOCK_APP_PORT", str(PORT)).strip()
    try:
        port = int(raw)
    except ValueError as error:
        raise ValueError("STOCK_APP_PORT 必須是整數") from error
    if port <= 0 or port > 65535:
        raise ValueError("STOCK_APP_PORT 必須介於 1 到 65535")
    return port


def get_google_client_id():
    return os.getenv("GOOGLE_CLIENT_ID", os.getenv("STOCK_GOOGLE_CLIENT_ID", "")).strip()


def get_google_client_secret():
    return os.getenv("GOOGLE_CLIENT_SECRET", "").strip()


def get_redirect_uri():
    return os.getenv("REDIRECT_URI", "").strip()


def get_firebase_api_key():
    return os.getenv("FIREBASE_API_KEY", "").strip()


def get_firebase_auth_domain():
    return os.getenv("FIREBASE_AUTH_DOMAIN", "").strip()


def get_firebase_project_id():
    return os.getenv("FIREBASE_PROJECT_ID", "").strip()


def get_firebase_app_id():
    return os.getenv("FIREBASE_APP_ID", "").strip()


def get_firebase_storage_bucket():
    return os.getenv("FIREBASE_STORAGE_BUCKET", "").strip()


def get_firebase_messaging_sender_id():
    return os.getenv("FIREBASE_MESSAGING_SENDER_ID", "").strip()


def get_firebase_service_account_path():
    return os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()


def google_oauth_env_error():
    missing = []
    if not get_google_client_id():
        missing.append("GOOGLE_CLIENT_ID")
    if not get_google_client_secret():
        missing.append("GOOGLE_CLIENT_SECRET")
    if not get_redirect_uri():
        missing.append("REDIRECT_URI")
    if not missing:
        return None
    return {
        "error": "Google OAuth 環境變數未設定完整：" + ", ".join(missing),
        "fix": "請依 .env.example 設定 GOOGLE_CLIENT_ID、GOOGLE_CLIENT_SECRET、REDIRECT_URI；GCP Authorized redirect URI 必須和 REDIRECT_URI 完全一致，例如 http://localhost:8000/api/auth/google/callback。",
        "missing": missing,
    }


def get_allowed_google_emails():
    raw = os.getenv("STOCK_ALLOWED_GOOGLE_EMAILS", "").strip()
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def get_allowed_google_domain():
    return os.getenv("STOCK_ALLOWED_GOOGLE_DOMAIN", "").strip().lower()


def is_cookie_secure():
    return os.getenv("STOCK_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "y"}


def requires_authentication(path):
    # Phase A Firebase 相容：僅保護 API 路徑；一般頁面先允許載入，交由前端 bridge 做 token guard。
    return path.startswith("/api/") and path not in PUBLIC_PATHS


def normalize_email(value):
    return str(value or "").strip().lower()


def hash_session_id(session_id):
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def fetch_google_tokeninfo(credential):
    url = "https://oauth2.googleapis.com/tokeninfo?id_token=" + urllib.parse.quote(credential)
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def exchange_google_code(code, redirect_uri=None):
    env_error = google_oauth_env_error()
    if env_error:
        raise ValueError(env_error["error"] + "；" + env_error["fix"])

    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": get_google_client_id(),
            "client_secret": get_google_client_secret(),
            "redirect_uri": redirect_uri or get_redirect_uri(),
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="ignore")
        raise ValueError("Google OAuth code 換 token 失敗，請確認 REDIRECT_URI 與 GCP 設定完全一致。" + detail) from error
    except urllib.error.URLError as error:
        raise ValueError("無法連線到 Google OAuth token endpoint，請稍後再試。") from error


def fetch_google_userinfo(access_token):
    if not access_token:
        raise ValueError("Google OAuth token response 缺少 access_token")
    request = urllib.request.Request(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="ignore")
        raise ValueError("無法取得 Google 使用者資訊。" + detail) from error
    except urllib.error.URLError as error:
        raise ValueError("無法連線到 Google userinfo endpoint，請稍後再試。") from error


def validate_google_profile(payload):
    if str(payload.get("email_verified", "")).lower() not in {"true", "1"}:
        raise ValueError("Google 帳號尚未完成 email 驗證")
    email = normalize_email(payload.get("email"))
    if not email:
        raise ValueError("Google 使用者資訊缺少 email")
    google_sub = str(payload.get("sub", "")).strip()
    if not google_sub:
        raise ValueError("Google 使用者資訊缺少 sub")

    allowed_emails = get_allowed_google_emails()
    allowed_domain = get_allowed_google_domain()
    if allowed_emails and email not in allowed_emails:
        raise ValueError("此 Google 帳號未被授權使用")
    if allowed_domain and not email.endswith("@" + allowed_domain):
        raise ValueError("此 Google 帳號網域未被授權使用")

    return {
        "sub": google_sub,
        "email": email,
        "email_verified": True,
        "name": str(payload.get("name") or email),
        "picture": str(payload.get("picture") or ""),
    }


def verify_google_identity(credential, client_id=None, tokeninfo_fetcher=fetch_google_tokeninfo):
    client_id = (client_id or get_google_client_id()).strip()
    if not client_id:
        raise ValueError("尚未設定 GOOGLE_CLIENT_ID 或 STOCK_GOOGLE_CLIENT_ID")
    if not credential:
        raise ValueError("缺少 Google 登入憑證")

    try:
        payload = tokeninfo_fetcher(credential)
    except urllib.error.URLError as error:
        raise ValueError("無法驗證 Google 登入憑證") from error

    if payload.get("aud") != client_id:
        raise ValueError("Google 登入憑證的 client_id 不符")
    if str(payload.get("email_verified", "")).lower() not in {"true", "1"}:
        raise ValueError("Google 帳號尚未完成 email 驗證")

    email = normalize_email(payload.get("email"))
    if not email:
        raise ValueError("Google 登入憑證缺少 email")

    allowed_emails = get_allowed_google_emails()
    allowed_domain = get_allowed_google_domain()
    if allowed_emails and email not in allowed_emails:
        raise ValueError("此 Google 帳號未被授權使用")
    if allowed_domain and not email.endswith("@" + allowed_domain):
        raise ValueError("此 Google 帳號網域未被授權使用")

    return {
        "sub": str(payload.get("sub", "")).strip(),
        "email": email,
        "email_verified": True,
        "name": str(payload.get("name") or email),
        "picture": str(payload.get("picture") or ""),
    }


def create_authenticated_session(profile):
    email = normalize_email(profile.get("email"))
    google_sub = str(profile.get("sub", "")).strip()
    if not email or not google_sub:
        raise ValueError("Google 使用者資訊不完整")

    now = datetime.now(TAIPEI_TZ)
    now_text = now.isoformat(timespec="seconds")
    expires_at = now + timedelta(days=SESSION_DAYS)
    session_id = secrets.token_urlsafe(32)
    session_hash = hash_session_id(session_id)

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO auth_users (email, google_sub, name, picture, created_at, updated_at, last_login_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                google_sub = excluded.google_sub,
                name = excluded.name,
                picture = excluded.picture,
                updated_at = excluded.updated_at,
                last_login_at = excluded.last_login_at
            """,
            (
                email,
                google_sub,
                str(profile.get("name") or email),
                str(profile.get("picture") or ""),
                now_text,
                now_text,
                now_text,
            ),
        )
        connection.execute(
            "INSERT INTO auth_sessions (id_hash, email, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (session_hash, email, now_text, expires_at.isoformat(timespec="seconds")),
        )
        connection.commit()

    cookie = SimpleCookie()
    cookie[SESSION_COOKIE_NAME] = session_id
    cookie[SESSION_COOKIE_NAME]["path"] = "/"
    cookie[SESSION_COOKIE_NAME]["httponly"] = True
    cookie[SESSION_COOKIE_NAME]["samesite"] = "Lax"
    cookie[SESSION_COOKIE_NAME]["max-age"] = str(SESSION_DAYS * 24 * 60 * 60)
    if is_cookie_secure():
        cookie[SESSION_COOKIE_NAME]["secure"] = True

    return {
        "email": email,
        "name": str(profile.get("name") or email),
        "picture": str(profile.get("picture") or ""),
        "Set-Cookie": cookie.output(header="").strip(),
    }


def get_authenticated_user_from_cookie(cookie_header):
    if not cookie_header:
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:
        return None
    if SESSION_COOKIE_NAME not in cookie:
        return None

    session_id = cookie[SESSION_COOKIE_NAME].value
    session_hash = hash_session_id(session_id)
    now_text = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT auth_users.email, auth_users.name, auth_users.picture
            FROM auth_sessions
            JOIN auth_users ON auth_users.email = auth_sessions.email
            WHERE auth_sessions.id_hash = ? AND auth_sessions.expires_at > ?
            """,
            (session_hash, now_text),
        ).fetchone()
    return dict(row) if row else None


def delete_authenticated_session(cookie_header):
    user = get_authenticated_user_from_cookie(cookie_header)
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header or "")
    except Exception:
        return user
    if SESSION_COOKIE_NAME in cookie:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM auth_sessions WHERE id_hash = ?",
                (hash_session_id(cookie[SESSION_COOKIE_NAME].value),),
            )
            connection.commit()
    return user


def expired_session_cookie():
    cookie = SimpleCookie()
    cookie[SESSION_COOKIE_NAME] = ""
    cookie[SESSION_COOKIE_NAME]["path"] = "/"
    cookie[SESSION_COOKIE_NAME]["max-age"] = "0"
    cookie[SESSION_COOKIE_NAME]["httponly"] = True
    cookie[SESSION_COOKIE_NAME]["samesite"] = "Lax"
    if is_cookie_secure():
        cookie[SESSION_COOKIE_NAME]["secure"] = True
    return cookie.output(header="").strip()


FIREBASE_APP = None
FIREBASE_APP_LOCK = threading.Lock()


def get_public_auth_config():
    return {
        "google_client_id": get_google_client_id(),
        "login_required": True,
        "firebase": {
            "apiKey": get_firebase_api_key(),
            "authDomain": get_firebase_auth_domain(),
            "projectId": get_firebase_project_id(),
            "appId": get_firebase_app_id(),
            "storageBucket": get_firebase_storage_bucket(),
            "messagingSenderId": get_firebase_messaging_sender_id(),
        },
    }


def get_bearer_token_from_auth_header(auth_header):
    if not auth_header:
        return ""
    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        return ""
    return auth_header[len(prefix):].strip()


def ensure_firebase_admin_app():
    if firebase_admin is None or firebase_auth is None:
        raise ValueError("伺服器尚未安裝 firebase-admin，請先安裝後再啟用 Firebase Auth")

    global FIREBASE_APP
    if FIREBASE_APP is not None:
        return FIREBASE_APP

    with FIREBASE_APP_LOCK:
        if FIREBASE_APP is not None:
            return FIREBASE_APP

        service_account_path = get_firebase_service_account_path()
        if service_account_path:
            cred = firebase_credentials.Certificate(service_account_path)
            FIREBASE_APP = firebase_admin.initialize_app(cred)
        else:
            FIREBASE_APP = firebase_admin.initialize_app()

    return FIREBASE_APP


def verify_firebase_id_token(id_token):
    if not id_token:
        return None
    ensure_firebase_admin_app()
    try:
        return firebase_auth.verify_id_token(id_token)
    except Exception:
        return None


def upsert_auth_user_from_firebase_claims(claims):
    uid = str(claims.get("uid") or "").strip()
    email = normalize_email(claims.get("email"))
    if not uid or not email:
        raise ValueError("Firebase ID Token 缺少 uid 或 email")
    if not claims.get("email_verified", False):
        raise ValueError("Firebase 帳號 email 尚未驗證")

    allowed_emails = get_allowed_google_emails()
    allowed_domain = get_allowed_google_domain()
    if allowed_emails and email not in allowed_emails:
        raise ValueError("此 Google 帳號未被授權使用")
    if allowed_domain and not email.endswith("@" + allowed_domain):
        raise ValueError("此 Google 帳號網域未被授權使用")

    now_text = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")
    name = str(claims.get("name") or email)
    picture = str(claims.get("picture") or "")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO auth_users (email, google_sub, name, picture, created_at, updated_at, last_login_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                google_sub = excluded.google_sub,
                name = excluded.name,
                picture = excluded.picture,
                updated_at = excluded.updated_at,
                last_login_at = excluded.last_login_at
            """,
            (email, uid, name, picture, now_text, now_text, now_text),
        )
        connection.commit()

    return {"email": email, "name": name, "picture": picture, "uid": uid}


def get_authenticated_user_from_bearer(auth_header):
    id_token = get_bearer_token_from_auth_header(auth_header)
    if not id_token:
        return None
    try:
        claims = verify_firebase_id_token(id_token)
    except Exception:
        return None
    if not claims:
        return None
    try:
        return upsert_auth_user_from_firebase_claims(claims)
    except ValueError:
        return None


def build_google_auth_url():
    env_error = google_oauth_env_error()
    if env_error:
        raise ValueError(env_error["error"] + "；" + env_error["fix"])

    state = secrets.token_urlsafe(24)
    params = urllib.parse.urlencode(
        {
            "client_id": get_google_client_id(),
            "redirect_uri": get_redirect_uri(),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{params}", state


def oauth_state_cookie(state):
    cookie = SimpleCookie()
    cookie["oauth_state"] = state
    cookie["oauth_state"]["path"] = "/"
    cookie["oauth_state"]["httponly"] = True
    cookie["oauth_state"]["samesite"] = "Lax"
    cookie["oauth_state"]["max-age"] = "600"
    if is_cookie_secure():
        cookie["oauth_state"]["secure"] = True
    return cookie.output(header="").strip()


def expired_oauth_state_cookie():
    cookie = SimpleCookie()
    cookie["oauth_state"] = ""
    cookie["oauth_state"]["path"] = "/"
    cookie["oauth_state"]["max-age"] = "0"
    cookie["oauth_state"]["httponly"] = True
    cookie["oauth_state"]["samesite"] = "Lax"
    if is_cookie_secure():
        cookie["oauth_state"]["secure"] = True
    return cookie.output(header="").strip()


def get_oauth_state_from_cookie(cookie_header):
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header or "")
    except Exception:
        return ""
    return cookie["oauth_state"].value if "oauth_state" in cookie else ""


def strip_prefix(value, prefix):
    return value[len(prefix):] if value.startswith(prefix) else value


def ensure_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_users (
                email TEXT PRIMARY KEY,
                google_sub TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL DEFAULT '',
                picture TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                id_hash TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(email) REFERENCES auth_users(email) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                account TEXT NOT NULL DEFAULT '主帳戶',
                settlement TEXT NOT NULL,
                side TEXT NOT NULL,
                date TEXT NOT NULL,
                year TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                fee REAL NOT NULL DEFAULT 0,
                tax REAL NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS quotes (
                symbol TEXT PRIMARY KEY,
                price REAL NOT NULL,
                quoted_date TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_targets (
                account TEXT NOT NULL,
                symbol TEXT NOT NULL,
                target_sell_price REAL,
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (account, symbol)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dividend_events (
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                ex_dividend_date TEXT NOT NULL,
                payment_date TEXT NOT NULL,
                cash_dividend_per_unit REAL NOT NULL,
                source TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (symbol, ex_dividend_date, payment_date)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dividend_adjustments (
                account TEXT NOT NULL,
                symbol TEXT NOT NULL,
                ex_dividend_date TEXT NOT NULL,
                payment_date TEXT NOT NULL,
                bank_fee REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (account, symbol, ex_dividend_date, payment_date)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dividend_manual_events (
                id TEXT PRIMARY KEY,
                account TEXT NOT NULL DEFAULT '主帳戶',
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                ex_dividend_date TEXT NOT NULL,
                payment_date TEXT NOT NULL,
                eligible_units INTEGER,
                cash_dividend_per_unit REAL NOT NULL,
                avg_price REAL,
                yield_rate REAL,
                updated_at TEXT NOT NULL
            )
            """
        )

        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(trades)").fetchall()
        }
        if "account" not in columns:
            connection.execute(
                "ALTER TABLE trades ADD COLUMN account TEXT NOT NULL DEFAULT '主帳戶'"
            )
            connection.execute(
                "UPDATE trades SET account = '主帳戶' WHERE account IS NULL OR account = ''"
            )

        manual_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(dividend_manual_events)").fetchall()
        }
        if "account" not in manual_columns:
            connection.execute(
                "ALTER TABLE dividend_manual_events ADD COLUMN account TEXT NOT NULL DEFAULT '主帳戶'"
            )
            connection.execute(
                """
                UPDATE dividend_manual_events
                SET account = '主帳戶'
                WHERE account IS NULL OR TRIM(account) = ''
                """
            )
        if "avg_price" not in manual_columns:
            connection.execute("ALTER TABLE dividend_manual_events ADD COLUMN avg_price REAL")
        if "yield_rate" not in manual_columns:
            connection.execute("ALTER TABLE dividend_manual_events ADD COLUMN yield_rate REAL")
        if "eligible_units" not in manual_columns:
            connection.execute("ALTER TABLE dividend_manual_events ADD COLUMN eligible_units INTEGER")

        ensure_default_account(connection)
        sync_accounts_from_trades(connection)
        connection.commit()


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=MEMORY")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def calculate_tax(side, amount):
    return round(amount * 0.003) if side == "賣出" else 0


def ensure_default_account(connection):
    now = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")
    connection.execute(
        """
        INSERT INTO accounts (id, name, created_at, updated_at)
        SELECT ?, ?, ?, ?
        WHERE NOT EXISTS (
            SELECT 1 FROM accounts WHERE name = ?
        )
        """,
        ("default-account", "主帳戶", now, now, "主帳戶"),
    )


def sync_accounts_from_trades(connection):
    now = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")
    rows = connection.execute(
        """
        SELECT DISTINCT account
        FROM trades
        WHERE account IS NOT NULL AND TRIM(account) <> ''
        """
    ).fetchall()

    for row in rows:
        name = row["account"].strip()
        connection.execute(
            """
            INSERT INTO accounts (id, name, created_at, updated_at)
            SELECT ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM accounts WHERE name = ?
            )
            """,
            (create_trade_id(), name, now, now, name),
        )


def normalize_trade_payload(payload, existing_id=None):
    required_fields = [
        "settlement",
        "side",
        "date",
        "symbol",
        "name",
        "quantity",
        "price",
        "fee",
        "tax",
        "note",
    ]

    for field in required_fields:
        if field not in payload:
            raise ValueError(f"缺少欄位: {field}")

    trade_date = str(payload["date"]).strip()
    if not trade_date:
        raise ValueError("日期不可為空")

    try:
        datetime.strptime(trade_date, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError("日期格式必須為 YYYY-MM-DD") from error

    side = str(payload["side"]).strip()
    if side not in {"買入", "賣出"}:
        raise ValueError("買賣欄位只接受 買入 或 賣出")

    settlement = str(payload["settlement"]).strip()
    if settlement not in {"Y", "N"}:
        raise ValueError("T+2 欄位只接受 Y 或 N")

    account = str(payload.get("account", "")).strip() or "主帳戶"
    symbol = str(payload["symbol"]).strip()
    name = str(payload["name"]).strip()
    quantity = int(payload["quantity"])
    price = round(float(payload["price"]), 2)
    fee = round(float(payload["fee"]), 2)
    entered_tax = round(float(payload["tax"]), 2)

    if not symbol or not name:
        raise ValueError("股號與股名不可為空")
    if quantity <= 0:
        raise ValueError("數量需大於 0")
    if price < 0 or fee < 0 or entered_tax < 0:
        raise ValueError("價格、手續費、交易稅不可小於 0")

    amount = round(quantity * price, 2)
    year = trade_date[:4]

    return {
        "id": existing_id or str(payload.get("id") or "").strip() or create_trade_id(),
        "account": account,
        "settlement": settlement,
        "side": side,
        "date": trade_date,
        "year": year,
        "symbol": symbol,
        "name": name,
        "quantity": quantity,
        "price": price,
        "amount": amount,
        "fee": fee,
        "tax": entered_tax if entered_tax > 0 else calculate_tax(side, amount),
        "note": str(payload["note"]).strip(),
    }


def create_trade_id():
    return datetime.now(TAIPEI_TZ).strftime("%Y%m%d%H%M%S%f")


def list_accounts():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name
            FROM accounts
            ORDER BY CASE WHEN name = '主帳戶' THEN 0 ELSE 1 END, name ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def ensure_account_exists(account_name):
    normalized_name = str(account_name).strip() or "主帳戶"

    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, name FROM accounts WHERE name = ?",
            (normalized_name,),
        ).fetchone()
        if row:
            return dict(row)

        now = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")
        account = {"id": create_trade_id(), "name": normalized_name}
        connection.execute(
            """
            INSERT INTO accounts (id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (account["id"], account["name"], now, now),
        )
        connection.commit()
        return account


def create_account(payload):
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("帳戶名稱不可為空")
    return ensure_account_exists(name)


def update_account(account_id, payload):
    new_name = str(payload.get("name", "")).strip()
    if not new_name:
        raise ValueError("帳戶名稱不可為空")

    now = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id, name FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        if not existing:
            raise LookupError("找不到要更新的帳戶")

        duplicate = connection.execute(
            "SELECT id FROM accounts WHERE name = ? AND id <> ?",
            (new_name, account_id),
        ).fetchone()
        if duplicate:
            raise ValueError("帳戶名稱已存在")

        old_name = existing["name"]
        connection.execute(
            "UPDATE accounts SET name = ?, updated_at = ? WHERE id = ?",
            (new_name, now, account_id),
        )
        connection.execute(
            "UPDATE trades SET account = ?, updated_at = ? WHERE account = ?",
            (new_name, now, old_name),
        )
        connection.execute(
            """
            INSERT INTO holding_targets (account, symbol, target_sell_price, note, updated_at)
            SELECT ?, symbol, target_sell_price, note, ?
            FROM holding_targets
            WHERE account = ?
            ON CONFLICT(account, symbol) DO UPDATE SET
                target_sell_price = excluded.target_sell_price,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (new_name, now, old_name),
        )
        connection.execute("DELETE FROM holding_targets WHERE account = ?", (old_name,))
        connection.commit()

    return {"id": account_id, "name": new_name}


def delete_account(account_id):
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id, name FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        if not existing:
            raise LookupError("找不到要刪除的帳戶")

        if existing["name"] == "主帳戶":
            raise ValueError("主帳戶不可刪除")

        usage = connection.execute(
            "SELECT COUNT(*) AS count FROM trades WHERE account = ?",
            (existing["name"],),
        ).fetchone()
        if usage["count"] > 0:
            raise ValueError("此帳戶仍有交易資料，請先移轉或刪除相關交易")

        connection.execute(
            "DELETE FROM holding_targets WHERE account = ?",
            (existing["name"],),
        )
        connection.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        connection.commit()


def list_trades():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, account, settlement, side, date, year, symbol, name, quantity, price, amount, fee, tax, note
            FROM trades
            ORDER BY date DESC, created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def create_trade(payload):
    trade = normalize_trade_payload(payload)
    ensure_account_exists(trade["account"])
    now = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO trades (
                id, account, settlement, side, date, year, symbol, name, quantity, price, amount, fee, tax, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade["id"],
                trade["account"],
                trade["settlement"],
                trade["side"],
                trade["date"],
                trade["year"],
                trade["symbol"],
                trade["name"],
                trade["quantity"],
                trade["price"],
                trade["amount"],
                trade["fee"],
                trade["tax"],
                trade["note"],
                now,
                now,
            ),
        )
        connection.commit()

    return trade


def update_trade(trade_id, payload):
    trade = normalize_trade_payload(payload, existing_id=trade_id)
    ensure_account_exists(trade["account"])
    now = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE trades
            SET account = ?, settlement = ?, side = ?, date = ?, year = ?, symbol = ?, name = ?, quantity = ?, price = ?, amount = ?, fee = ?, tax = ?, note = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                trade["account"],
                trade["settlement"],
                trade["side"],
                trade["date"],
                trade["year"],
                trade["symbol"],
                trade["name"],
                trade["quantity"],
                trade["price"],
                trade["amount"],
                trade["fee"],
                trade["tax"],
                trade["note"],
                now,
                trade_id,
            ),
        )
        connection.commit()

    if cursor.rowcount == 0:
        raise LookupError("找不到要更新的交易")

    return trade


def delete_trade(trade_id):
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
        connection.commit()

    if cursor.rowcount == 0:
        raise LookupError("找不到要刪除的交易")


def replace_trades(items):
    if not isinstance(items, list):
        raise ValueError("匯入資料必須為陣列")

    normalized = [normalize_trade_payload(item) for item in items]
    now = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")

    with get_connection() as connection:
        ensure_default_account(connection)
        connection.execute("DELETE FROM trades")
        connection.executemany(
            """
            INSERT INTO trades (
                id, account, settlement, side, date, year, symbol, name, quantity, price, amount, fee, tax, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    trade["id"],
                    trade["account"],
                    trade["settlement"],
                    trade["side"],
                    trade["date"],
                    trade["year"],
                    trade["symbol"],
                    trade["name"],
                    trade["quantity"],
                    trade["price"],
                    trade["amount"],
                    trade["fee"],
                    trade["tax"],
                    trade["note"],
                    now,
                    now,
                )
                for trade in normalized
            ],
        )
        sync_accounts_from_trades(connection)
        connection.commit()

    return normalized


def get_quote_map(connection):
    rows = connection.execute(
        "SELECT symbol, price, quoted_date, updated_at, source FROM quotes"
    ).fetchall()
    return {row["symbol"]: dict(row) for row in rows}


def get_target_map(connection):
    rows = connection.execute(
        "SELECT account, symbol, target_sell_price, note, updated_at FROM holding_targets"
    ).fetchall()
    return {(row["account"], row["symbol"]): dict(row) for row in rows}


def compute_inventory_items():
    with get_connection() as connection:
        trades = connection.execute(
            """
            SELECT account, symbol, name, side, quantity, amount, fee, tax, date, created_at
            FROM trades
            ORDER BY date ASC, created_at ASC
            """
        ).fetchall()
        quote_map = get_quote_map(connection)
        target_map = get_target_map(connection)

    positions = {}
    for trade in trades:
        key = (trade["account"], trade["symbol"])
        position = positions.setdefault(
            key,
            {
                "account": trade["account"],
                "symbol": trade["symbol"],
                "name": trade["name"],
                "quantity": 0,
                "cost_basis": 0.0,
                "last_trade_date": trade["date"],
            },
        )
        position["name"] = trade["name"]
        position["last_trade_date"] = trade["date"]

        if trade["side"] == "買入":
            position["quantity"] += trade["quantity"]
            position["cost_basis"] += trade["amount"] + trade["fee"] + trade["tax"]
            continue

        sell_qty = trade["quantity"]
        if position["quantity"] <= 0:
            position["quantity"] = 0
            position["cost_basis"] = 0.0
            continue

        avg_cost = position["cost_basis"] / position["quantity"] if position["quantity"] else 0
        reduction_qty = min(sell_qty, position["quantity"])
        position["quantity"] -= reduction_qty
        position["cost_basis"] -= avg_cost * reduction_qty
        if position["quantity"] <= 0:
            position["quantity"] = 0
            position["cost_basis"] = 0.0

    items = []
    for key, position in positions.items():
        if position["quantity"] <= 0:
            continue

        account, symbol = key
        quote = quote_map.get(symbol)
        target = target_map.get((account, symbol), {})
        quantity = int(position["quantity"])
        inventory_cost = round(position["cost_basis"], 2)
        avg_price = round(inventory_cost / quantity, 2) if quantity else 0
        latest_price = round(float(quote["price"]), 2) if quote else None
        market_value = round(quantity * latest_price, 2) if latest_price is not None else None
        unrealized_profit = (
            round(market_value - inventory_cost, 2) if market_value is not None else None
        )
        unrealized_profit_pct = (
            round((unrealized_profit / inventory_cost) * 100, 2)
            if unrealized_profit is not None and inventory_cost > 0
            else None
        )
        target_price = target.get("target_sell_price")
        target_hit = (
            latest_price is not None
            and target_price is not None
            and latest_price >= float(target_price)
        )

        items.append(
            {
                "account": account,
                "symbol": symbol,
                "name": position["name"],
                "quantity": quantity,
                "avg_price": avg_price,
                "inventory_cost": inventory_cost,
                "latest_price": latest_price,
                "quoted_date": quote["quoted_date"] if quote else None,
                "price_updated_at": quote["updated_at"] if quote else None,
                "price_source": quote["source"] if quote else None,
                "market_value": market_value,
                "unrealized_profit": unrealized_profit,
                "unrealized_profit_pct": unrealized_profit_pct,
                "target_sell_price": round(float(target_price), 2) if target_price is not None else None,
                "target_hit": target_hit,
                "note": target.get("note", ""),
                "last_trade_date": position["last_trade_date"],
            }
        )

    items.sort(key=lambda item: (item["account"], item["symbol"]))
    return items


def list_inventory(account_filter="ALL"):
    items = compute_inventory_items()
    if account_filter and account_filter != "ALL":
        items = [item for item in items if item["account"] == account_filter]

    summary = {
        "inventory_cost": round(sum(item["inventory_cost"] for item in items), 2),
        "market_value": round(
            sum(item["market_value"] or 0 for item in items),
            2,
        ),
        "unrealized_profit": round(
            sum(item["unrealized_profit"] or 0 for item in items),
            2,
        ),
        "ready_to_sell_count": sum(1 for item in items if item["target_hit"]),
    }
    return {"items": items, "summary": summary}


def save_inventory_target(payload):
    account = str(payload.get("account", "")).strip()
    symbol = str(payload.get("symbol", "")).strip()
    if not account or not symbol:
        raise ValueError("account 與 symbol 不可為空")

    ensure_account_exists(account)

    raw_target = payload.get("target_sell_price")
    target_price = None if raw_target in (None, "", "null") else round(float(raw_target), 2)
    if target_price is not None and target_price < 0:
        raise ValueError("可賣價不可小於 0")

    note = str(payload.get("note", "")).strip()
    now = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO holding_targets (account, symbol, target_sell_price, note, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(account, symbol) DO UPDATE SET
                target_sell_price = excluded.target_sell_price,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (account, symbol, target_price, note, now),
        )
        connection.commit()

    return {
        "account": account,
        "symbol": symbol,
        "target_sell_price": target_price,
        "note": note,
        "updated_at": now,
    }


def bulk_apply_target_percentage(payload):
    percentage = float(payload.get("percentage", 0))
    if percentage <= 0:
        raise ValueError("百分比必須大於 0")

    account_filter = str(payload.get("account", "ALL")).strip() or "ALL"
    only_empty_targets = bool(payload.get("only_empty_targets", False))
    inventory_items = list_inventory(account_filter)["items"]
    if not inventory_items:
        return {"updated_count": 0, "percentage": percentage, "only_empty_targets": only_empty_targets}

    now = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")
    updated_count = 0
    with get_connection() as connection:
        for item in inventory_items:
            if only_empty_targets and item.get("target_sell_price") is not None:
                continue
            target_price = round(item["avg_price"] * (percentage / 100), 2)
            connection.execute(
                """
                INSERT INTO holding_targets (account, symbol, target_sell_price, note, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account, symbol) DO UPDATE SET
                    target_sell_price = excluded.target_sell_price,
                    updated_at = excluded.updated_at
                """,
                (
                    item["account"],
                    item["symbol"],
                    target_price,
                    item.get("note", ""),
                    now,
                ),
            )
            updated_count += 1
        connection.commit()

    return {
        "updated_count": updated_count,
        "percentage": percentage,
        "only_empty_targets": only_empty_targets,
    }


class TwseDividendListParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_row = False
        self.in_cell = False
        self.current_row = []
        self.current_cell = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_row = True
            self.current_row = []
        elif tag in {"td", "th"} and self.in_row:
            self.in_cell = True
            self.current_cell = []

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.in_cell:
            text = "".join(self.current_cell).strip()
            self.current_row.append(" ".join(text.split()))
            self.in_cell = False
            self.current_cell = []
        elif tag == "tr" and self.in_row:
            if self.current_row:
                self.rows.append(self.current_row)
            self.in_row = False
            self.current_row = []

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data)


def fetch_twse_dividend_list():
    urls = [
        "https://www.twse.com.tw/en/ETFortune-institute/dividendList",
        "https://wwwc.twse.com.tw/en/ETFortune-institute/dividendList",
    ]
    html = None
    last_error = None

    for url in urls:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                html = response.read().decode("utf-8", errors="ignore")
                break
        except urllib.error.URLError as error:
            last_error = error

    if html is None:
        raise RuntimeError("目前無法連線至 TWSE 股利資料來源，請稍後再試") from last_error

    parser = TwseDividendListParser()
    parser.feed(html)

    unique_items = {}
    for row in parser.rows:
        if len(row) < 6:
            continue
        if row[0] == "ETF Code" or "/" not in row[2] or "/" not in row[3]:
            continue
        dividend = parse_float(row[4])
        if dividend is None:
            continue
        item = {
            "symbol": row[0].strip(),
            "name": row[1].strip(),
            "ex_dividend_date": row[2].replace("/", "-"),
            "payment_date": row[3].replace("/", "-"),
            "cash_dividend_per_unit": round(dividend, 3),
            "source": "TWSE ETF dividend list",
        }
        key = (item["symbol"], item["ex_dividend_date"], item["payment_date"])
        existing = unique_items.get(key)
        if (
            existing is None
            or item["cash_dividend_per_unit"] > existing["cash_dividend_per_unit"]
            or len(item["name"]) > len(existing["name"])
        ):
            unique_items[key] = item

    return list(unique_items.values())


def refresh_dividend_events(force=False):
    now = datetime.now(TAIPEI_TZ)
    if not force and now.hour < DIVIDEND_REFRESH_HOUR:
        return {"updated_count": 0}

    items = fetch_twse_dividend_list()
    updated_at = now.isoformat(timespec="seconds")

    with get_connection() as connection:
        connection.execute("DELETE FROM dividend_events WHERE source = 'TWSE ETF dividend list'")
        connection.executemany(
            """
            INSERT INTO dividend_events (
                symbol, name, ex_dividend_date, payment_date, cash_dividend_per_unit, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, ex_dividend_date, payment_date) DO UPDATE SET
                name = excluded.name,
                cash_dividend_per_unit = excluded.cash_dividend_per_unit,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            [
                (
                    item["symbol"],
                    item["name"],
                    item["ex_dividend_date"],
                    item["payment_date"],
                    item["cash_dividend_per_unit"],
                    item["source"],
                    updated_at,
                )
                for item in items
            ],
        )
        connection.commit()

    return {"updated_count": len(items)}


def compute_position_until(ex_dividend_date):
    with get_connection() as connection:
        trades = connection.execute(
            """
            SELECT account, symbol, name, side, quantity, amount, fee, tax, date, created_at
            FROM trades
            WHERE date < ?
            ORDER BY date ASC, created_at ASC
            """,
            (ex_dividend_date,),
        ).fetchall()

    positions = {}
    for trade in trades:
        key = (trade["account"], trade["symbol"])
        position = positions.setdefault(
            key,
            {
                "account": trade["account"],
                "symbol": trade["symbol"],
                "name": trade["name"],
                "quantity": 0,
                "cost_basis": 0.0,
            },
        )
        position["name"] = trade["name"]

        if trade["side"] == "買入":
            position["quantity"] += trade["quantity"]
            position["cost_basis"] += trade["amount"] + trade["fee"] + trade["tax"]
            continue

        if position["quantity"] <= 0:
            position["quantity"] = 0
            position["cost_basis"] = 0.0
            continue

        avg_cost = position["cost_basis"] / position["quantity"] if position["quantity"] else 0
        reduction_qty = min(trade["quantity"], position["quantity"])
        position["quantity"] -= reduction_qty
        position["cost_basis"] -= avg_cost * reduction_qty
        if position["quantity"] <= 0:
            position["quantity"] = 0
            position["cost_basis"] = 0.0

    return positions


def build_dividend_record(event, account, position, adjustment_map):
    computed_quantity = int(position["quantity"]) if position else 0
    manual_units = event.get("eligible_units")
    quantity = int(manual_units) if manual_units is not None else computed_quantity
    cost_basis = float(position["cost_basis"]) if position else 0.0
    computed_avg_price = round(cost_basis / quantity, 2) if quantity else 0
    manual_avg_price = event.get("avg_price")
    avg_price = (
        round(float(manual_avg_price), 2)
        if manual_avg_price is not None
        else computed_avg_price
    )
    gross_amount = round(quantity * float(event["cash_dividend_per_unit"]), 2)
    adjustment = adjustment_map.get(
        (account, event["symbol"], event["ex_dividend_date"], event["payment_date"]),
        {},
    )
    bank_fee = round(float(adjustment.get("bank_fee", 0) or 0), 2)
    net_amount = round(gross_amount - bank_fee, 2)
    manual_yield_rate = event.get("yield_rate")
    yield_rate = (
        round(float(manual_yield_rate), 2)
        if manual_yield_rate is not None
        else (
            round((float(event["cash_dividend_per_unit"]) / avg_price) * 100, 2)
            if avg_price > 0
            else None
        )
    )

    ex_date = event["ex_dividend_date"]
    return {
        "account": account,
        "ex_dividend_date": ex_date,
        "payment_date": event["payment_date"],
        "year": ex_date[:4],
        "month": str(int(ex_date[5:7])),
        "symbol": event["symbol"],
        "name": (position["name"] if position and position.get("name") else "") or event["name"],
        "eligible_units": quantity,
        "avg_price": avg_price,
        "cash_dividend_per_unit": round(float(event["cash_dividend_per_unit"]), 3),
        "yield_rate": yield_rate,
        "gross_amount": gross_amount,
        "bank_fee": bank_fee,
        "net_amount": net_amount,
        "source": event["source"],
        "manual_event_id": event.get("id"),
        "is_manual": event["source"] == "manual",
        "updated_at": event["updated_at"],
    }


def list_dividend_records(account_filter="ALL"):
    with get_connection() as connection:
        official_events = connection.execute(
            """
            SELECT symbol, name, ex_dividend_date, payment_date, cash_dividend_per_unit, source, updated_at
            FROM dividend_events
            ORDER BY ex_dividend_date DESC, symbol ASC
            """
        ).fetchall()
        manual_events = connection.execute(
            """
            SELECT id, account, symbol, name, ex_dividend_date, payment_date, eligible_units, cash_dividend_per_unit, avg_price, yield_rate, updated_at
            FROM dividend_manual_events
            ORDER BY ex_dividend_date DESC, symbol ASC
            """
        ).fetchall()
        adjustments = connection.execute(
            """
            SELECT account, symbol, ex_dividend_date, payment_date, bank_fee, updated_at
            FROM dividend_adjustments
            """
        ).fetchall()

    adjustment_map = {
        (row["account"], row["symbol"], row["ex_dividend_date"], row["payment_date"]): dict(row)
        for row in adjustments
    }

    records = []
    manual_keys = {
        (row["account"], row["symbol"], row["ex_dividend_date"], row["payment_date"])
        for row in manual_events
    }
    all_events = [dict(row) for row in official_events] + [
        {
            "id": row["id"],
            "account": row["account"],
            "symbol": row["symbol"],
            "name": row["name"],
            "ex_dividend_date": row["ex_dividend_date"],
            "payment_date": row["payment_date"],
            "eligible_units": row["eligible_units"],
            "cash_dividend_per_unit": row["cash_dividend_per_unit"],
            "avg_price": row["avg_price"],
            "yield_rate": row["yield_rate"],
            "source": "manual",
            "updated_at": row["updated_at"],
        }
        for row in manual_events
    ]

    for event in all_events:
        positions = compute_position_until(event["ex_dividend_date"])
        if event["source"] == "manual":
            account = event["account"]
            if account_filter != "ALL" and account != account_filter:
                continue
            position = positions.get(
                (account, event["symbol"]),
                {
                    "account": account,
                    "symbol": event["symbol"],
                    "name": event["name"],
                    "quantity": 0,
                    "cost_basis": 0.0,
                },
            )
            records.append(build_dividend_record(event, account, position, adjustment_map))
            continue

        for (account, symbol), position in positions.items():
            if symbol != event["symbol"] or position["quantity"] <= 0:
                continue
            if account_filter != "ALL" and account != account_filter:
                continue
            if (
                account,
                symbol,
                event["ex_dividend_date"],
                event["payment_date"],
            ) in manual_keys:
                continue
            records.append(build_dividend_record(event, account, position, adjustment_map))

    records.sort(key=lambda item: (item["ex_dividend_date"], item["account"], item["symbol"]), reverse=True)
    return {"items": records}


def validate_dividend_event_fields(
    account,
    symbol,
    name,
    ex_dividend_date,
    payment_date,
    eligible_units,
    cash_dividend_per_unit,
    avg_price=None,
    yield_rate=None,
):
    if not account or not symbol or not name or not ex_dividend_date or not payment_date:
        raise ValueError("股利資料欄位不可為空")
    try:
        datetime.strptime(ex_dividend_date, "%Y-%m-%d")
        datetime.strptime(payment_date, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError("日期格式必須為 YYYY-MM-DD") from error
    if eligible_units is not None and eligible_units < 0:
        raise ValueError("單位數不可小於 0")
    if cash_dividend_per_unit < 0:
        raise ValueError("每股股利不可小於 0")
    if avg_price is not None and avg_price < 0:
        raise ValueError("股價不可小於 0")
    if yield_rate is not None and yield_rate < 0:
        raise ValueError("殖利率不可小於 0")


def create_manual_dividend_event(payload):
    account = str(payload.get("account", "")).strip() or "主帳戶"
    symbol = str(payload.get("symbol", "")).strip()
    name = str(payload.get("name", "")).strip()
    ex_dividend_date = str(payload.get("ex_dividend_date", "")).strip()
    payment_date = str(payload.get("payment_date", "")).strip()
    raw_eligible_units = payload.get("eligible_units")
    eligible_units = (
        None
        if raw_eligible_units in (None, "", "null")
        else int(float(raw_eligible_units))
    )
    cash_dividend_per_unit = round(float(payload.get("cash_dividend_per_unit", 0) or 0), 3)
    raw_avg_price = payload.get("avg_price")
    avg_price = None if raw_avg_price in (None, "", "null") else round(float(raw_avg_price), 2)
    raw_yield_rate = payload.get("yield_rate")
    yield_rate = None if raw_yield_rate in (None, "", "null") else round(float(raw_yield_rate), 2)
    validate_dividend_event_fields(
        account,
        symbol,
        name,
        ex_dividend_date,
        payment_date,
        eligible_units,
        cash_dividend_per_unit,
        avg_price,
        yield_rate,
    )
    ensure_account_exists(account)

    event_id = create_trade_id()
    updated_at = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO dividend_manual_events (
                id, account, symbol, name, ex_dividend_date, payment_date, eligible_units, cash_dividend_per_unit, avg_price, yield_rate, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                account,
                symbol,
                name,
                ex_dividend_date,
                payment_date,
                eligible_units,
                cash_dividend_per_unit,
                avg_price,
                yield_rate,
                updated_at,
            ),
        )
        connection.commit()

    return {
        "id": event_id,
        "account": account,
        "symbol": symbol,
        "name": name,
        "ex_dividend_date": ex_dividend_date,
        "payment_date": payment_date,
        "eligible_units": eligible_units,
        "cash_dividend_per_unit": cash_dividend_per_unit,
        "avg_price": avg_price,
        "yield_rate": yield_rate,
        "updated_at": updated_at,
    }


def update_manual_dividend_event(event_id, payload):
    account = str(payload.get("account", "")).strip() or "主帳戶"
    symbol = str(payload.get("symbol", "")).strip()
    name = str(payload.get("name", "")).strip()
    ex_dividend_date = str(payload.get("ex_dividend_date", "")).strip()
    payment_date = str(payload.get("payment_date", "")).strip()
    raw_eligible_units = payload.get("eligible_units")
    eligible_units = (
        None
        if raw_eligible_units in (None, "", "null")
        else int(float(raw_eligible_units))
    )
    cash_dividend_per_unit = round(float(payload.get("cash_dividend_per_unit", 0) or 0), 3)
    raw_avg_price = payload.get("avg_price")
    avg_price = None if raw_avg_price in (None, "", "null") else round(float(raw_avg_price), 2)
    raw_yield_rate = payload.get("yield_rate")
    yield_rate = None if raw_yield_rate in (None, "", "null") else round(float(raw_yield_rate), 2)
    validate_dividend_event_fields(
        account,
        symbol,
        name,
        ex_dividend_date,
        payment_date,
        eligible_units,
        cash_dividend_per_unit,
        avg_price,
        yield_rate,
    )
    ensure_account_exists(account)

    updated_at = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")
    with get_connection() as connection:
        original_event = connection.execute(
            """
            SELECT account, symbol, ex_dividend_date, payment_date
            FROM dividend_manual_events
            WHERE id = ?
            """,
            (event_id,),
        ).fetchone()
        if not original_event:
            raise LookupError("找不到要更新的手動股利資料")

        cursor = connection.execute(
            """
            UPDATE dividend_manual_events
            SET account = ?, symbol = ?, name = ?, ex_dividend_date = ?, payment_date = ?, eligible_units = ?, cash_dividend_per_unit = ?, avg_price = ?, yield_rate = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                account,
                symbol,
                name,
                ex_dividend_date,
                payment_date,
                eligible_units,
                cash_dividend_per_unit,
                avg_price,
                yield_rate,
                updated_at,
                event_id,
            ),
        )
        if (
            original_event["account"] != account
            or original_event["symbol"] != symbol
            or original_event["ex_dividend_date"] != ex_dividend_date
            or original_event["payment_date"] != payment_date
        ):
            connection.execute(
                """
                DELETE FROM dividend_adjustments
                WHERE account = ? AND symbol = ? AND ex_dividend_date = ? AND payment_date = ?
                """,
                (
                    original_event["account"],
                    original_event["symbol"],
                    original_event["ex_dividend_date"],
                    original_event["payment_date"],
                ),
            )
        connection.commit()

    if cursor.rowcount == 0:
        raise LookupError("找不到要更新的手動股利資料")

    return {
        "id": event_id,
        "account": account,
        "symbol": symbol,
        "name": name,
        "ex_dividend_date": ex_dividend_date,
        "payment_date": payment_date,
        "eligible_units": eligible_units,
        "cash_dividend_per_unit": cash_dividend_per_unit,
        "avg_price": avg_price,
        "yield_rate": yield_rate,
        "updated_at": updated_at,
    }


def delete_manual_dividend_event(event_id):
    with get_connection() as connection:
        event = connection.execute(
            """
            SELECT account, symbol, ex_dividend_date, payment_date
            FROM dividend_manual_events
            WHERE id = ?
            """,
            (event_id,),
        ).fetchone()
        if not event:
            raise LookupError("找不到要刪除的手動股利資料")

        connection.execute("DELETE FROM dividend_manual_events WHERE id = ?", (event_id,))
        connection.execute(
            """
            DELETE FROM dividend_adjustments
            WHERE account = ? AND symbol = ? AND ex_dividend_date = ? AND payment_date = ?
            """,
            (event["account"], event["symbol"], event["ex_dividend_date"], event["payment_date"]),
        )
        connection.commit()


def save_dividend_adjustment(payload):
    account = str(payload.get("account", "")).strip()
    symbol = str(payload.get("symbol", "")).strip()
    ex_dividend_date = str(payload.get("ex_dividend_date", "")).strip()
    payment_date = str(payload.get("payment_date", "")).strip()
    bank_fee = round(float(payload.get("bank_fee", 0) or 0), 2)

    if not account or not symbol or not ex_dividend_date or not payment_date:
        raise ValueError("股利調整資料不完整")
    if bank_fee < 0:
        raise ValueError("跨行扣款不可小於 0")

    now = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO dividend_adjustments (account, symbol, ex_dividend_date, payment_date, bank_fee, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account, symbol, ex_dividend_date, payment_date) DO UPDATE SET
                bank_fee = excluded.bank_fee,
                updated_at = excluded.updated_at
            """,
            (account, symbol, ex_dividend_date, payment_date, bank_fee, now),
        )
        connection.commit()

    return {
        "account": account,
        "symbol": symbol,
        "ex_dividend_date": ex_dividend_date,
        "payment_date": payment_date,
        "bank_fee": bank_fee,
        "updated_at": now,
    }


def parse_float(value):
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if not text or text in {"--", "---", "N/A"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def extract_price_rows(payload):
    tables = []

    if isinstance(payload, dict) and "tables" in payload:
        for table in payload.get("tables", []):
            tables.append((table.get("fields", []), table.get("data", [])))

    if isinstance(payload, dict):
        for key, value in payload.items():
            if not key.startswith("fields"):
                continue
            suffix = key.replace("fields", "")
            data_key = f"data{suffix}"
            tables.append((value or [], payload.get(data_key, [])))

    price_map = {}
    code_candidates = {"證券代號", "Security Code", "Code"}
    name_candidates = {"證券名稱", "Security Name", "Name"}
    price_candidates = {"收盤價", "Closing Price", "Close"}

    for fields, rows in tables:
        if not fields or not rows:
            continue

        code_index = next((i for i, field in enumerate(fields) if field in code_candidates), None)
        name_index = next((i for i, field in enumerate(fields) if field in name_candidates), None)
        price_index = next((i for i, field in enumerate(fields) if field in price_candidates), None)
        if code_index is None or price_index is None:
            continue

        for row in rows:
            if len(row) <= max(code_index, price_index):
                continue
            code = str(row[code_index]).strip()
            if not code:
                continue
            price = parse_float(row[price_index])
            if price is None:
                continue
            price_map[code] = {
                "symbol": code,
                "name": str(row[name_index]).strip() if name_index is not None and len(row) > name_index else "",
                "price": round(price, 2),
            }

    return price_map


def fetch_twse_daily_prices(query_date):
    url = (
        "https://www.twse.com.tw/exchangeReport/MI_INDEX?"
        + urllib.parse.urlencode(
            {
                "response": "json",
                "date": query_date.strftime("%Y%m%d"),
                "type": "ALLBUT0999",
            }
        )
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return extract_price_rows(payload)


def refresh_quotes(force=False):
    inventory_symbols = {item["symbol"] for item in compute_inventory_items()}
    if not inventory_symbols:
        return {"updated_count": 0, "quoted_date": None}

    now = datetime.now(TAIPEI_TZ)
    if not force and now.hour < PRICE_REFRESH_HOUR:
        return {"updated_count": 0, "quoted_date": None}

    latest_map = {}
    quoted_date = None
    for day_offset in range(0, 7):
        query_date = now.date() - timedelta(days=day_offset)
        try:
            daily_prices = fetch_twse_daily_prices(query_date)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        if daily_prices:
            latest_map = daily_prices
            quoted_date = query_date.isoformat()
            break

    if not latest_map or not quoted_date:
        return {"updated_count": 0, "quoted_date": None}

    now_text = now.isoformat(timespec="seconds")
    updated_count = 0
    with get_connection() as connection:
        for symbol in inventory_symbols:
            price_row = latest_map.get(symbol)
            if not price_row:
                continue
            connection.execute(
                """
                INSERT INTO quotes (symbol, price, quoted_date, updated_at, source)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    price = excluded.price,
                    quoted_date = excluded.quoted_date,
                    updated_at = excluded.updated_at,
                    source = excluded.source
                """,
                (
                    symbol,
                    price_row["price"],
                    quoted_date,
                    now_text,
                    "TWSE public after-market data",
                ),
            )
            updated_count += 1
        connection.commit()

    return {"updated_count": updated_count, "quoted_date": quoted_date}


def get_latest_quote_refresh_date():
    with get_connection() as connection:
        row = connection.execute(
            "SELECT MAX(quoted_date) AS quoted_date FROM quotes"
        ).fetchone()
    return row["quoted_date"] if row and row["quoted_date"] else None


def maybe_refresh_quotes_on_startup():
    now = datetime.now(TAIPEI_TZ)
    today = now.date().isoformat()
    latest_refresh = get_latest_quote_refresh_date()
    if now.hour >= PRICE_REFRESH_HOUR and latest_refresh != today:
        try:
            refresh_quotes(force=True)
        except Exception:
            return


def scheduled_price_refresh_loop():
    while True:
        now = datetime.now(TAIPEI_TZ)
        next_run = now.replace(hour=PRICE_REFRESH_HOUR, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        wait_seconds = max((next_run - now).total_seconds(), 60)
        threading.Event().wait(wait_seconds)
        try:
            refresh_quotes(force=True)
        except Exception:
            continue


def maybe_refresh_dividends_on_startup():
    try:
        refresh_dividend_events(force=True)
    except Exception:
        return


def scheduled_dividend_refresh_loop():
    while True:
        now = datetime.now(TAIPEI_TZ)
        next_run = now.replace(hour=DIVIDEND_REFRESH_HOUR, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        wait_seconds = max((next_run - now).total_seconds(), 60)
        threading.Event().wait(wait_seconds)
        try:
            refresh_dividend_events(force=True)
        except Exception:
            continue


class StockRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)

            if parsed.path == "/api/health":
                self.send_json({"status": "ok"})
                return

            if parsed.path == "/api/auth/config":
                self.send_json(get_public_auth_config())
                return

            if parsed.path == "/api/auth/google/start":
                self.redirect_to_google_auth()
                return

            if parsed.path == "/api/auth/google/callback":
                self.handle_google_callback(query)
                return

            if requires_authentication(parsed.path) and not self.get_authenticated_user():
                self.reject_unauthenticated(parsed.path)
                return

            if parsed.path == "/api/auth/me":
                self.send_json({"user": self.get_authenticated_user()})
                return

            if parsed.path == "/api/trades":
                self.send_json({"items": list_trades()})
                return

            if parsed.path == "/api/accounts":
                self.send_json({"items": list_accounts()})
                return

            if parsed.path == "/api/inventory":
                account = query.get("account", ["ALL"])[0]
                self.send_json(list_inventory(account))
                return

            if parsed.path == "/api/dividends":
                account = query.get("account", ["ALL"])[0]
                self.send_json(list_dividend_records(account))
                return

            if parsed.path in STATIC_FILES:
                self.serve_static(STATIC_FILES[parsed.path])
                return

            self.send_error(HTTPStatus.NOT_FOUND)
        except Exception:
            traceback.print_exc()
            self.send_json({"error": "internal_server_error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):
        parsed = urlparse(self.path)

        try:
            payload = self.read_json_body()

            if parsed.path == "/api/auth/google":
                profile = verify_google_identity(payload.get("credential", ""))
                session = create_authenticated_session(profile)
                self.send_json(
                    {
                        "user": {
                            "email": session["email"],
                            "name": session["name"],
                            "picture": session["picture"],
                        }
                    },
                    headers={"Set-Cookie": session["Set-Cookie"]},
                )
                return

            if parsed.path == "/api/auth/logout":
                delete_authenticated_session(self.headers.get("Cookie", ""))
                self.send_json({"ok": True}, headers={"Set-Cookie": expired_session_cookie()})
                return

            if requires_authentication(parsed.path) and not self.get_authenticated_user():
                self.reject_unauthenticated(parsed.path)
                return

            if parsed.path == "/api/trades":
                trade = create_trade(payload)
                self.send_json({"item": trade}, status=HTTPStatus.CREATED)
                return

            if parsed.path == "/api/trades/import":
                items = replace_trades(payload.get("items"))
                self.send_json({"items": items})
                return

            if parsed.path == "/api/accounts":
                account = create_account(payload)
                self.send_json({"item": account}, status=HTTPStatus.CREATED)
                return

            if parsed.path == "/api/inventory/target":
                item = save_inventory_target(payload)
                self.send_json({"item": item})
                return

            if parsed.path == "/api/dividends/adjustment":
                item = save_dividend_adjustment(payload)
                self.send_json({"item": item})
                return

            if parsed.path == "/api/dividends/manual":
                item = create_manual_dividend_event(payload)
                self.send_json({"item": item}, status=HTTPStatus.CREATED)
                return

            if parsed.path == "/api/inventory/target/bulk":
                result = bulk_apply_target_percentage(payload)
                self.send_json(result)
                return

            if parsed.path == "/api/dividends/refresh":
                result = refresh_dividend_events(force=True)
                self.send_json(result)
                return

            if parsed.path == "/api/prices/refresh":
                result = refresh_quotes(force=True)
                self.send_json(result)
                return

            self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self.send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
        except Exception:
            traceback.print_exc()
            self.send_json({"error": "目前無法更新資料，請稍後再試"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self):
        parsed = urlparse(self.path)

        try:
            if requires_authentication(parsed.path) and not self.get_authenticated_user():
                self.reject_unauthenticated(parsed.path)
                return

            payload = self.read_json_body()

            if parsed.path.startswith("/api/trades/"):
                trade_id = strip_prefix(parsed.path, "/api/trades/")
                trade = update_trade(trade_id, payload)
                self.send_json({"item": trade})
                return

            if parsed.path.startswith("/api/accounts/"):
                account_id = strip_prefix(parsed.path, "/api/accounts/")
                account = update_account(account_id, payload)
                self.send_json({"item": account})
                return

            if parsed.path.startswith("/api/dividends/manual/"):
                event_id = strip_prefix(parsed.path, "/api/dividends/manual/")
                item = update_manual_dividend_event(event_id, payload)
                self.send_json({"item": item})
                return

            self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self.send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
        except LookupError as error:
            self.send_json({"error": str(error)}, status=HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        parsed = urlparse(self.path)

        try:
            if requires_authentication(parsed.path) and not self.get_authenticated_user():
                self.reject_unauthenticated(parsed.path)
                return

            if parsed.path.startswith("/api/trades/"):
                trade_id = strip_prefix(parsed.path, "/api/trades/")
                delete_trade(trade_id)
                self.send_json({"deleted": True})
                return

            if parsed.path.startswith("/api/accounts/"):
                account_id = strip_prefix(parsed.path, "/api/accounts/")
                delete_account(account_id)
                self.send_json({"deleted": True})
                return

            if parsed.path.startswith("/api/dividends/manual/"):
                event_id = strip_prefix(parsed.path, "/api/dividends/manual/")
                delete_manual_dividend_event(event_id)
                self.send_json({"deleted": True})
                return

            self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self.send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
        except LookupError as error:
            self.send_json({"error": str(error)}, status=HTTPStatus.NOT_FOUND)

    def read_json_body(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("JSON 格式錯誤") from error

    def serve_static(self, filename):
        file_path = BASE_DIR / filename
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def get_authenticated_user(self):
        bearer_user = get_authenticated_user_from_bearer(self.headers.get("Authorization", ""))
        if bearer_user:
            return bearer_user
        return get_authenticated_user_from_cookie(self.headers.get("Cookie", ""))

    def request_origin(self):
        forwarded_proto = self.headers.get("X-Forwarded-Proto")
        proto = (forwarded_proto.split(",")[0].strip() if forwarded_proto else "http") or "http"
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host")
        return f"{proto}://{host}" if host else ""

    def redirect_to_google_auth(self):
        env_error = google_oauth_env_error()
        if env_error:
            self.send_json(env_error, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return
        location, state = build_google_auth_url()
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Set-Cookie", oauth_state_cookie(state))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def handle_google_callback(self, query):
        if query.get("error", [""])[0]:
            self.send_json(
                {
                    "error": "Google 登入失敗：" + query.get("error", [""])[0],
                    "fix": "請重新點選 Log in with Google；若持續失敗，請檢查 GCP OAuth consent screen 與 Authorized redirect URI。",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        code = query.get("code", [""])[0]
        if not code:
            self.send_json(
                {"error": "Google callback 缺少 code", "fix": "請從 /login.html 點選 Log in with Google 重新登入。"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        state = query.get("state", [""])[0]
        cookie_state = get_oauth_state_from_cookie(self.headers.get("Cookie", ""))
        if state and cookie_state and state != cookie_state:
            self.send_json(
                {"error": "Google OAuth state 驗證失敗", "fix": "請重新點選 Log in with Google；不要手動修改 callback URL。"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            tokens = exchange_google_code(code, get_redirect_uri())
            profile = validate_google_profile(fetch_google_userinfo(tokens.get("access_token", "")))
            session = create_authenticated_session(profile)
        except ValueError as error:
            self.send_json(
                {"error": str(error), "fix": "請確認 GOOGLE_CLIENT_ID、GOOGLE_CLIENT_SECRET、REDIRECT_URI 與 GCP Authorized redirect URI 設定正確。"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        user = {"email": session["email"], "name": session["name"], "picture": session["picture"]}
        if query.get("return", [""])[0] == "json":
            self.send_json({"user": user}, headers={"Set-Cookie": session["Set-Cookie"]})
            return

        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", session["Set-Cookie"])
        self.send_header("Content-Length", "0")
        self.end_headers()

    def reject_unauthenticated(self, path):
        if path.startswith("/api/"):
            self.send_json({"error": "authentication_required"}, status=HTTPStatus.UNAUTHORIZED)
            return
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", "/login.html")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_json(self, payload, status=HTTPStatus.OK, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def run():
    ensure_database()
    startup_refresh = threading.Thread(target=maybe_refresh_quotes_on_startup, daemon=True)
    startup_refresh.start()
    scheduler = threading.Thread(target=scheduled_price_refresh_loop, daemon=True)
    scheduler.start()
    dividend_startup_refresh = threading.Thread(target=maybe_refresh_dividends_on_startup, daemon=True)
    dividend_startup_refresh.start()
    dividend_scheduler = threading.Thread(target=scheduled_dividend_refresh_loop, daemon=True)
    dividend_scheduler.start()
    host = get_env_host()
    port = get_env_port()
    server = ThreadingHTTPServer((host, port), StockRequestHandler)
    print(f"Stock app running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
