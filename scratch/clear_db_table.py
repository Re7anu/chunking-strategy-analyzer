import sys
import os
sys.path.append(os.getcwd())

from db_client import init_db, get_db_connection, release_db_connection

def clear_table():
    init_db()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE analyzer_chunks;")
            conn.commit()
            print("Successfully truncated table analyzer_chunks!")
    finally:
        release_db_connection(conn)

if __name__ == "__main__":
    clear_table()
