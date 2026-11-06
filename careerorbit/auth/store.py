"""Argon2 authentication, opaque revocable sessions, and account registry.

The auth database only contains authentication metadata. Each account's
application records live in an isolated data directory and SQLite database.
The first registered account owns the existing legacy data directory.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from careerorbit.config.settings import SETTINGS

SESSION_TTL = timedelta(hours=12)
LOGIN_WINDOW = timedelta(minutes=15)
MAX_FAILED_LOGINS = 6
COOKIE_NAME = "careerorbit_session"
CSRF_COOKIE_NAME = "careerorbit_csrf"
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    email: str
    display_name: str
    storage_key: str

    def public_dict(self) -> dict[str, str]:
        return {
            "id": self.user_id,
            "email": self.email,
            "display_name": self.display_name,
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _auth_db_path() -> Path:
    return SETTINGS.DATA_DIR / "auth.db"


def _connect() -> sqlite3.Connection:
    path = _auth_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_auth_store() -> None:
    """Apply an idempotent versioned migration to the separate auth database."""
    path = _auth_db_path()
    existed = path.exists() and path.stat().st_size > 0
    conn = _connect()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version=?",
            ("2026-10-26-auth-sessions-v1",),
        ).fetchone()
        if applied:
            return
        if existed:
            backup = path.with_name(f"auth_pre_migration_{_now():%Y%m%d_%H%M%S}.db")
            with sqlite3.connect(backup) as backup_conn:
                conn.backup(backup_conn)
        with conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    storage_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1))
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_hash TEXT NOT NULL UNIQUE,
                    csrf_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user_expiry
                    ON sessions(user_id, expires_at);
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_hash TEXT NOT NULL,
                    ip_hash TEXT NOT NULL,
                    attempted_at TEXT NOT NULL,
                    succeeded INTEGER NOT NULL DEFAULT 0 CHECK(succeeded IN (0,1))
                );
                CREATE INDEX IF NOT EXISTS idx_login_attempts_window
                    ON login_attempts(email_hash, ip_hash, attempted_at);
                INSERT INTO schema_migrations(version, applied_at)
                    VALUES ('2026-10-26-auth-sessions-v1', CURRENT_TIMESTAMP);
                """
            )
        conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.close()


def setup_required() -> bool:
    init_auth_store()
    with _connect() as conn:
        return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is None


def _normalize_email(email: str) -> str:
    normalized = (email or "").strip().casefold()
    if len(normalized) > 254 or normalized.count("@") != 1:
        raise ValueError("Enter a valid email address.")
    local, domain = normalized.split("@", 1)
    if not local or not domain or "." not in domain or any(ch.isspace() for ch in normalized):
        raise ValueError("Enter a valid email address.")
    return normalized


def _validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    if len(password) > 256:
        raise ValueError("Password is too long.")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def account_data_dir(user: AuthUser) -> Path:
    if user.storage_key == "legacy":
        return SETTINGS.DATA_DIR
    return SETTINGS.DATA_DIR / "accounts" / user.storage_key


def _row_to_user(row: sqlite3.Row) -> AuthUser:
    return AuthUser(
        user_id=str(row["id"]),
        email=str(row["email"]),
        display_name=str(row["display_name"]),
        storage_key=str(row["storage_key"]),
    )


def get_user(user_id: str) -> AuthUser | None:
    init_auth_store()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id,email,display_name,storage_key FROM users WHERE id=? AND disabled=0",
            (user_id,),
        ).fetchone()
    return _row_to_user(row) if row else None


def _create_session(user_id: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = _now()
    with _connect() as conn, conn:
        conn.execute(
            "INSERT INTO sessions(user_id,token_hash,csrf_hash,created_at,last_seen_at,expires_at) "
            "VALUES(?,?,?,?,?,?)",
            (user_id, _digest(token), _digest(csrf_token), _iso(now), _iso(now), _iso(now + SESSION_TTL)),
        )
    return token, csrf_token


def _initialize_account_storage(user: AuthUser) -> None:
    """Initialize only the new account's application database, never copy another account."""
    if user.storage_key == "legacy" and (SETTINGS.DATA_DIR / "careerorbit.db").exists():
        return
    root = account_data_dir(user)
    root.mkdir(parents=True, exist_ok=True)
    from careerorbit.config.settings import account_storage_context
    from careerorbit.database.db import init_db
    from careerorbit.config.profile import candidate_profile_context

    with account_storage_context(root), candidate_profile_context(root):
        init_db()


def register_user(email: str, password: str, display_name: str, ip_address: str = "local") -> tuple[AuthUser, str, str]:
    init_auth_store()
    normalized_email = _normalize_email(email)
    _validate_password(password)
    name = (display_name or "").strip()
    if not name or len(name) > 120:
        raise ValueError("Enter a display name no longer than 120 characters.")
    user_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        first_user = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is None
        storage_key = "legacy" if first_user else uuid.uuid4().hex
        try:
            conn.execute(
                "INSERT INTO users(id,email,display_name,password_hash,storage_key,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (user_id, normalized_email, name, PASSWORD_HASHER.hash(password), storage_key, _iso(_now())),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("An account with that email already exists.") from exc
    user = AuthUser(user_id, normalized_email, name, storage_key)
    try:
        _initialize_account_storage(user)
    except Exception:
        with _connect() as conn, conn:
            conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        raise
    token, csrf = _create_session(user_id)
    return user, token, csrf


def authenticate(email: str, password: str, ip_address: str = "local") -> tuple[AuthUser, str, str] | None:
    init_auth_store()
    try:
        normalized = _normalize_email(email)
    except ValueError:
        normalized = (email or "").strip().casefold()[:254]
    email_hash, ip_hash = _digest(normalized), _digest(ip_address or "local")
    now = _now()
    with _connect() as conn:
        recent = conn.execute(
            "SELECT count(*) FROM login_attempts WHERE email_hash=? AND ip_hash=? AND succeeded=0 AND attempted_at>=?",
            (email_hash, ip_hash, _iso(now - LOGIN_WINDOW)),
        ).fetchone()[0]
        row = conn.execute(
            "SELECT id,email,display_name,password_hash,storage_key,disabled FROM users WHERE email=? COLLATE NOCASE",
            (normalized,),
        ).fetchone()
    if recent >= MAX_FAILED_LOGINS:
        return None
    valid = False
    if row and not row["disabled"]:
        try:
            valid = PASSWORD_HASHER.verify(row["password_hash"], password)
        except (VerifyMismatchError, VerificationError, InvalidHashError, TypeError):
            valid = False
    if not valid:
        with _connect() as conn, conn:
            conn.execute(
                "INSERT INTO login_attempts(email_hash,ip_hash,attempted_at,succeeded) VALUES(?,?,?,0)",
                (email_hash, ip_hash, _iso(now)),
            )
        return None
    if PASSWORD_HASHER.check_needs_rehash(row["password_hash"]):
        upgraded_hash = PASSWORD_HASHER.hash(password)
        with _connect() as conn, conn:
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (upgraded_hash, row["id"]))
    with _connect() as conn, conn:
        conn.execute("DELETE FROM login_attempts WHERE email_hash=? AND ip_hash=?", (email_hash, ip_hash))
    user = _row_to_user(row)
    _initialize_account_storage(user)
    token, csrf = _create_session(user.user_id)
    return user, token, csrf


def resolve_session(token: str | None) -> tuple[AuthUser, str] | None:
    if not token or len(token) > 256:
        return None
    init_auth_store()
    digest = _digest(token)
    now = _iso(_now())
    with _connect() as conn:
        row = conn.execute(
            "SELECT u.id,u.email,u.display_name,u.storage_key,s.csrf_hash,s.expires_at "
            "FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND u.disabled=0",
            (digest, now),
        ).fetchone()
    if not row:
        return None
    with _connect() as conn, conn:
        conn.execute("UPDATE sessions SET last_seen_at=? WHERE token_hash=?", (now, digest))
    return _row_to_user(row), str(row["csrf_hash"])


def valid_csrf(token: str | None, expected_hash: str) -> bool:
    return bool(token) and hmac.compare_digest(_digest(token), expected_hash)


def revoke_session(token: str | None) -> None:
    if not token or len(token) > 256:
        return
    init_auth_store()
    with _connect() as conn, conn:
        conn.execute(
            "UPDATE sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
            (_iso(_now()), _digest(token)),
        )


def revoke_user_sessions(user_id: str) -> None:
    init_auth_store()
    with _connect() as conn, conn:
        conn.execute(
            "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
            (_iso(_now()), user_id),
        )


def rotate_csrf_token(raw_session_token: str) -> str | None:
    """Rotate a session's CSRF secret without changing its session identifier."""
    if not raw_session_token or len(raw_session_token) > 256:
        return None
    init_auth_store()
    csrf = secrets.token_urlsafe(32)
    with _connect() as conn, conn:
        cursor = conn.execute(
            "UPDATE sessions SET csrf_hash=? WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?",
            (_digest(csrf), _digest(raw_session_token), _iso(_now())),
        )
    return csrf if cursor.rowcount == 1 else None
