"""
Phase 2 Auth System Test Suite
Runs against the live Docker container at http://localhost:3000.
Execute: python backend/src/tests/test_auth_apis.py
"""
import sys
import json
import uuid
import requests

BASE = "http://localhost:3000"
PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"

errors = []

def check(label: str, condition: bool, detail: str = ""):
    if condition:
        print(f"{PASS} {label}")
    else:
        msg = f"{FAIL} {label}" + (f" — {detail}" if detail else "")
        print(msg)
        errors.append(label)

def post(path, body=None, token=None, form=False):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form:
        return requests.post(f"{BASE}{path}", data=body, headers=headers)
    return requests.post(f"{BASE}{path}", json=body, headers=headers)

def get(path, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.get(f"{BASE}{path}", headers=headers)


# Use a unique email per run so tests are idempotent
unique = uuid.uuid4().hex[:8]
email = f"testuser_{unique}@example.com"
username = f"testuser_{unique}"
password = "TestPassword123!"
token = None
user_id = None
session_id = None


print("\n=== Phase 2: Auth API Tests ===\n")

# ── 1. Register ────────────────────────────────────────────────────────────────
r = post("/api/auth/register", {
    "username": username,
    "email": email,
    "password": password,
    "session_name": "Test Session"
})
check("Register — HTTP 201", r.status_code == 201, f"got {r.status_code}: {r.text[:200]}")
if r.status_code == 201:
    data = r.json()
    token = data.get("token")
    user_id = data.get("user_id")
    session_id = data.get("session_id")
    check("Register — returns token", bool(token))
    check("Register — returns user_id", bool(user_id))
    check("Register — returns session_id", bool(session_id))

# ── 2. Duplicate registration ──────────────────────────────────────────────────
r = post("/api/auth/register", {"username": username, "email": email, "password": password})
check("Duplicate Register — HTTP 409", r.status_code == 409, f"got {r.status_code}")

# ── 3. /api/auth/me ────────────────────────────────────────────────────────────
r = get("/api/auth/me", token=token)
check("/api/auth/me — HTTP 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")
if r.status_code == 200:
    me = r.json()
    check("/api/auth/me — correct email", me.get("email") == email)

# ── 4. Unauthenticated access blocked ─────────────────────────────────────────
r = post("/api/ingest", {"content": "test", "strategy": "fixed-size"})
check("Unauthenticated /api/ingest — HTTP 403 or 401", r.status_code in (401, 403), f"got {r.status_code}")

r = post("/api/search", {"query": "test"})
check("Unauthenticated /api/search — HTTP 403 or 401", r.status_code in (401, 403), f"got {r.status_code}")

r = post("/api/chat", {"question": "test"})
check("Unauthenticated /api/chat — HTTP 403 or 401", r.status_code in (401, 403), f"got {r.status_code}")

# ── 5. Authenticated ingest ────────────────────────────────────────────────────
r = post("/api/ingest", {
    "content": "Customer support agents should always greet the customer politely and verify their account before proceeding.",
    "strategy": "fixed-size",
    "metadata": {"title": "Auth Test Doc", "category": "Test"}
}, token=token)
check("Authenticated /api/ingest — HTTP 200", r.status_code == 200, f"got {r.status_code}: {r.text[:300]}")
if r.status_code == 200:
    check("Ingest — chunksIngested > 0", r.json().get("chunksIngested", 0) > 0)

# ── 6. Authenticated search ────────────────────────────────────────────────────
r = post("/api/search", {"query": "greet customer politely"}, token=token)
check("Authenticated /api/search — HTTP 200", r.status_code == 200, f"got {r.status_code}: {r.text[:300]}")

# ── 7. Login ───────────────────────────────────────────────────────────────────
r = post("/api/auth/login", {"email": email, "password": password, "session_name": "Login Session"})
check("Login — HTTP 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")
login_token = None
if r.status_code == 200:
    login_token = r.json().get("token")
    check("Login — returns fresh token", bool(login_token))

# ── 8. Wrong password ─────────────────────────────────────────────────────────
r = post("/api/auth/login", {"email": email, "password": "WrongPassword!"})
check("Wrong password — HTTP 401", r.status_code == 401, f"got {r.status_code}")

# ── 9. Logout ──────────────────────────────────────────────────────────────────
r = post("/api/auth/logout", token=token)
check("Logout — HTTP 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")

# ── 10. Token unusable after logout ───────────────────────────────────────────
r = post("/api/search", {"query": "test"}, token=token)
check("Revoked token rejected — HTTP 401", r.status_code == 401, f"got {r.status_code}")


# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n{'='*40}")
if errors:
    print(f"\033[91m{len(errors)} test(s) FAILED:\033[0m")
    for e in errors:
        print(f"  • {e}")
    sys.exit(1)
else:
    print(f"\033[92mAll tests passed!\033[0m")
    sys.exit(0)
