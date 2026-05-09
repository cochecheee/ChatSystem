"""
Vulnerable Flask sample for chat-system / sast-chat demo.

CONTAINS INTENTIONAL SECURITY FLAWS. Do not deploy publicly.
See README.md for the list of seeded vulnerabilities.
"""
import os
import sqlite3
import urllib.request

from flask import Flask, request
from markupsafe import Markup

app = Flask(__name__)

# Vuln #4 — Hardcoded secret (Bandit B105)
SECRET_KEY = "super-secret-do-not-rotate-2024"
app.config["SECRET_KEY"] = SECRET_KEY

DB_PATH = "/tmp/sample.db"


def init_db() -> None:
    con = sqlite3.connect(DB_PATH)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT
        );
        INSERT OR IGNORE INTO users (id, name, email)
        VALUES (1, 'alice', 'alice@example.com'),
               (2, 'bob',   'bob@example.com');
        """
    )
    con.commit()
    con.close()


@app.route("/")
def index() -> str:
    return (
        "<h1>Vulnerable sample</h1>"
        "<ul>"
        "<li><a href='/user?id=1'>/user?id=1</a> (SQLi)</li>"
        "<li><a href='/greet?name=Tien'>/greet?name=Tien</a> (XSS)</li>"
        "<li><a href='/ping?host=8.8.8.8'>/ping?host=8.8.8.8</a> (cmd injection)</li>"
        "<li><a href='/fetch?url=https://example.com'>/fetch?url=...</a> (SSRF)</li>"
        "</ul>"
    )


@app.route("/user")
def user_lookup() -> str:
    """Vuln #1 — SQL injection via f-string concat."""
    user_id = request.args.get("id", "1")
    con = sqlite3.connect(DB_PATH)
    # nosec ignored on purpose — Semgrep + Bandit should still flag this.
    query = f"SELECT id, name, email FROM users WHERE id = {user_id}"
    rows = con.execute(query).fetchall()
    con.close()
    return f"<pre>{rows}</pre>"


@app.route("/greet")
def greet() -> str:
    """Vuln #2 — Reflected XSS via Markup() bypassing autoescape."""
    name = request.args.get("name", "world")
    return Markup(f"<h2>Hello, {name}!</h2>")


@app.route("/ping")
def ping() -> str:
    """Vuln #3 — Command injection via os.system."""
    host = request.args.get("host", "127.0.0.1")
    rc = os.system(f"ping -c 1 {host}")  # noqa: S605
    return f"<pre>ping rc={rc}</pre>"


@app.route("/fetch")
def fetch_url() -> str:
    """Vuln #5 — SSRF: arbitrary URL fetch with no allowlist."""
    target = request.args.get("url", "https://example.com")
    with urllib.request.urlopen(target, timeout=5) as resp:  # noqa: S310
        body = resp.read(2000)
    return f"<pre>{body!r}</pre>"


@app.route("/health")
def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    init_db()
    # Vuln-adjacent: debug=True exposes Werkzeug debugger in some configs.
    app.run(host="0.0.0.0", port=5000, debug=False)
