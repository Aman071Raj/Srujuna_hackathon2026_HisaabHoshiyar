import os, sys
base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HisaabHoshiyaar")
sys.path.insert(0, base)
os.chdir(base)
from dotenv import load_dotenv
load_dotenv(os.path.join(base, ".env"))
url = os.getenv('SUPABASE_URL', '')
key = os.getenv('SUPABASE_KEY', '')
print('URL:', url)
print('KEY len:', len(key), 'KEY prefix:', key[:20] if key else 'NOT SET')
import httpx
try:
    r = httpx.get(url + '/rest/v1/customers?select=id&limit=1',
                  headers={'apikey': key, 'Authorization': 'Bearer ' + key},
                  timeout=10)
    print('HTTP status:', r.status_code)
    print('Response:', r.text[:200])
except Exception as e:
    print('HTTP request FAILED:', type(e).__name__, str(e)[:200])
