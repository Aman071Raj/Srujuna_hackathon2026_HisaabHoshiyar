"""Comprehensive integration test suite for HisaabHoshiyaar FastAPI backend.
"""
import json
from starlette.testclient import TestClient
from main import app

client = TestClient(app)

def test_static_routes():
    res = client.get("/")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert "HisaabHoshiyaar" in res.text, "index.html content missing"
    print("[PASS] Static route '/' successfully serves index.html")

    res_css = client.get("/style.css")
    assert res_css.status_code == 200, f"Expected 200, got {res_css.status_code}"
    assert "color:var(--navy)" in res_css.text or "Inter" in res_css.text
    print("[PASS] Static route '/style.css' successfully serves style.css")

def test_api_status():
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.0.0"
    print("[PASS] /api/status endpoint works")

def test_api_overview():
    res = client.get("/api/overview")
    assert res.status_code == 200
    data = res.json()
    assert "weekly_balances" in data
    assert "metrics" in data
    assert len(data["weekly_balances"]) == 9  # week 0 to 8
    print("[PASS] /api/overview endpoint works")

def test_api_transactions():
    res = client.get("/api/transactions")
    assert res.status_code == 200
    txs = res.json()
    assert len(txs) >= 9
    print(f"[PASS] /api/transactions returned {len(txs)} transactions")

    # Test adding a transaction
    new_tx = {
        "name": "Integration Test Bill",
        "type": "expense",
        "dir": "out",
        "amount": 25000,
        "day": 12,
        "delay": 0,
        "status": "expected"
    }
    post_res = client.post("/api/transactions", json=new_tx)
    assert post_res.status_code == 200
    tx_id = post_res.json()["id"]
    print("[PASS] /api/transactions POST created transaction with id:", tx_id)

    # Clean up test transaction
    del_res = client.delete(f"/api/transactions/{tx_id}")
    assert del_res.status_code == 200
    print("[PASS] /api/transactions DELETE successfully cleaned up")

def test_api_customers_behaviour():
    res = client.get("/api/customers/behaviour")
    assert res.status_code == 200
    custs = res.json()
    assert len(custs) == 5
    for c in custs:
        assert "id" in c and "avg_delay" in c and "status" in c
    print(f"[PASS] /api/customers/behaviour verified {len(custs)} customers")

def test_api_health_score():
    res = client.get("/api/health-score")
    assert res.status_code == 200
    data = res.json()
    assert 0 <= data["score"] <= 100
    assert "comps" in data
    assert len(data["comps"]) == 6
    print(f"[PASS] /api/health-score works: Score {data['score']}/100 ({data['label']})")

def test_api_seasonal():
    res = client.get("/api/forecast/seasonal?months=6&uplift=1.0")
    assert res.status_code == 200
    forecast = res.json()
    assert len(forecast) == 6
    for row in forecast:
        assert "income" in row and "expenses" in row and "cash_after" in row
    print(f"[PASS] /api/forecast/seasonal returned {len(forecast)} forecast months")

def test_api_scenario_simulate():
    scenario = {
        "inv": "c2",
        "dl": 20,
        "sp": 15,
        "sup": "p2",
        "sh": 14,
        "ex": 50000,
        "exd": 14,
        "pred": False
    }
    res = client.post("/api/scenario/simulate", json=scenario)
    assert res.status_code == 200
    data = res.json()
    assert "baseline" in data and "modified" in data and "fixes" in data
    print("[PASS] /api/scenario/simulate baseline vs modified")

def test_api_fixes():
    res = client.get("/api/fixes")
    assert res.status_code == 200
    data = res.json()
    assert len(data["fixes"]) == 3
    print("[PASS] /api/fixes calculated 3 solutions. Best fix index:", data["best_index"])

def test_api_chat():
    queries = [
        "When will I run short of cash?",
        "Which customers pay late?",
        "How is my financial health?",
        "What should I do about the shortage?",
        "Plan for Diwali"
    ]
    for q in queries:
        res = client.post("/api/chat", json={"message": q, "history": []})
        assert res.status_code == 200
        reply = res.json().get("reply")
        assert reply, f"Empty reply for '{q}'"
        print(f"[PASS] /api/chat answered query")

def test_api_reminders():
    # Send a reminder
    payload = {
        "customer_id": "kiran",
        "channel": "email",
        "message": "Hi Kiran Enterprises, invoice #1030 is due."
    }
    res = client.post("/api/reminders", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["cust"] == "Kiran Enterprises"
    print("[PASS] /api/reminders POST logged reminder:", data["status"])

    # Retrieve reminders log
    get_res = client.get("/api/reminders")
    assert get_res.status_code == 200
    log = get_res.json()
    assert len(log) >= 1
    print(f"[PASS] /api/reminders GET returned {len(log)} logged messages")

def test_api_users():
    test_user = {
        "name": "Ramesh Kumar",
        "email": "ramesh@teststore.example",
        "biz_name": "Kumar General Store",
        "biz_type": "Retail Store",
        "biz_size": "Micro",
        "country": "INR",
        "currency": "INR"
    }
    # 1. Save user
    post_res = client.post("/api/users", json=test_user)
    assert post_res.status_code == 200
    res_data = post_res.json()
    assert res_data["ok"] is True
    print("[PASS] /api/users POST saved user profile")

    # 2. Get user by email
    by_em_res = client.get(f"/api/users/by-email/{test_user['email']}")
    assert by_em_res.status_code == 200
    user_data = by_em_res.json()
    assert user_data["email"] == test_user["email"]
    assert user_data["biz_name"] == test_user["biz_name"]
    print("[PASS] /api/users/by-email retrieved saved user profile successfully")

    # 3. Get all users
    all_users_res = client.get("/api/users")
    assert all_users_res.status_code == 200
    users_list = all_users_res.json()
    assert any(u["email"] == test_user["email"] for u in users_list)
    print(f"[PASS] /api/users GET verified user exists in {len(users_list)} total users")

def test_api_auth():
    test_auth_user = {
        "name": "Auth Tester",
        "email": "authtest@example.com",
        "password": "Password@123",
        "biz_name": "Auth Business",
        "biz_type": "Services",
        "biz_size": "Just me",
        "country": "INR",
        "currency": "INR"
    }
    # Register user with password
    reg_res = client.post("/api/auth/register", json=test_auth_user)
    assert reg_res.status_code in (200, 409)

    # Test WRONG password -> MUST return 401 Unauthorized
    bad_login = client.post("/api/auth/login", json={"email": "authtest@example.com", "password": "WrongPassword999"})
    assert bad_login.status_code == 401
    assert "Incorrect password" in bad_login.json().get("detail", "")
    print("[PASS] /api/auth/login correctly rejected WRONG password with HTTP 401")

    # Test CORRECT password -> MUST return 200 OK
    good_login = client.post("/api/auth/login", json={"email": "authtest@example.com", "password": "Password@123"})
    assert good_login.status_code == 200
    assert good_login.json().get("ok") is True
    print("[PASS] /api/auth/login correctly accepted CORRECT password with HTTP 200")

    # Test NON-EXISTENT user -> MUST return 401
    unknown_login = client.post("/api/auth/login", json={"email": "nonexistent_9999@nowhere.com", "password": "Password@123"})
    assert unknown_login.status_code == 401
    print("[PASS] /api/auth/login rejected non-existent account")

def test_money_in_out_exact_nine_records():
    """Verify exact financial metrics for the 9 test transactions:
    Opening balance: 100,000
    Total income: 140,000 (50k settled + 90k pending)
    Total expenses: 200,000 (20k settled + 180k pending)
    Current cash balance: 130,000 (100k opening + 50k received - 20k paid)
    October actual income: 50,000
    October actual expenses: 20,000
    October monthly net: +30,000
    """
    headers = {"X-User-Id": "u_1792867293938", "X-User-Email": "ayimantarannum09@gmail.com"}
    res = client.get("/api/overview", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["open_balance"] == 100000, f"Expected 100000 opening balance, got {data['open_balance']}"
    assert data["cash_balance"] == 130000, f"Expected 130000 current cash balance, got {data['cash_balance']}"

    totals = data["totals"]
    assert totals["total_income"] == 140000, f"Expected 140000 total income, got {totals['total_income']}"
    assert totals["total_expenses"] == 200000, f"Expected 200000 total expenses, got {totals['total_expenses']}"
    assert totals["received"] == 50000, f"Expected 50000 actual received, got {totals['received']}"
    assert totals["paid"] == 20000, f"Expected 20000 actual paid, got {totals['paid']}"
    assert totals["expected_inflows"] == 90000, f"Expected 90000 pending inflows, got {totals['expected_inflows']}"
    assert totals["expected_outflows"] == 180000, f"Expected 180000 pending outflows, got {totals['expected_outflows']}"

    print("[PASS] test_money_in_out_exact_nine_records passed: All 9 test transaction calculations match expected values!")

if __name__ == "__main__":
    test_static_routes()
    test_api_status()
    test_api_overview()
    test_money_in_out_exact_nine_records()
    test_api_transactions()
    test_api_customers_behaviour()
    test_api_health_score()
    test_api_seasonal()
    test_api_scenario_simulate()
    test_api_fixes()
    test_api_chat()
    test_api_reminders()
    test_api_users()
    test_api_auth()
    print("\n==========================================")
    print("ALL INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("==========================================")
