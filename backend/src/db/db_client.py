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


def get_db_connection():
    if not db_pool:
        raise Exception("Database connection pool has not been initialized.")
    return db_pool.getconn()


def release_db_connection(conn):
    if db_pool and conn:
        db_pool.putconn(conn)
