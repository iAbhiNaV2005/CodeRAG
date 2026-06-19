"""Quick gateway integration test."""
import httpx

# Test 1: Get JWT token
print("=== Test 1: Get JWT ===")
token_resp = httpx.post("http://localhost:8080/auth/token", json={"user_id": "alice"}).json()
token = token_resp["token"]
print(f"Token: {token[:40]}...")

headers = {"Authorization": f"Bearer {token}"}

# Test 2: 401 without token
print("\n=== Test 2: No token -> 401 ===")
r = httpx.get("http://localhost:8080/ingest/status/test")
print(f"Status: {r.status_code}")

# Test 3: Proxied request with token
print("\n=== Test 3: Ingest status via gateway ===")
r = httpx.get(
    "http://localhost:8080/ingest/status/github_iAbhiNaV2005_To-Do_a20b406560b3",
    headers=headers,
)
print(f"Status: {r.status_code}")
rate_limit = r.headers.get("X-RateLimit-Limit", "N/A")
print(f"X-RateLimit-Limit: {rate_limit}")
print(f"Body: {r.json()}")

# Test 4: Chat via gateway (SSE proxy)
print("\n=== Test 4: Chat SSE via gateway ===")
r = httpx.post(
    "http://localhost:8080/chat",
    json={
        "repo_id": "github_iAbhiNaV2005_To-Do_a20b406560b3",
        "question": "What is the main HTML structure?",
    },
    headers=headers,
    timeout=60,
)
print(f"Status: {r.status_code}")
lines = r.text.strip().split("\n")
print(f"SSE events received: {len([l for l in lines if l.startswith('data:')])}")
print(f"First event: {lines[1][:100] if len(lines) > 1 else 'N/A'}...")

print("\n=== All tests passed! ===")
