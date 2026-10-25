"""CLI tool to migrate HisaabHoshiyaar SQLite database to Supabase Cloud.

Usage:
    python migrate_to_supabase.py
"""

import os
import sys
from dotenv import load_dotenv

# Ensure HisaabHoshiyaar directory is in path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.join(os.path.dirname(BASE_DIR), ".env"))
load_dotenv()

from db_service import db_manager

def main():
    print("==================================================")
    print("  HisaabHoshiyaar - Supabase Cloud Migration Tool ")
    print("==================================================")

    url = os.getenv("SUPABASE_URL", "").strip()
    if url:
        url = url.rstrip("/")
        if url.endswith("/rest/v1"):
            url = url[:-8].rstrip("/")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_KEY", "").strip()
        or os.getenv("SUPABASE_ANON_KEY", "").strip()
    )

    if not url or not key:
        print("\n[ERROR] SUPABASE_URL or SUPABASE_KEY is missing!")
        print("Please configure your credentials in HisaabHoshiyaar/.env:")
        print("  SUPABASE_URL=https://<your-project-ref>.supabase.co")
        print("  SUPABASE_KEY=<your-anon-or-service-role-key>\n")
        sys.exit(1)

    print(f"Target Supabase URL: {url}")
    print(f"Source SQLite DB   : {db_manager.get_status()['sqlite_path']}")

    if not db_manager.is_supabase:
        print("\nAttempting connection to Supabase...")
        try:
            from supabase import create_client
            client = create_client(url, key)
            db_manager.supabase_client = client
            db_manager.provider = "supabase"
            print("[OK] Supabase connection established successfully.")
        except Exception as e:
            print(f"[FAIL] Failed to connect to Supabase: {e}")
            sys.exit(1)

    print("\nStarting data migration...")
    try:
        res = db_manager.sync_sqlite_to_supabase()
        print("\n Migration Completed Successfully!")
        print(f"  - Customers Synced   : {res['synced_customers']}")
        print(f"  - Transactions Synced: {res['synced_transactions']}")
        print(f"  - Comms Log Synced   : {res['synced_comms']}")
        print("\nYour HisaabHoshiyaar backend is now fully synchronized with Supabase Cloud!")
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        print("Tip: Make sure you have executed 'supabase_schema.sql' in your Supabase SQL Editor.")
        sys.exit(1)

if __name__ == "__main__":
    main()
