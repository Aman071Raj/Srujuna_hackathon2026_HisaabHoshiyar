"""Test raw network connectivity - using urllib instead of httpx."""
import os
import urllib.request
import urllib.error
import json

from dotenv import load_dotenv
load_dotenv(r"e:\HisaabHoshiyaar\HisaabHoshiyaar\.env")

url = os.getenv("SUPABASE_URL", "")
key = os.getenv("SUPABASE_KEY", "")
print(f"URL: {url}")
print(f"Key prefix: {key[:20]}")

# Test with urllib (no httpx)
req_url = url + "/rest/v1/customers?select=id&limit=1"
req = urllib.request.Request(
    req_url,
    headers={"apikey": key, "Content-Type": "application/json"},
)
print(f"\nRequesting: {req_url}")
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        print(f"Status: {resp.status}")
        print(f"Response: {body[:300]}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTP Error {e.code}: {body[:300]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
