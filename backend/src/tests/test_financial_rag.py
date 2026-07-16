import sys
import os
import requests

# Add backend directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.utils.financial_parser import detect_financial_metadata
from src.config.settings import DEFAULT_SESSION_NAME

API_URL = "http://127.0.0.1:3000"

def test_metadata_auto_detection():
    print("\n--- Testing Metadata Auto-Detection ---")
    
    test_cases = [
        ("TSLA-Q3-2024.pdf", "UNITED STATES SECURITIES AND EXCHANGE COMMISSION FORM 10-Q", 2024, "Q3"),
        ("Apple_FY25_Annual.pdf", "FORM 10-K ANNUAL REPORT", 2025, "FY"),
        ("Google_Q2_24.pdf", "For the quarterly period ended June 30, 2024 Form 10-Q", 2024, "Q2"),
        ("General_Documentation.pdf", "This is some random documentation about software.", None, None)
    ]
    
    for filename, text, expected_year, expected_q in test_cases:
        year, q = detect_financial_metadata(filename, text)
        print(f"File: {filename} -> Detected: Year={year}, Quarter={q}")
        assert year == expected_year, f"Expected year {expected_year}, got {year}"
        assert q == expected_q, f"Expected quarter {expected_q}, got {q}"
        
    print("[PASS] Metadata auto-detection works perfectly.")


def test_financial_search_filtering():
    print("\n--- Testing Financial Search Metadata Scoping ---")
    
    # 1. Register a test user
    email = "fin_tester@example.com"
    password = "secure_password"
    username = "fintester"
    
    reg_resp = requests.post(
        f"{API_URL}/api/auth/register",
        json={"username": username, "email": email, "password": password}
    )
    if reg_resp.status_code == 409:
        # User already exists, log in
        login_resp = requests.post(
            f"{API_URL}/api/auth/login",
            json={"email": email, "password": password}
        )
        token = login_resp.json()["token"]
    else:
        assert reg_resp.status_code == 201
        token = reg_resp.json()["token"]
        
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Ingest two documents under different years/quarters
    print("Ingesting test document 1 (2024, Q2)...")
    ingest1 = requests.post(
        f"{API_URL}/api/ingest",
        json={
            "content": "Tesla delivered 443,956 vehicles in Q2 2024.",
            "metadata": {"title": "Tesla Q2 24 Report", "category": "Automotive"},
            "strategy": "fixed-size",
            "fiscalYear": 2024,
            "quarter": "Q2"
        },
        headers=headers
    )
    assert ingest1.status_code == 200, f"Ingestion 1 failed: {ingest1.text}"

    print("Ingesting test document 2 (2025, Q1)...")
    ingest2 = requests.post(
        f"{API_URL}/api/ingest",
        json={
            "content": "Tesla delivered 512,000 vehicles in Q1 2025.",
            "metadata": {"title": "Tesla Q1 25 Report", "category": "Automotive"},
            "strategy": "fixed-size",
            "fiscalYear": 2025,
            "quarter": "Q1"
        },
        headers=headers
    )
    assert ingest2.status_code == 200, f"Ingestion 2 failed: {ingest2.text}"

    # 3. Test filter queries
    print("Querying with filter Year=2024...")
    search_2024 = requests.post(
        f"{API_URL}/api/search",
        json={
            "query": "delivered vehicles",
            "fiscalYear": 2024
        },
        headers=headers
    )
    assert search_2024.status_code == 200
    results = search_2024.json()["results"]
    print(f"Results for Year=2024 count: {len(results)}")
    for r in results:
        print(f" - {r['content']} | Metadata: Year={r['metadata'].get('fiscal_year')}, Q={r['metadata'].get('quarter')}")
        assert r['metadata'].get('fiscal_year') == 2024

    print("Querying with filter Quarter=Q1...")
    search_q1 = requests.post(
        f"{API_URL}/api/search",
        json={
            "query": "delivered vehicles",
            "quarter": "Q1"
        },
        headers=headers
    )
    assert search_q1.status_code == 200
    results = search_q1.json()["results"]
    print(f"Results for Quarter=Q1 count: {len(results)}")
    for r in results:
        print(f" - {r['content']} | Metadata: Year={r['metadata'].get('fiscal_year')}, Q={r['metadata'].get('quarter')}")
        assert r['metadata'].get('quarter') == "Q1"

    print("[PASS] Financial filtering works flawlessly!")


if __name__ == "__main__":
    try:
        test_metadata_auto_detection()
        test_financial_search_filtering()
        print("\nAll financial RAG tests passed successfully!")
    except Exception as e:
        print(f"\n[FAIL] Financial RAG tests failed: {e}")
        sys.exit(1)
