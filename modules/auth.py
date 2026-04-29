"""
auth.py
User authentication system:
  - Register / Login / Logout
  - Password hashing with werkzeug
  - SQLite user table
  - Flask-Login integration
  - User profile + watchlist management
"""

import sqlite3
import os
import logging
from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "crypto.db")


# ── Flask-Login User class ─────────────────────────────────────────────────────
class User(UserMixin):
    def __init__(self, id, username, email, password_hash,
                 role="user", created_at="", avatar_initials="",
                 watchlist="", alert_email=False):
        self.id              = id
        self.username        = username
        self.email           = email
        self.password_hash   = password_hash
        self.role            = role
        self.created_at      = created_at
        self.avatar_initials = avatar_initials or username[:2].upper()
        self.watchlist       = watchlist or "bitcoin,ethereum,solana"
        self.alert_email     = alert_email

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def watchlist_list(self):
        return [w.strip() for w in self.watchlist.split(",") if w.strip()]

    @property
    def is_admin(self):
        return self.role == "admin"


# ── DB init ────────────────────────────────────────────────────────────────────
def init_user_tables():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT    NOT NULL UNIQUE,
            email           TEXT    NOT NULL UNIQUE,
            password_hash   TEXT    NOT NULL,
            role            TEXT    DEFAULT 'user',
            created_at      TEXT    NOT NULL,
            avatar_initials TEXT,
            watchlist       TEXT    DEFAULT 'bitcoin,ethereum,solana',
            alert_email     INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_alerts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            alert_id   INTEGER NOT NULL,
            read       INTEGER DEFAULT 0,
            created_at TEXT    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()

    # Seed a demo admin account if no users exist
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        _create_user(c, "rehan", "admin@cryptopulse.io",
                     "rehan22125", role="admin")
        _create_user(c, "demo", "demo@cryptopulse.io",
                     "Demo@123", role="user")
        conn.commit()
        logger.info("Demo accounts created: admin / Admin@123  |  demo / Demo@123")
    conn.close()


def _create_user(cursor, username, email, password, role="user"):
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO users (username, email, password_hash, role, created_at, avatar_initials)
        VALUES (?,?,?,?,?,?)
    """, (username, email, generate_password_hash(password),
          role, now, username[:2].upper()))


# ── CRUD ───────────────────────────────────────────────────────────────────────
def get_user_by_id(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return _row_to_user(row) if row else None


def get_user_by_username(username):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE username=?",
                       (username,)).fetchone()
    conn.close()
    return _row_to_user(row) if row else None


def get_user_by_email(email):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE email=?",
                       (email,)).fetchone()
    conn.close()
    return _row_to_user(row) if row else None


def _row_to_user(row):
    if not row:
        return None
    return User(
        id=row["id"],
        username=row["username"],
        email=row["email"],
        password_hash=row["password_hash"],
        role=row["role"],
        created_at=row["created_at"],
        avatar_initials=row["avatar_initials"],
        watchlist=row["watchlist"],
        alert_email=bool(row["alert_email"]),
    )


def register_user(username, email, password):
    """
    Returns (user, error_message).
    error_message is None on success.
    """
    if get_user_by_username(username):
        return None, "Username already taken."
    if get_user_by_email(email):
        return None, "Email already registered."
    if len(password) < 6:
        return None, "Password must be at least 6 characters."

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        _create_user(c, username, email, password)
        conn.commit()
        user = get_user_by_username(username)
        return user, None
    except Exception as e:
        logger.error("Register error: %s", e)
        return None, "Registration failed. Please try again."
    finally:
        conn.close()


def update_profile(user_id, display_name=None, email=None,
                   watchlist=None, alert_email=None, new_password=None,
                   current_password=None):
    """Update user profile fields. Returns (success, message)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    user_row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user_row:
        conn.close()
        return False, "User not found."

    updates = []
    params  = []

    if display_name and display_name != user_row["username"]:
        existing = c.execute("SELECT id FROM users WHERE username=? AND id!=?",
                             (display_name, user_id)).fetchone()
        if existing:
            conn.close()
            return False, "Username already taken."
        updates.append("username=?")
        params.append(display_name)
        updates.append("avatar_initials=?")
        params.append(display_name[:2].upper())

    if email and email != user_row["email"]:
        existing = c.execute("SELECT id FROM users WHERE email=? AND id!=?",
                             (email, user_id)).fetchone()
        if existing:
            conn.close()
            return False, "Email already registered."
        updates.append("email=?")
        params.append(email)

    if watchlist is not None:
        updates.append("watchlist=?")
        params.append(watchlist)

    if alert_email is not None:
        updates.append("alert_email=?")
        params.append(1 if alert_email else 0)

    if new_password:
        if not current_password:
            conn.close()
            return False, "Current password required to change password."
        if not check_password_hash(user_row["password_hash"], current_password):
            conn.close()
            return False, "Current password is incorrect."
        if len(new_password) < 6:
            conn.close()
            return False, "New password must be at least 6 characters."
        updates.append("password_hash=?")
        params.append(generate_password_hash(new_password))

    if updates:
        params.append(user_id)
        c.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=?", params)
        conn.commit()

    conn.close()
    return True, "Profile updated successfully."


def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id,username,email,role,created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


def get_user_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
    admins = c.fetchone()[0]
    conn.close()
    return {"total": total, "admins": admins, "regular": total - admins}
