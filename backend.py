"""CyberShield local learning server: Python stdlib + SQLite."""

from __future__ import annotations

import hmac
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CYBERSHIELD_DB", ROOT / "data" / "messages.sqlite3"))
ADMIN_USER = os.environ.get("CYBERSHIELD_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("CYBERSHIELD_ADMIN_PASSWORD", "")
MAX_BODY = 16_384
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
SESSIONS: set[str] = set()
SESSIONS_LOCK = threading.Lock()
LOGGER = logging.getLogger("cybershield")


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database():
    connection = connect_db()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_db() -> None:
    with database() as connection:
        connection.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'")
        super().end_headers()

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_payload(self) -> dict:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("Некоректний розмір запиту.") from exc
        if length < 0 or length > MAX_BODY:
            raise ValueError("Запит завеликий.")
        raw = self.rfile.read(length)
        content_type = self.headers.get_content_type()
        try:
            if content_type == "application/json":
                value = json.loads(raw or b"{}")
            elif content_type == "application/x-www-form-urlencoded":
                from urllib.parse import parse_qs
                fields = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
                value = {key: values[0] for key, values in fields.items()}
            else:
                raise ValueError("Підтримуються JSON або URL-encoded дані.")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Не вдалося прочитати дані форми.") from exc
        if not isinstance(value, dict):
            raise ValueError("Очікується об’єкт із полями форми.")
        return value

    def session_id(self) -> str | None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            return None
        morsel = cookie.get("cybershield_session")
        return morsel.value if morsel else None

    def is_authenticated(self) -> bool:
        session = self.session_id()
        if not session:
            return False
        with SESSIONS_LOCK:
            return session in SESSIONS

    def require_auth(self) -> bool:
        if self.is_authenticated():
            return True
        self.send_json(401, {"error": "Потрібен вхід адміністратора."})
        return False

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/messages":
            if not self.require_auth():
                return
            try:
                with database() as connection:
                    rows = connection.execute(
                        "SELECT id, name, email, message, created_at FROM messages ORDER BY created_at DESC, id DESC"
                    ).fetchall()
            except sqlite3.Error:
                LOGGER.exception("Could not read messages from the database")
                self.send_json(500, {"error": "Не вдалося прочитати повідомлення."})
                return
            self.send_json(200, {"messages": [dict(row) for row in rows]})
            return
        if path.startswith("/api/"):
            self.send_json(404, {"error": "API-маршрут не знайдено."})
            return
        if path == "/messages":
            self.path = "/messages.html"
        super().do_GET()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path not in ("/api/messages", "/api/login", "/api/logout"):
            self.send_json(404, {"error": "Маршрут не знайдено."})
            return
        try:
            data = self.read_payload()
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
            return

        if path == "/api/login":
            username = str(data.get("username", ""))
            password = str(data.get("password", ""))
            if not (hmac.compare_digest(username.encode("utf-8"), ADMIN_USER.encode("utf-8")) and hmac.compare_digest(password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8"))):
                self.send_json(401, {"error": "Неправильне ім’я користувача або пароль."})
                return
            token = secrets.token_urlsafe(32)
            with SESSIONS_LOCK:
                SESSIONS.add(token)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", f"cybershield_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/logout":
            token = self.session_id()
            with SESSIONS_LOCK:
                if token:
                    SESSIONS.discard(token)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", "cybershield_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip()
        message = str(data.get("message", "")).strip()
        errors = {}
        if not 2 <= len(name) <= 100:
            errors["name"] = "Ім’я має містити від 2 до 100 символів."
        if len(email) > 254 or not EMAIL_RE.fullmatch(email):
            errors["email"] = "Вкажи коректну електронну адресу."
        if not 5 <= len(message) <= 5000:
            errors["message"] = "Повідомлення має містити від 5 до 5000 символів."
        if errors:
            self.send_json(400, {"error": "Перевір заповнення полів.", "fields": errors})
            return
        created_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        try:
            with database() as connection:
                cursor = connection.execute(
                    "INSERT INTO messages (name, email, message, created_at) VALUES (?, ?, ?, ?)",
                    (name, email, message, created_at),
                )
                message_id = cursor.lastrowid
        except sqlite3.Error:
            LOGGER.exception("Could not save a submitted message")
            self.send_json(500, {"error": "Не вдалося зберегти повідомлення."})
            return
        self.send_json(201, {"ok": True, "message": "Повідомлення успішно збережено.", "id": message_id})

    def do_DELETE(self) -> None:
        path = urlsplit(self.path).path
        match = re.fullmatch(r"/api/messages/(\d+)", path)
        if not match:
            self.send_json(404, {"error": "API-маршрут не знайдено."})
            return
        if not self.require_auth():
            return
        try:
            with database() as connection:
                cursor = connection.execute("DELETE FROM messages WHERE id = ?", (int(match.group(1)),))
        except sqlite3.Error:
            LOGGER.exception("Could not delete a message")
            self.send_json(500, {"error": "Не вдалося видалити повідомлення."})
            return
        if cursor.rowcount == 0:
            self.send_json(404, {"error": "Повідомлення не знайдено."})
            return
        self.send_json(200, {"ok": True, "message": "Повідомлення видалено."})


class LoggingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        LOGGER.exception("Unhandled request error from %s", client_address[0])


if __name__ == "__main__":
    if not ADMIN_PASSWORD:
        raise SystemExit("Set CYBERSHIELD_ADMIN_PASSWORD before starting the server.")
    log_path = ROOT / "data" / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.setLevel(logging.INFO)
    log_handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(log_handler)
    initialize_db()
    server = LoggingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8000"))), Handler)
    print(f"CyberShield запущено: http://127.0.0.1:{server.server_port}")
    print(f"База даних: {DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер зупинено.")
    finally:
        server.server_close()
