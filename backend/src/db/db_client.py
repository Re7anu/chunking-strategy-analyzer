import os
import psycopg2
from psycopg2 import pool

from src.config.settings import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

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
                
                # Relational connection tested successfully
                pass
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
