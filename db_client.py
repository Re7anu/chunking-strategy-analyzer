import os
import time
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()

from settings import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

db_pool = None

def init_db():
    global db_pool
    print("Connecting to PostgreSQL database...")
    try:
        # Create connection pool
        db_pool = pool.SimpleConnectionPool(
            1, 20,
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        
        # Test connection & check tables
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                print("Connected to PostgreSQL successfully.")
                
                # Check if the analyzer_chunks table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM pg_tables 
                        WHERE schemaname = 'public' 
                        AND tablename = 'analyzer_chunks'
                    );
                """)
                exists = cur.fetchone()[0]
                
                if exists:
                    # Verify column vector dimension
                    try:
                        cur.execute("""
                            SELECT atttypmod 
                            FROM pg_attribute 
                            WHERE attrelid = 'analyzer_chunks'::regclass 
                              AND attname = 'embedding';
                        """)
                        row = cur.fetchone()
                        if row and row[0] != 384:
                            print(f"Database schema mismatch: Found vector dimension {row[0]}, expected 384. Dropping table for recreation...")
                            cur.execute("DROP TABLE IF EXISTS analyzer_chunks CASCADE;")
                            exists = False
                    except Exception as err:
                        print(f"Warning: Failed to check vector dimension: {err}. Dropping table just in case.")
                        cur.execute("DROP TABLE IF EXISTS analyzer_chunks CASCADE;")
                        exists = False
                
                if not exists:
                    print("Table analyzer_chunks not found or dropped. Initializing from init.sql...")
                    sql_path = os.path.join(os.getcwd(), "init.sql")
                    if os.path.exists(sql_path):
                        with open(sql_path, "r", encoding="utf-8") as f:
                            sql = f.read()
                        cur.execute(sql)
                        conn.commit()
                        print("Database initialized successfully from init.sql.")
                    else:
                        print("init.sql not found! Attempting fallback creation in code...")
                        cur.execute("""
                            CREATE EXTENSION IF NOT EXISTS vector;
                            CREATE TABLE IF NOT EXISTS analyzer_chunks (
                                id SERIAL PRIMARY KEY,
                                content TEXT NOT NULL,
                                embedding VECTOR(384) NOT NULL,
                                fts_tokens TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
                                metadata JSONB,
                                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS analyzer_chunks_embedding_hnsw_idx ON analyzer_chunks USING hnsw (embedding vector_cosine_ops);
                            CREATE INDEX IF NOT EXISTS analyzer_chunks_fts_idx ON analyzer_chunks USING gin (fts_tokens);
                        """)
                        conn.commit()
                        print("Database fallback initialization completed.")
                else:
                    print("Database already initialized and dimensions match. Table analyzer_chunks ready.")
        finally:
            db_pool.putconn(conn)
            
    except Exception as e:
        print(f"CRITICAL: Failed to initialize PostgreSQL pool: {e}")
        raise e

def get_db_connection():
    if not db_pool:
        raise Exception("Database connection pool has not been initialized.")
    return db_pool.getconn()

def release_db_connection(conn):
    if db_pool and conn:
        db_pool.putconn(conn)
