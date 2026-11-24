"""Run with python3 -m backend.server. No third-party dependencies required."""
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .detection import LANGUAGE_HINTS, analyze, model_status

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.environ.get("NETRA_DB", str(ROOT / "data" / "netra.sqlite3")))
PASSWORD = os.environ.get("AUTHORITY_PASSWORD") or secrets.token_urlsafe(12)
SESSIONS = {}

def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    return db

def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, text TEXT NOT NULL, source TEXT NOT NULL, analysis TEXT NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', updated_at TEXT)")

def record(row):
    item = dict(row)
    item["analysis"] = json.loads(item["analysis"])
    return item

class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200, cookie=None):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def authenticated(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            token = cookie["netra_session"].value
            return SESSIONS.get(token, 0) > time.time()
        except (KeyError, ValueError):
            return False

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.send_json({"ok": True, **model_status(), "authenticated": self.authenticated()})
        if path == "/api/messages":
            if not self.authenticated():
                return self.send_json({"error": "Authority login required"}, 401)
            with connect() as db:
                rows = db.execute("SELECT * FROM messages ORDER BY created_at DESC LIMIT 1000").fetchall()
            return self.send_json({"messages": [record(row) for row in rows]})
        files = {"/": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}
        if path not in files:
            return self.send_json({"error": "Not found"}, 404)
        file = ROOT / "frontend" / files[path]
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css"}[file.suffix])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        # Block cross-site mutations, including localhost-targeting forms.
        origin = self.headers.get("Origin")
        if origin and origin not in ("http://" + self.headers.get("Host", ""), "https://" + self.headers.get("Host", "")):
            return self.send_json({"error": "Origin rejected"}, 403)
        try:
            size = int(self.headers.get("Content-Length", 0))
            if size < 1 or size > 64000:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
        except (ValueError, UnicodeError):
            return self.send_json({"error": "Invalid JSON request"}, 400)
        path = urlparse(self.path).path
        if path == "/api/login":
            password = data.get("password", "")
            if not isinstance(password, str) or not hmac.compare_digest(password.encode(), PASSWORD.encode()):
                return self.send_json({"error": "Incorrect authority password"}, 401)
            token = secrets.token_urlsafe(32)
            SESSIONS[token] = time.time() + 8 * 3600
            return self.send_json({"ok": True}, cookie=f"netra_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800")
        if path == "/api/logout":
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            if "netra_session" in cookie:
                SESSIONS.pop(cookie["netra_session"].value, None)
            return self.send_json({"ok": True}, cookie="netra_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
        if path == "/api/analyze":
            text, source = data.get("text", ""), data.get("source", "Manual submission")
            language_hint = data.get("language_hint", "auto")
            if language_hint not in LANGUAGE_HINTS:
                return self.send_json({"error": "Select auto, english, hinglish, or other for language."}, 400)
            if not isinstance(text, str) or not 3 <= len(text.strip()) <= 5000 or not isinstance(source, str) or len(source) > 120:
                return self.send_json({"error": "Enter a message of 3–5,000 characters and a source under 120 characters."}, 400)
            text = text.strip()
            analysis = analyze(text, language_hint)
            item = {"id": secrets.token_hex(6).upper(), "created_at": datetime.now(timezone.utc).isoformat(), "text": text, "source": source.strip() or "Manual submission", "analysis": analysis, "status": "screened" if analysis["verdict"] == "no_flags" else "pending", "note": "", "updated_at": None}
            with connect() as db:
                db.execute("INSERT INTO messages (id,created_at,text,source,analysis,status) VALUES (?,?,?,?,?,?)", (item["id"], item["created_at"], text, item["source"], json.dumps(analysis), item["status"]))
            return self.send_json(item, 201)
        if path == "/api/review":
            if not self.authenticated():
                return self.send_json({"error": "Authority login required"}, 401)
            status, note = data.get("status"), data.get("note", "")
            if status not in ("pending", "investigating", "dismissed", "escalated") or not isinstance(note, str) or len(note) > 2000 or not isinstance(data.get("id"), str):
                return self.send_json({"error": "Invalid review"}, 400)
            with connect() as db:
                cursor = db.execute("UPDATE messages SET status=?, note=?, updated_at=? WHERE id=? AND status != 'screened'", (status, note, datetime.now(timezone.utc).isoformat(), data["id"]))
            return self.send_json({"ok": True} if cursor.rowcount else {"error": "Review item not found"}, 200 if cursor.rowcount else 404)
        return self.send_json({"error": "Not found"}, 404)

if __name__ == "__main__":
    initialize()
    host, port = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000"))
    print(f"NETRA running at http://{host}:{port}", flush=True)
    print(f"Authority password: {PASSWORD}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
