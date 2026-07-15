import requests
import os
import json

def test_python_api():
    print("--- STARTING PYTHON API VERIFICATION ---")
    url_ingest = "http://localhost:3000/api/ingest"
    url_search = "http://localhost:3000/api/search"
    url_compare = "http://localhost:3000/api/compare"
    
    # 1. Test raw text ingestion
    payload = {
        "content": "Satoshi Nakamoto published the Bitcoin whitepaper in 2008. It described a peer-to-peer electronic cash system that solves the double-spending problem.",
        "metadata": {"title": "Bitcoin Abstract", "category": "Crypto"},
        "strategy": "fixed-size",
        "chunkSize": 100,
        "chunkOverlap": 10
    }
    
    print("Testing Ingest API...")
    r_ingest = requests.post(url_ingest, json=payload)
    print(f"Ingest status: {r_ingest.status_code}")
    print(f"Ingest response: {r_ingest.json()}")
    assert r_ingest.status_code == 200, "Ingest failed"
    
    # 2. Test search
    search_payload = {
        "query": "Satoshi Nakamoto",
        "strategy": "fixed-size"
    }
    print("\nTesting Search API...")
    r_search = requests.post(url_search, json=search_payload)
    print(f"Search status: {r_search.status_code}")
    search_res = r_search.json()
    print(f"Search results count: {len(search_res['results'])}")
    assert r_search.status_code == 200, "Search failed"
    
    # 3. Test compare
    compare_payload = {
        "query": "electronic cash system"
    }
    print("\nTesting Compare API...")
    r_compare = requests.post(url_compare, json=compare_payload)
    print(f"Compare status: {r_compare.status_code}")
    compare_res = r_compare.json()
    assert r_compare.status_code == 200, "Compare failed"
    print("Compare strategies in response:", [c["strategy"] for c in compare_res['comparisons']])
    
    # 4. Test PDF ingestion
    if os.path.exists("test.pdf"):
        print("\nTesting PDF Ingestion API with test.pdf...")
        url_pdf = "http://localhost:3000/api/ingest-pdf"
        with open("test.pdf", "rb") as f:
            files = {"file": ("test.pdf", f, "application/pdf")}
            data = {
                "title": "Bitcoin Whitepaper Proof",
                "category": "Crypto",
                "strategy": "fixed-size",
                "chunkSize": "1000",
                "chunkOverlap": "200",
                "ingestAllStrategies": "true"
            }
            r_pdf = requests.post(url_pdf, files=files, data=data)
        print(f"PDF Ingest status: {r_pdf.status_code}")
        print(f"PDF Ingest response: {r_pdf.json()}")
        assert r_pdf.status_code == 200, "PDF Ingest failed"

    print("\n--- ALL PYTHON ENDPOINT VERIFICATIONS PASSED ---")

if __name__ == "__main__":
    test_python_api()
