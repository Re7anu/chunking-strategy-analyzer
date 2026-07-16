"""
Pure PostgreSQL query functions for users and sessions.
No business logic — that lives in auth/router.py.
"""
from src.db.db_client import get_db_connection, release_db_connection


def _row_to_dict(cursor, row) -> dict:
    """Converts a psycopg2 row tuple into a column-keyed dict."""
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))


# ─── Users ────────────────────────────────────────────────────────────────────

def create_user(username: str, email: str, password_hash: str) -> dict:
    """Inserts a new user and returns the full user row."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (username, email, password_hash)
                VALUES (%s, %s, %s)
                RETURNING id, username, email, created_at;
                """,
                (username, email, password_hash)
            )
            row = cur.fetchone()
            conn.commit()
            return _row_to_dict(cur, row)
    finally:
        release_db_connection(conn)


def get_user_by_email(email: str) -> dict | None:
    """Fetches a user row by email. Returns None if not found."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, email, password_hash, created_at FROM users WHERE email = %s;",
                (email,)
            )
            row = cur.fetchone()
            return _row_to_dict(cur, row) if row else None
    finally:
        release_db_connection(conn)


def get_user_by_id(user_id: str) -> dict | None:
    """Fetches a user row by UUID. Returns None if not found."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, email, created_at FROM users WHERE id = %s;",
                (user_id,)
            )
            row = cur.fetchone()
            return _row_to_dict(cur, row) if row else None
    finally:
        release_db_connection(conn)


# ─── Sessions ─────────────────────────────────────────────────────────────────

def create_session(user_id: str, session_name: str = "Default Session") -> dict:
    """Creates a new session for the user and returns the session row."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_sessions (user_id, session_name)
                VALUES (%s, %s)
                RETURNING id, user_id, session_name, created_at, expires_at;
                """,
                (str(user_id), session_name)
            )
            row = cur.fetchone()
            conn.commit()
            return _row_to_dict(cur, row)
    finally:
        release_db_connection(conn)


def get_session(session_id: str) -> dict | None:
    """
    Fetches a session row. Returns None if not found OR if already expired,
    which is what allows server-side token revocation via logout.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, session_name, created_at, expires_at
                FROM user_sessions
                WHERE id = %s AND expires_at > NOW();
                """,
                (str(session_id),)
            )
            row = cur.fetchone()
            return _row_to_dict(cur, row) if row else None
    finally:
        release_db_connection(conn)


def delete_session(session_id: str) -> None:
    """Deletes a session row, invalidating the associated token server-side."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_sessions WHERE id = %s;",
                (str(session_id),)
            )
            conn.commit()
    finally:
        release_db_connection(conn)
