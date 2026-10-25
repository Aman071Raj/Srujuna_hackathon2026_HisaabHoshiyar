"""Quick smoke-test: load db_service and verify Supabase connectivity."""
import os
import sys
import time

base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HisaabHoshiyaar")
sys.path.insert(0, base)
os.chdir(base)

from dotenv import load_dotenv
load_dotenv(r"e:\HisaabHoshiyaar\HisaabHoshiyaar\.env")

t0 = time.time()
print("Loading db_service …")
import db_service as dbs
print(f"  db_manager.provider  : {dbs.db_manager.provider}")
print(f"  db_manager.is_supabase: {dbs.db_manager.is_supabase}")
print(f"  db_manager._connected : {dbs.db_manager._connected}")
print(f"  Load time: {time.time()-t0:.2f}s")

if dbs.db_manager.is_supabase:
    print("\nFetching customers from Supabase …")
    cust = dbs.db_manager.get_customers_dict()
    print(f"  Customers fetched: {len(cust)}")
    for cid, (name, email, phone, hist) in cust.items():
        print(f"    {cid}: {name} | history={hist}")

    print("\nFetching transactions from Supabase …")
    df = dbs.db_manager.get_transactions_df()
    print(f"  Transactions fetched: {len(df)}")
    print(df[["id","name","type","dir","amount","status"]].to_string())

    print("\nDB status:")
    import json
    print(json.dumps(dbs.db_manager.get_status(), indent=2))
else:
    print("\nNot connected to Supabase — running in SQLite mode.")
    cust = dbs.db_manager.get_customers_dict()
    print(f"  SQLite customers: {len(cust)}")
    df = dbs.db_manager.get_transactions_df()
    print(f"  SQLite transactions: {len(df)}")

print("\nDone.")
