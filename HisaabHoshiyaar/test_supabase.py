"""Unit and Mock Tests for Supabase Integration in HisaabHoshiyaar.
Verifies:
1. SQLite fallback behavior when Supabase credentials are not set
2. Data structure consistency between Supabase and SQLite
3. Supabase PostgREST table operations (mocked Client)
4. API endpoints reporting database status
"""

import json
import os
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient
import pandas as pd

from main import app
from db_service import DatabaseManager, SEED_CUSTOMERS, SEED_TRANSACTIONS

client = TestClient(app)

def test_sqlite_fallback_mode():
    """Verify that when no Supabase credentials exist, SQLite acts as the robust fallback."""
    with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": "", "SUPABASE_SERVICE_ROLE_KEY": ""}):
        mgr = DatabaseManager()
        assert mgr.get_provider() == "sqlite"
        assert mgr.is_supabase is False

        # Check customers
        custs = mgr.get_customers_dict()
        assert len(custs) >= 5
        assert "kiran" in custs
        name, email, phone, hist = custs["kiran"]
        assert name == "Kiran Enterprises"
        assert isinstance(hist, list)

        # Check transactions
        df = mgr.get_transactions_df()
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 13
        assert "amount" in df.columns
        assert "status" in df.columns

        # Check status dictionary
        status = mgr.get_status()
        assert status["provider"] == "sqlite"
        assert status["connected"] is True
        assert "counts" in status
        print("[PASS] SQLite fallback mode and data integrity verified")


def test_live_supabase_connection():
    """Verify live Supabase connection when environment variables are set."""
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        print("[SKIP] Live Supabase test skipped (credentials not in environment)")
        return

    mgr = DatabaseManager()
    assert mgr.is_supabase is True
    assert mgr.get_provider() == "supabase"

    custs = mgr.get_customers_dict()
    assert len(custs) >= 5
    tx_df = mgr.get_transactions_df()
    assert len(tx_df) >= 13
    print(f"[PASS] Live Supabase cloud verified: {len(custs)} customers, {len(tx_df)} transactions")


def test_supabase_mock_operations():
    """Verify DatabaseManager behaves correctly when connected to Supabase."""
    mgr = DatabaseManager()

    mock_supabase = MagicMock()
    mgr._rest_client = None
    mgr.supabase_client = mock_supabase
    mgr.provider = "supabase"

    # 1. Test get_customers_dict with both list and string json history
    mock_cust_table = MagicMock()
    mock_supabase.table.return_value = mock_cust_table
    mock_select = MagicMock()
    mock_cust_table.select.return_value = mock_select
    mock_select.limit.return_value = mock_select
    mock_select.execute.return_value = MagicMock(data=[
        {
            "id": "c_cloud_1",
            "name": "Cloud Customer 1",
            "email": "c1@cloud.example",
            "phone": "+919999999991",
            "history": [2, 0, 1]
        },
        {
            "id": "c_cloud_2",
            "name": "Cloud Customer 2",
            "email": "c2@cloud.example",
            "phone": "+919999999992",
            "history": "[5, 10, 12]" # JSON string representation
        }
    ])

    cust_dict = mgr.get_customers_dict()
    assert len(cust_dict) == 2
    assert cust_dict["c_cloud_1"][3] == [2, 0, 1]
    assert cust_dict["c_cloud_2"][3] == [5, 10, 12]
    print("[PASS] Supabase get_customers_dict properly parses both jsonb and string histories")

    # 2. Test get_transactions_df
    mock_tx_table = MagicMock()
    mock_supabase.table.return_value = mock_tx_table
    mock_tx_select = MagicMock()
    mock_tx_table.select.return_value = mock_tx_select
    mock_tx_select.limit.return_value = mock_tx_select
    mock_tx_select.execute.return_value = MagicMock(data=[
        {
            "id": "tx_cloud_1",
            "name": "Cloud Sale",
            "cust": "c_cloud_1",
            "type": "customer",
            "dir": "in",
            "amount": "50000", # string from API converted to int
            "day": 10,
            "delay": 0,
            "status": "expected"
        }
    ])

    tx_df = mgr.get_transactions_df()
    assert len(tx_df) == 1
    assert tx_df.iloc[0]["id"] == "tx_cloud_1"
    assert tx_df.iloc[0]["amount"] == 50000
    assert isinstance(tx_df.iloc[0]["amount"], (int, pd.Series, pd.api.types.pandas_dtype("int64").type))
    print("[PASS] Supabase get_transactions_df outputs properly typed pandas DataFrame")

    # 3. Test add_transaction
    mock_tx_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "tx_new"}])
    res_add = mgr.add_transaction("tx_new", "Test", "c_cloud_1", "customer", "in", 20000, 5, 0, "expected")
    assert res_add is True
    mock_tx_table.insert.assert_called()
    print("[PASS] Supabase add_transaction calls table insert")

    # 4. Test update_transaction_status
    mock_update = MagicMock()
    mock_tx_table.update.return_value = mock_update
    mock_eq = MagicMock()
    mock_update.eq.return_value = mock_eq
    mock_eq.execute.return_value = MagicMock(data=[{"id": "tx_new", "status": "settled"}])
    res_up = mgr.update_transaction_status("tx_new", "settled")
    assert res_up is True
    mock_tx_table.update.assert_called_with({"status": "settled"})
    print("[PASS] Supabase update_transaction_status calls table update")

    # 5. Test delete_transaction
    mock_delete = MagicMock()
    mock_tx_table.delete.return_value = mock_delete
    mock_del_eq = MagicMock()
    mock_delete.eq.return_value = mock_del_eq
    mock_del_eq.execute.return_value = MagicMock(data=[{"id": "tx_new"}])
    res_del = mgr.delete_transaction("tx_new")
    assert res_del is True
    print("[PASS] Supabase delete_transaction calls table delete")

    # 6. Test sync_sqlite_to_supabase
    mock_upsert = MagicMock()
    mock_cust_table.upsert.return_value = mock_upsert
    mock_upsert.execute.return_value = MagicMock()
    mock_tx_table.upsert.return_value = mock_upsert
    sync_res = mgr.sync_sqlite_to_supabase()
    assert sync_res["ok"] is True
    assert sync_res["synced_customers"] >= 5
    assert sync_res["synced_transactions"] >= 13
    print(f"[PASS] Supabase sync_sqlite_to_supabase successfully synced {sync_res['synced_transactions']} transactions")


def test_api_status_database_metadata():
    """Verify that /api/status and /api/db/status return database information."""
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "database" in data
    assert "database_connected" in data
    assert "supabase_enabled" in data
    print(f"[PASS] /api/status reports database: {data['database']} (connected: {data['database_connected']})")

    res_db = client.get("/api/db/status")
    assert res_db.status_code == 200
    db_data = res_db.json()
    assert "provider" in db_data
    assert "counts" in db_data
    assert db_data["counts"]["transactions"] >= 13
    print(f"[PASS] /api/db/status returns complete database telemetry: {db_data['counts']}")


if __name__ == "__main__":
    print("\nRunning Supabase Integration Test Suite...")
    test_sqlite_fallback_mode()
    test_live_supabase_connection()
    test_supabase_mock_operations()
    test_api_status_database_metadata()
    print("\n==========================================")
    print("ALL SUPABASE INTEGRATION TESTS PASSED!   ")
    print("==========================================")
