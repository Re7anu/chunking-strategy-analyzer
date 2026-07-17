import sys
import os
import json

# Add backend directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.db.db_client import init_db, get_db_connection, release_db_connection
from main import run_hybrid_search

def main():
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get the latest user and session
    cur.execute("SELECT user_id, id, session_name FROM user_sessions ORDER BY created_at DESC LIMIT 1;")
    row = cur.fetchone()
    release_db_connection(conn)
    
    if not row:
        print("No active user sessions found.")
        return
        
    user_id, session_id, session_name = row
    print(f"Latest Session: {session_name} | User ID: {user_id} | Session ID: {session_id}")
    
    query = "What was YouTube's advertising revenue in Q3 2024 and how does it compare to Q3 2023?"
    print(f"Running hybrid search for query: '{query}'")
    
    results = run_hybrid_search(
        query=query,
        user_id=str(user_id),
        session_id=str(session_id),
        strategy="all",
        limit=15
    )
    
    print(f"\nRetrieved {len(results)} chunks:")
    table_found = False
    for idx, r in enumerate(results):
        content = r['content']
        strat = r['metadata'].get('strategy', 'unknown')
        page = r['metadata'].get('page', 'unknown')
        
        # Check if table numbers are present
        has_numbers = "8,921" in content or "7,952" in content
        indicator = " [CONTAINS TABLE NUMBERS]" if has_numbers else ""
        if has_numbers:
            table_found = True
            
        print(f"\n--- Rank #{idx+1} | Strategy: {strat} | Page: {page}{indicator} ---")
        print(content[:300].replace("\n", " ") + "...")
        
    if table_found:
        print("\n[SUCCESS] The target table chunk is indeed in the retrieved context!")
    else:
        print("\n[FAILURE] The target table chunk was NOT retrieved in the top 15 results.")

if __name__ == "__main__":
    main()
