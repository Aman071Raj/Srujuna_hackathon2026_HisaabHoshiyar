"""Test raw network connectivity to Supabase."""
import os
from dotenv import load_dotenv
load_dotenv(r"e:\HisaabHoshiyaar\HisaabHoshiyaar\.env")

url = os.getenv("SUPABASE_URL", "")
key = os.getenv("SUPABASE_KEY", "")
print(f"URL: {url}")
print(f"Key prefix: {key[:20]}")

import httpx
print("\nTesting httpx connection with 8s timeout...")
try:
    r = httpx.get(
        url + "/rest/v1/customers",
        headers={
            "apikey": key,
            "Content-Type": "application/json",
        },
        params={"select": "id", "limit": "1"},
        timeout=8.0,
    )
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:300]}")
except httpx.TimeoutException as e:
    print(f"TIMEOUT: {e}")
except httpx.ConnectError as e:
    print(f"CONNECT ERROR: {e}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
