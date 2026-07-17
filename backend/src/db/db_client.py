import psycopg2
from psycopg2 import pool

from src.config.settings import (
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME,
    DB_POOL_MIN, DB_POOL_MAX, DEFAULT_SESSION_NAME
)

db_pool = None


def init_db():
    global db_pool
    print("Connecting to PostgreSQL database...")
    try:
        # Create connection pool
        db_pool = pool.SimpleConnectionPool(
            DB_POOL_MIN, DB_POOL_MAX,
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )

        # Test connection and initialise relational schema
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                print("Connected to PostgreSQL successfully.")
                _init_users_schema(cur)
                _init_persistence_schema(cur)
            conn.commit()
        finally:
            db_pool.putconn(conn)

    except Exception as e:
        print(f"CRITICAL: Failed to initialize PostgreSQL pool: {e}")
        raise e


def _init_users_schema(cur):
    """
    Creates the users and user_sessions tables if they don't exist.
    Safe to run on every startup — uses IF NOT EXISTS.
    """
    # Enable pgcrypto for gen_random_uuid() — comes bundled with Postgres
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username      VARCHAR(100) UNIQUE NOT NULL,
            email         VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at    TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS user_sessions (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_name VARCHAR(255) DEFAULT '{DEFAULT_SESSION_NAME}',
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            expires_at   TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours'
        );
    """)

    print("PostgreSQL schema ready: users and user_sessions tables verified.")


def _init_persistence_schema(cur):
    """
    Creates chat_threads, chat_messages, user_documents, and thread_documents tables.
    """
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_threads (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title      VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id  UUID NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
            role       VARCHAR(50) NOT NULL,
            content    TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_documents (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            filename     VARCHAR(255) NOT NULL,
            category     VARCHAR(100) DEFAULT 'General',
            pages_count  INT NOT NULL DEFAULT 0,
            chunks_count INT NOT NULL DEFAULT 0,
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT unique_user_filename UNIQUE (user_id, filename)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS thread_documents (
            thread_id   UUID NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
            document_id UUID NOT NULL REFERENCES user_documents(id) ON DELETE CASCADE,
            PRIMARY KEY (thread_id, document_id)
        );
    """)

    print("PostgreSQL persistence schema verified: chat_threads, chat_messages, user_documents, and thread_documents ready.")


def get_db_connection():
    if not db_pool:
        raise Exception("Database connection pool has not been initialized.")
    return db_pool.getconn()


def release_db_connection(conn):
    if db_pool and conn:
        db_pool.putconn(conn)
