import uuid
from src.db.db_client import get_db_connection, release_db_connection

# ─── Chat Threads Store ────────────────────────────────────────────────────────

def get_user_threads(user_id: str) -> list[dict]:
    """
    Fetches all chat threads belonging to a user, ordered from most recent to oldest.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, created_at FROM chat_threads WHERE user_id = %s ORDER BY created_at DESC;",
                (user_id,)
            )
            rows = cur.fetchall()
            return [{"id": str(r[0]), "title": r[1], "createdAt": r[2].isoformat()} for r in rows]
    finally:
        release_db_connection(conn)


def create_chat_thread(user_id: str, title: str = "New Chat") -> dict:
    """
    Creates a new chat thread for the user.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_threads (user_id, title) VALUES (%s, %s) RETURNING id, title, created_at;",
                (user_id, title)
            )
            row = cur.fetchone()
            conn.commit()
            return {"id": str(row[0]), "title": row[1], "createdAt": row[2].isoformat()}
    finally:
        release_db_connection(conn)


def delete_chat_thread(user_id: str, thread_id: str) -> bool:
    """
    Deletes a specific chat thread belonging to the user.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM chat_threads WHERE id = %s AND user_id = %s RETURNING id;",
                (thread_id, user_id)
            )
            row = cur.fetchone()
            conn.commit()
            return row is not None
    finally:
        release_db_connection(conn)


def rename_chat_thread(user_id: str, thread_id: str, title: str) -> bool:
    """
    Renames a chat thread.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE chat_threads SET title = %s WHERE id = %s AND user_id = %s RETURNING id;",
                (title, thread_id, user_id)
            )
            row = cur.fetchone()
            conn.commit()
            return row is not None
    finally:
        release_db_connection(conn)


# ─── Chat Messages Store ───────────────────────────────────────────────────────

def get_thread_messages(thread_id: str) -> list[dict]:
    """
    Loads all messages in a thread, ordered chronologically.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content FROM chat_messages WHERE thread_id = %s ORDER BY created_at ASC;",
                (thread_id,)
            )
            rows = cur.fetchall()
            return [{"role": r[0], "content": r[1]} for r in rows]
    finally:
        release_db_connection(conn)


def save_chat_message(thread_id: str, role: str, content: str) -> dict:
    """
    Persists a single chat message (user or assistant response) into PostgreSQL.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_messages (thread_id, role, content) VALUES (%s, %s, %s) RETURNING id, created_at;",
                (thread_id, role, content)
            )
            row = cur.fetchone()
            conn.commit()
            return {"id": str(row[0]), "createdAt": row[1].isoformat()}
    finally:
        release_db_connection(conn)


# ─── User Documents Store ──────────────────────────────────────────────────────

def get_user_documents(user_id: str) -> list[dict]:
    """
    Lists all documents uploaded by the user.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, filename, category, pages_count, chunks_count, created_at FROM user_documents WHERE user_id = %s ORDER BY created_at DESC;",
                (user_id,)
            )
            rows = cur.fetchall()
            return [
                {
                    "id": str(r[0]),
                    "filename": r[1],
                    "category": r[2],
                    "pagesCount": r[3],
                    "chunksCount": r[4],
                    "createdAt": r[5].isoformat()
                }
                for r in rows
            ]
    finally:
        release_db_connection(conn)


def register_user_document(user_id: str, filename: str, category: str, pages_count: int, chunks_count: int) -> dict:
    """
    Registers or updates user document metadata in the database.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # ON CONFLICT update stats to support re-upload override
            cur.execute(
                """
                INSERT INTO user_documents (user_id, filename, category, pages_count, chunks_count)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, filename) DO UPDATE 
                SET category = EXCLUDED.category, pages_count = EXCLUDED.pages_count, chunks_count = EXCLUDED.chunks_count, created_at = NOW()
                RETURNING id, filename, category, pages_count, chunks_count;
                """,
                (user_id, filename, category, pages_count, chunks_count)
            )
            row = cur.fetchone()
            conn.commit()
            return {
                "id": str(row[0]),
                "filename": row[1],
                "category": row[2],
                "pagesCount": row[3],
                "chunksCount": row[4]
            }
    finally:
        release_db_connection(conn)


def get_document_by_id(document_id: str) -> dict:
    """
    Retrieves document info by ID.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, filename, category FROM user_documents WHERE id = %s;",
                (document_id,)
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": str(row[0]),
                    "userId": str(row[1]),
                    "filename": row[2],
                    "category": row[3]
                }
            return None
    finally:
        release_db_connection(conn)


# ─── Thread Documents (Attachments) Store ──────────────────────────────────────

def get_thread_documents(thread_id: str) -> list[dict]:
    """
    Gets all documents attached to a specific chat thread.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.id, d.filename, d.category, d.pages_count 
                FROM user_documents d
                JOIN thread_documents td ON d.id = td.document_id
                WHERE td.thread_id = %s;
                """,
                (thread_id,)
            )
            rows = cur.fetchall()
            return [
                {
                    "id": str(r[0]),
                    "filename": r[1],
                    "category": r[2],
                    "pagesCount": r[3]
                }
                for r in rows
            ]
    finally:
        release_db_connection(conn)


def attach_document_to_thread(thread_id: str, document_id: str) -> bool:
    """
    Associates a document with a chat thread.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO thread_documents (thread_id, document_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING thread_id;",
                (thread_id, document_id)
            )
            row = cur.fetchone()
            conn.commit()
            return True
    finally:
        release_db_connection(conn)


def detach_document_from_thread(thread_id: str, document_id: str) -> bool:
    """
    Removes the document association from the thread.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM thread_documents WHERE thread_id = %s AND document_id = %s RETURNING thread_id;",
                (thread_id, document_id)
            )
            row = cur.fetchone()
            conn.commit()
            return row is not None
    finally:
        release_db_connection(conn)
