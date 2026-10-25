"""HisaabHoshiyaar backend: FastAPI + pandas + SQLite.
Run: uvicorn main:app --reload --port 8000
"""
import json
import os
import smtplib
import sqlite3
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import List, Optional

import httpx
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Base configuration
OPEN = 430_000
SAFE = 100_000
H = 8
BIZ = "Sharma Provision Store"

app = FastAPI(title="HisaabHoshiyaar API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ----------------- Database Setup & Supabase Integration -----------------
from db_service import db_manager, DatabaseManager

# Initialize the active database (Supabase Cloud if configured, SQLite hh.db otherwise)
db_manager.init_db()
db = db_manager.sqlite_conn  # Backward compatibility alias

def get_customers_dict():
    return db_manager.get_customers_dict()

def get_transactions_df(user_id: Optional[str] = None):
    return db_manager.get_transactions_df(user_id=user_id)

# Historical monthly data for seasonal analysis (24 months, Nov 2024 is i=0)
SG = [1.05, 0.9, 1.15, 1.05, 0.85, 0.8, 0.85, 1.0, 1.05, 1.2, 1.45, 1.2]
def _rev(i):
    return round(800000 * (1 + 0.012 * i) * SG[(10 + i) % 12] * (1 + 0.04 * np.sin(i * 2.3)))

HIST = pd.DataFrame({"i": range(24)})
HIST["month"] = (10 + HIST.i) % 12
HIST["rev"] = [_rev(i) for i in HIST.i]
HIST["exp"] = [round(0.55 * _rev(i) + 0.25 * _rev(i + 1) + 100000) for i in HIST.i]

FESTIVALS = {
    0: "Sankranti / Pongal",
    2: "Holi",
    3: "Ugadi / Baisakhi",
    7: "Onam / Ganesh Chaturthi",
    9: "Dussehra",
    10: "Diwali",
    11: "Christmas & New Year"
}
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ----------------- Analytics Engine -----------------
def forecast(tx: pd.DataFrame, open_=OPEN):
    d = np.zeros(H + 1)
    for r in tx[tx.status != "settled"].itertuples():
        effective_day = r.day + r.delay
        w = max(0, int(np.ceil(effective_day / 7)))
        if w <= H:
            d[w] += r.amount if r.dir == "in" else -r.amount
    return (open_ + d.cumsum()).astype(int).tolist()

def metrics(b: List[int], safe=SAFE, tx: Optional[pd.DataFrame] = None, open_: int = OPEN):
    lowest = int(min(b))
    lowest_week = int(b.index(lowest))
    shortage_week = next((i for i, v in enumerate(b) if v < 0), None)
    weeks_below_zero = int(sum(v < 0 for v in b))
    weeks_below_safe = int(sum(v < safe for v in b))

    # Chronological transaction-level shortage analysis
    shortage_date = None
    causing_tx = None
    if tx is not None and not tx.empty:
        pending = tx[tx.status != "settled"].copy()
        if not pending.empty:
            pending["eff_day"] = pending["day"] + pending["delay"]
            pending = pending.sort_values("eff_day")
            bal = open_
            for r in pending.itertuples():
                change = r.amount if r.dir == "in" else -r.amount
                bal += change
                if bal < 0:
                    shortage_date = int(r.eff_day)
                    causing_tx = {
                        "id": getattr(r, "id", ""),
                        "name": getattr(r, "name", ""),
                        "amount": int(getattr(r, "amount", 0)),
                        "dir": getattr(r, "dir", "out"),
                        "type": getattr(r, "type", getattr(r, "_4", "expense")),
                        "eff_day": int(getattr(r, "eff_day", 0))
                    }
                    break

    return {
        "lowest": lowest,
        "lowest_week": lowest_week,
        "shortage_week": shortage_week,
        "weeks_below_zero": weeks_below_zero,
        "weeks_below_safety": weeks_below_safe,
        "shortage_date": shortage_date,
        "causing_transaction": causing_tx,
        "lo": lowest,
        "s": shortage_week,
        "z": weeks_below_zero,
        "sf": weeks_below_safe,
    }

def behaviour(user_id: Optional[str] = None):
    cust_dict = get_customers_dict()
    tx = get_transactions_df(user_id=user_id)
    out = []
    for cid, (name, email, phone, h) in cust_dict.items():
        s = pd.Series(h, dtype=float)
        op = tx[(tx.cust == cid) & (tx.status != "settled")]
        avg = float(s.mean()) if len(s) else 0.0
        if np.isnan(avg):
            avg = 0.0
        trend = float(s.tail(3).mean() - s.head(3).mean()) if len(s) >= 3 else 0.0
        if np.isnan(trend):
            trend = 0.0
        cls = "overdue" if (op.status == "overdue").any() or avg > 14 else "late" if avg > 3 else "regular"
        out_amount = int(op.amount.sum()) if len(op) else 0
        on_time = round(float((s <= 2).mean()) * 100) if len(s) else 100
        out.append({
            "id": cid,
            "name": name,
            "n": name,
            "email": email,
            "em": email,
            "phone": phone,
            "ph": phone,
            "avg_delay": round(avg, 1),
            "avg": round(avg, 1),
            "on_time_pct": on_time,
            "ontime": on_time,
            "trend": "slower" if trend > 1 else "improving" if trend < -1 else "steady",
            "tr": round(trend, 2),
            "status": cls,
            "cls": "over" if cls == "overdue" else cls,
            "outstanding": out_amount,
            "out": out_amount,
            "history": h,
            "h": h
        })
    return out

def health(open_: Optional[int] = None, user_id: Optional[str] = None):
    opening_bal = OPEN if open_ is None else open_
    tx = get_transactions_df(user_id=user_id)
    b = forecast(tx, open_=opening_bal)
    m = metrics(b, open_=opening_bal, tx=tx)
    cs = behaviour(user_id=user_id)
    rec = int(tx[(tx.type.isin(["customer", "cust"])) & (tx.status != "settled")].amount.sum() or 1)
    outs = int(tx[(tx.dir == "out") & (tx.status != "settled")].amount.sum() or 1)
    risk = sum(c["outstanding"] * (1.0 if c["status"] == "overdue" else 0.5 if c["status"] == "late" else 0.0) for c in cs)
    l6 = HIST.tail(6)
    rev_sum = float(l6.rev.sum())
    margin = float(1 - l6.exp.sum() / rev_sum) if rev_sum > 0 else 0.25
    if np.isnan(margin) or np.isinf(margin):
        margin = 0.25

    def cl(x):
        try:
            val = float(x)
            if np.isnan(val) or np.isinf(val):
                return 0.0
            return float(min(1.0, max(0.0, val)))
        except Exception:
            return 0.0

    comps = {
        "liquidity": (20, cl(m["lowest"] / SAFE)),
        "shortage_risk": (20, 1 - cl(m["weeks_below_zero"] / 3)),
        "collections": (20, 1 - cl(risk / rec * 1.5)),
        "obligation_cover": (15, cl((opening_bal + rec) / outs / 1.2)),
        "cash_trend": (10, cl(0.5 + (b[H] - opening_bal) / (opening_bal if opening_bal != 0 else 1))),
        "margin": (15, cl(margin / 0.25))
    }
    score = int(round(sum(w * s for w, s in comps.values())))
    label = "Strong" if score >= 75 else "Stable" if score >= 55 else "Needs attention" if score >= 35 else "At risk"

    recs_map = {
        "liquidity": f"Lowest projected balance is ₹{m['lowest']:,}, below safety limit ₹{SAFE:,}. Rebuild cash reserve.",
        "shortage_risk": f"Cash is below zero in {m['weeks_below_zero']} week(s). Pull cash forward or postpone bills.",
        "collections": f"₹{int(risk):,} of receivables sit with late/overdue customers. Issue reminders.",
        "obligation_cover": "Upcoming payments match incoming receipts closely. Extend supplier terms.",
        "cash_trend": "Cash balance at end of horizon is lower than current balance.",
        "margin": f"Expenses consume {round((1 - margin)*100)}% of revenue. Streamline overheads."
    }
    recommendations = [recs_map[k] for k, (w, s) in comps.items() if s < 0.65]

    comps_list = [
        {"k": "liq", "key": "liquidity", "name": "Liquidity buffer", "w": 20, "s": round(comps["liquidity"][1], 2)},
        {"k": "short", "key": "shortage_risk", "name": "Shortage risk", "w": 20, "s": round(comps["shortage_risk"][1], 2)},
        {"k": "coll", "key": "collections", "name": "Collections quality", "w": 20, "s": round(comps["collections"][1], 2)},
        {"k": "obl", "key": "obligation_cover", "name": "Obligation coverage", "w": 15, "s": round(comps["obligation_cover"][1], 2)},
        {"k": "trend", "key": "cash_trend", "name": "Cash trend", "w": 10, "s": round(comps["cash_trend"][1], 2)},
        {"k": "margin", "key": "margin", "name": "Profit margin", "w": 15, "s": round(comps["margin"][1], 2)},
    ]

    return {
        "score": score,
        "label": label,
        "comps": comps_list,
        "components": {k: {"weight": w, "score": round(s, 2)} for k, (w, s) in comps.items()},
        "m": m,
        "risk": int(risk),
        "mg": round(margin, 3),
        "recommendations": recommendations,
        "b": b
    }

def seasonal(n: int = 6, uplift: float = 1.0, open_: Optional[int] = None):
    def fit(col):
        b, a = np.polyfit(HIST.i, HIST[col], 1)
        ratio = (HIST[col] / (a + b * HIST.i))
        # groupby month
        idx_series = ratio.groupby(HIST.month).mean()
        return a, b, idx_series

    ar, br, ir = fit("rev")
    ae, be, ie = fit("exp")
    cash = OPEN if open_ is None else open_
    rows = []

    for j in range(n):
        i = 24 + j
        m = (10 + i) % 12
        year = 2024 + (10 + i) // 12
        idx_val = float(ir.get(m, 1.0))
        exp_idx = float(ie.get(m, 1.0))
        tr_r = round(ar + br * i)
        tr_e = round(ae + be * i)
        rev = round(tr_r * (1 + (idx_val - 1) * uplift))
        exp = round(tr_e * exp_idx)
        cash += rev - exp

        rows.append({
            "month": int(m),
            "m": int(m),
            "month_name": MONTH_NAMES[m],
            "year": int(year),
            "y": int(year),
            "income": int(rev),
            "rev": int(rev),
            "expenses": int(exp),
            "exp": int(exp),
            "net": int(rev - exp),
            "cash_after": int(cash),
            "cash": int(cash),
            "seasonal_index": round(idx_val, 2),
            "idx": round(idx_val, 2),
            "trR": tr_r,
            "trE": tr_e,
            "festival": FESTIVALS.get(m, "")
        })

    history_rows = [
        {
            "i": int(r.i),
            "m": int(r.month),
            "month_name": MONTH_NAMES[r.month],
            "y": int(2024 + (10 + r.i) // 12),
            "rev": int(r.rev),
            "exp": int(r.exp),
            "festival": FESTIVALS.get(r.month, "")
        }
        for r in HIST.itertuples()
    ]

    return {"forecast": rows, "history": history_rows}

def apply_scenario(s: dict, base_df: Optional[pd.DataFrame] = None):
    t = (base_df if base_df is not None else get_transactions_df()).copy()

    # Support multiple parameter naming conventions
    delay_tx = s.get("delay_tx") or s.get("inv")
    delay_days = s.get("delay_days") if s.get("delay_days") is not None else s.get("dl", 0)
    supplier_tx = s.get("supplier_tx") or s.get("sup")
    supplier_shift = s.get("supplier_shift") if s.get("supplier_shift") is not None else s.get("sh", 0)
    sales_pct = s.get("sales_pct") if s.get("sales_pct") is not None else s.get("sp", 0)
    expense_amt = s.get("expense_amount") if s.get("expense_amount") is not None else s.get("ex", 0)
    expense_day = s.get("expense_day") if s.get("expense_day") is not None else s.get("exd", 30)
    use_pred = s.get("pred", False)

    if delay_tx and delay_days:
        t.loc[t.id == delay_tx, "delay"] += int(delay_days)

    if supplier_tx and supplier_shift:
        t.loc[t.id == supplier_tx, "day"] += int(supplier_shift)

    if sales_pct and float(sales_pct) > 0:
        pct = float(sales_pct)
        mask = (t.type.isin(["customer", "cust"])) & (t.status != "settled")
        t.loc[mask, "amount"] = (t.loc[mask, "amount"] * (1 - pct / 100)).round().astype(int)

    if use_pred:
        cust_dict = get_customers_dict()
        for cid, (_, _, _, h) in cust_dict.items():
            avg_d = round(float(np.mean(h))) if len(h) else 0
            mask = (t.cust == cid) & (t.status != "settled")
            t.loc[mask, "delay"] = t.loc[mask, "delay"].apply(lambda d: max(int(d), avg_d))

    if expense_amt and float(expense_amt) > 0:
        new_row = pd.DataFrame([{
            "id": "x",
            "name": "Unexpected expense",
            "cust": None,
            "type": "expense",
            "dir": "out",
            "amount": int(expense_amt),
            "day": int(expense_day),
            "delay": 0,
            "status": "expected"
        }])
        t = pd.concat([t, new_row], ignore_index=True)

    return t

def compute_fixes(df: pd.DataFrame, open_: Optional[int] = None):
    opening_bal = OPEN if open_ is None else open_

    # Fix 1: Collect first eligible pending customer invoice 21 days earlier (or day 0 if earlier)
    f1_tx = df.copy()
    cust_mask = (f1_tx.type.isin(["customer", "cust"])) & (f1_tx.status != "settled")
    c_target = None
    if cust_mask.any():
        c_target = f1_tx[cust_mask].sort_values("day", ascending=False).iloc[0]
        f1_tx.loc[f1_tx.id == c_target["id"], "day"] = max(0, int(c_target["day"]) - 21)
    b1 = forecast(f1_tx, open_=opening_bal)
    m1 = metrics(b1, open_=opening_bal, tx=f1_tx)
    f1_desc = f"{c_target['name']} invoice collected 21 days earlier" if c_target is not None else "Customer invoice collected 21 days earlier"

    # Fix 2: Delay a supplier payment by 14 days
    f2_tx = df.copy()
    sup_mask = (f2_tx.type.isin(["supplier", "sup"])) & (f2_tx.status != "settled")
    s_target = None
    if sup_mask.any():
        s_target = f2_tx[sup_mask].sort_values("amount", ascending=False).iloc[0]
        f2_tx.loc[f2_tx.id == s_target["id"], "day"] += 14
    b2 = forecast(f2_tx, open_=opening_bal)
    m2 = metrics(b2, open_=opening_bal, tx=f2_tx)
    f2_desc = f"{s_target['name']} payment delayed 14 days" if s_target is not None else "Supplier payment delayed 14 days"

    # Fix 3: Short term loan (₹150,000 at day 28, repay ₹154,500 at day 56)
    loan_in = pd.DataFrame([{
        "id": "li", "name": "Short-term loan receipt", "cust": None,
        "type": "loan", "dir": "in", "amount": 150000, "day": 28, "delay": 0, "status": "expected"
    }])
    loan_out = pd.DataFrame([{
        "id": "lo", "name": "Loan repayment + 3% fee", "cust": None,
        "type": "loan", "dir": "out", "amount": 154500, "day": 56, "delay": 0, "status": "expected"
    }])
    f3_tx = pd.concat([df.copy(), loan_in, loan_out], ignore_index=True)
    b3 = forecast(f3_tx, open_=opening_bal)
    m3 = metrics(b3, open_=opening_bal, tx=f3_tx)

    fixes = [
        {"id": 1, "name": "Fix 1: Collect an invoice earlier", "desc": f1_desc, "b": b1, "m": m1},
        {"id": 2, "name": "Fix 2: Delay a supplier payment", "desc": f2_desc, "b": b2, "m": m2},
        {"id": 3, "name": "Fix 3: Short-term loan", "desc": "Loan of ₹150,000 in 28 days, repaid with 3% fee in 56 days", "b": b3, "m": m3},
    ]

    # Best fix: highest lowest balance, fewer weeks below zero
    best_idx = 0
    best_score = (-99999999, 999)
    for i, f in enumerate(fixes):
        score = (f["m"]["lo"], -f["m"]["z"])
        if score > best_score:
            best_score = score
            best_idx = i
    return {"fixes": fixes, "best_index": best_idx}

# ----------------- Intelligent AI Advisor Fallback -----------------
def generate_ollie_reply(q: str):
    s = q.lower().strip()
    tx = get_transactions_df()
    b = forecast(tx)
    m = metrics(b)
    cs = behaviour()
    hl = health()
    fx = compute_fixes(tx)
    best_f = fx["fixes"][fx["best_index"]]

    if any(k in s for k in ["short", "run out", "negative", "balance", "low", "runway"]):
        if m["s"] is not None:
            day_due = (m["s"] - 1) * 7 + 1
            due_date = (datetime.now() + timedelta(days=day_due)).strftime("%d %b")
            return {
                "reply": f"Your balance is projected to fall below zero in Week {m['s']} (around {due_date}), with a low of ₹{m['lo']:,}. Today you have ₹{OPEN:,}.",
                "html": f"Your balance is projected to fall below zero in <b>Week {m['s']}</b> (around {due_date}), with a low of <b>₹{m['lo']:,}</b>. Today you have <b>₹{OPEN:,}</b>.<br><button class=\"chip\" data-go=\"fx\">Compare fixes →</button>"
            }
        else:
            return {
                "reply": f"No shortage is forecast. Your lowest projected balance is ₹{m['lo']:,} against a safety threshold of ₹{SAFE:,}.",
                "html": f"No cash shortage is forecast! Your lowest projected balance is <b>₹{m['lo']:,}</b> against safety threshold <b>₹{SAFE:,}</b>.<br><button class=\"chip\" data-go=\"ov\">View Overview →</button>"
            }

    if any(k in s for k in ["late", "overdue", "customer", "collect", "owes", "unpaid"]):
        late_custs = [c for c in cs if c["status"] in ["late", "overdue"]]
        if late_custs:
            details = [f"{c['name']} (avg {c['avg_delay']} days late, ₹{c['outstanding']:,} open{', overdue' if c['status']=='overdue' else ''})" for c in late_custs]
            html_details = [f"<b>{c['name']}</b> (avg {c['avg_delay']} days late, <b>₹{c['outstanding']:,}</b> open{', overdue' if c['status']=='overdue' else ''})" for c in late_custs]
            return {
                "reply": f"{len(late_custs)} customers pay late: {'; '.join(details)}. Send them a payment reminder.",
                "html": f"<b>{len(late_custs)} customers pay late:</b><br>• " + "<br>• ".join(html_details) + "<br><button class=\"chip\" data-go=\"cu\">Open Customers & Send Reminders →</button>"
            }
        return {
            "reply": "All your customers are currently paying on time!",
            "html": "All your customers are currently paying on time! Keep up positive customer relations."
        }

    if any(k in s for k in ["health", "score", "rating", "how am i doing", "status"]):
        weak = [c["name"] for c in hl["comps"] if c["s"] < 0.65]
        weak_str = " and ".join(weak) if weak else "None"
        return {
            "reply": f"Your financial health score is {hl['score']}/100 ({hl['label']}). Weakest areas: {weak_str}.",
            "html": f"Your financial health score is <b>{hl['score']}/100 ({hl['label']})</b>.<br>Weakest spots: <b>{weak_str}</b>.<br><button class=\"chip\" data-go=\"hl\">Open Health Score →</button>"
        }

    if any(k in s for k in ["fix", "solve", "improve", "recommend", "advice", "plan", "shortage"]):
        return {
            "reply": f"Based on cash metrics, {best_f['name']} looks best: lowest projected balance ₹{best_f['m']['lo']:,}, {best_f['m']['z']} week(s) below zero.",
            "html": f"On cash numbers alone, <b>{best_f['name']}</b> ({best_f['desc']}) looks best: lowest balance <b>₹{best_f['m']['lo']:,}</b>, {best_f['m']['z']} week(s) below zero.<br><button class=\"chip\" data-go=\"fx\">Compare fixes →</button>"
        }

    if any(k in s for k in ["diwali", "festival", "season", "holi", "christmas", "dussehra", "pongal"]):
        se = seasonal(6)["forecast"]
        peaks = [r for r in se if r["festival"] and r["seasonal_index"] > 1.05]
        if peaks:
            summary = [f"{p['festival']} in {p['month_name']} {p['year']}: revenue ≈ ₹{p['income']:,} (+{round((p['seasonal_index']-1)*100)}% uplift)" for p in peaks]
            html_summary = [f"<b>{p['festival']}</b> ({p['month_name']} {p['year']}): income ≈ <b>₹{p['income']:,}</b> (+{round((p['seasonal_index']-1)*100)}%)" for p in peaks]
            return {
                "reply": f"Upcoming festival peaks: {'; '.join(summary)}. Stock-up spending lands the month before, so keep cash ready.",
                "html": "Upcoming festival peaks:<br>• " + "<br>• ".join(html_summary) + "<br><i>Remember: stock-up spending lands the month before, so keep liquidity ready!</i><br><button class=\"chip\" data-go=\"se\">Open Seasonal Forecast →</button>"
            }
        return {
            "reply": "No major festival sales peaks in the next 6 months.",
            "html": "No major festival sales peaks in the next 6 months.<br><button class=\"chip\" data-go=\"se\">Open Seasonal Forecast →</button>"
        }

    if any(k in s for k in ["remind", "email", "sms", "message"]):
        return {
            "reply": "You can send 1-click personalized payment reminders via Email or SMS from the Customers tab.",
            "html": "You can send 1-click personalized reminders from the Customers tab. Start with the most overdue invoices!<br><button class=\"chip\" data-go=\"cu\">Open Customers →</button>"
        }

    return {
        "reply": f"Hi! I'm Ollie, your HisaabHoshiyaar cash flow assistant. You currently have ₹{OPEN:,} in cash. You can ask me about cash shortages, late-paying customers, financial health score, fixes, or festival forecasting.",
        "html": f"Hi! I'm Ollie, your cash flow assistant. You currently have <b>₹{OPEN:,}</b> in cash.<br>I can help you with:<br>• <b>Cash shortages & runway</b><br>• <b>Late customer invoices</b><br>• <b>Health score improvements</b><br>• <b>Recommended fixes</b><br>• <b>Festival & seasonal planning</b>"
    }

# ----------------- Static Files & Frontend Route -----------------
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
STYLE_PATH = os.path.join(BASE_DIR, "style.css")
SUPABASE_CLIENT_PATH = os.path.join(BASE_DIR, "supabaseClient.js")

@app.get("/")
def serve_index():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH)
    raise HTTPException(404, "index.html not found")

@app.get("/style.css")
def serve_style():
    if os.path.exists(STYLE_PATH):
        return FileResponse(STYLE_PATH, media_type="text/css")
    raise HTTPException(404, "style.css not found")

@app.get("/supabaseClient.js")
def serve_supabase_client():
    if os.path.exists(SUPABASE_CLIENT_PATH):
        return FileResponse(SUPABASE_CLIENT_PATH, media_type="application/javascript")
    raise HTTPException(404, "supabaseClient.js not found")

@app.get("/api/config")
def api_config():
    return {
        "supabaseUrl": os.getenv("SUPABASE_URL", "https://mskltxhhszqvqhbgaxbm.supabase.co"),
        "supabaseKey": os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY", "sb_publishable_C6HOmjdGbROzrAQom5Jn5A_9mCNWqfc")
    }

# ----------------- API Endpoints -----------------
@app.get("/api/status")
@app.get("/api/health")
def api_status():
    db_info = db_manager.get_status()
    return {
        "status": "ok",
        "app": "HisaabHoshiyaar",
        "version": "2.0.0",
        "business": BIZ,
        "open_balance": OPEN,
        "safety_limit": SAFE,
        "database": db_info["provider"],
        "database_connected": db_info["connected"],
        "supabase_enabled": db_info["is_supabase"],
    }

@app.get("/api/db/status")
def api_db_status():
    return db_manager.get_status()

@app.post("/api/db/sync-to-supabase")
def api_db_sync_to_supabase():
    try:
        return db_manager.sync_sqlite_to_supabase()
    except Exception as e:
        raise HTTPException(400, str(e))

class BalanceUpdate(BaseModel):
    balance: int
    user_id: Optional[str] = None
    email: Optional[str] = None

@app.get("/api/balance")
def api_get_balance(
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email")
):
    uid = user_id or x_user_id or x_user_email or "default"
    bal = db_manager.get_user_cash_balance(uid)
    return {"user_id": uid, "balance": bal}

@app.post("/api/balance")
@app.put("/api/balance")
def api_set_balance(
    b: BalanceUpdate,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email")
):
    uid = b.user_id or b.email or x_user_id or x_user_email or "default"
    ok = db_manager.set_user_cash_balance(uid, b.balance)
    return {"ok": ok, "user_id": uid, "balance": int(b.balance)}

@app.get("/api/overview")
def api_overview(
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email")
):
    uid = user_id or x_user_id or x_user_email or None
    open_bal = db_manager.get_user_cash_balance(uid) if uid else OPEN
    tx = get_transactions_df(user_id=uid)
    b = forecast(tx, open_=open_bal)
    m = metrics(b, safe=SAFE, tx=tx, open_=open_bal)
    pending = tx[tx.status != "settled"].copy()
    pending["eff_day"] = pending["day"] + pending["delay"]
    pending = pending.sort_values("eff_day")
    
    upcoming = []
    for r in pending.head(8).itertuples():
        upcoming.append({
            "id": r.id,
            "name": r.name,
            "n": r.name,
            "cust": r.cust if pd.notnull(r.cust) else None,
            "type": r.type,
            "dir": r.dir,
            "amount": int(r.amount),
            "a": int(r.amount),
            "day": int(r.day),
            "delay": int(r.delay),
            "eff_day": int(r.eff_day),
            "status": r.status
        })

    inflows = int(tx[(tx.dir == "in") & (tx.status != "settled")].amount.sum()) if not tx.empty else 0
    outflows = int(tx[(tx.dir == "out") & (tx.status != "settled")].amount.sum()) if not tx.empty else 0
    received = int(tx[(tx.dir == "in") & (tx.status == "settled")].amount.sum()) if not tx.empty else 0
    paid = int(tx[(tx.dir == "out") & (tx.status == "settled")].amount.sum()) if not tx.empty else 0
    current_cash = open_bal + received - paid

    return {
        "business": BIZ,
        "open_balance": open_bal,
        "cash_balance": current_cash,
        "user_id": uid,
        "safety_limit": SAFE,
        "horizon_weeks": H,
        "weekly_balances": b,
        "metrics": m,
        "upcoming_transactions": upcoming,
        "totals": {
            "expected_inflows": inflows,
            "expected_outflows": outflows,
            "received": received,
            "paid": paid,
            "total_income": inflows + received,
            "total_expenses": outflows + paid,
            "current_cash_balance": current_cash
        }
    }

@app.get("/api/transactions")
def api_transactions(
    q: Optional[str] = None,
    dir: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email")
):
    uid = user_id or x_user_id or x_user_email or None
    tx = get_transactions_df(user_id=uid)
    if q:
        tx = tx[tx.name.str.lower().str.contains(q.lower())]
    if dir:
        tx = tx[tx.dir == dir]
    if status:
        st_map = {"e": "expected", "s": "settled", "o": "overdue"}
        stat_val = st_map.get(status, status)
        tx = tx[tx.status == stat_val]

    # Convert to format compatible with both frontend and backend
    records = []
    for r in tx.itertuples():
        records.append({
            "id": r.id,
            "name": r.name,
            "n": r.name,
            "cust": None if (pd.isna(r.cust) or r.cust is None) else str(r.cust),
            "type": r.type,
            "ty": "cust" if r.type == "customer" else "sup" if r.type == "supplier" else "pay" if r.type == "payroll" else r.type,
            "dir": r.dir,
            "amount": int(r.amount),
            "a": int(r.amount),
            "day": int(r.day),
            "delay": int(r.delay),
            "dl": int(r.delay),
            "status": r.status,
            "st": "s" if r.status == "settled" else "o" if r.status == "overdue" else "e"
        })
    return records

class TransactionCreate(BaseModel):
    name: str
    type: str = "customer"  # customer, supplier, expense, payroll, loan
    dir: str = "in"         # in, out
    amount: int
    day: int = 0
    delay: int = 0
    cust: Optional[str] = None
    status: str = "expected" # expected, settled, overdue
    method: Optional[str] = "UPI"
    user_id: Optional[str] = None

class TransactionUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    dir: Optional[str] = None
    amount: Optional[int] = None
    day: Optional[int] = None
    delay: Optional[int] = None
    cust: Optional[str] = None
    status: Optional[str] = None
    method: Optional[str] = None

class UserProfile(BaseModel):
    name: str
    email: str
    biz_name: str
    biz_type: Optional[str] = ""
    biz_size: Optional[str] = ""
    country: Optional[str] = "INR"
    currency: Optional[str] = "INR"

class LoginRequest(BaseModel):
    email: str
    password: str

class ResetPasswordRequest(BaseModel):
    email: str
    new_password: str

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    biz_name: str
    biz_type: Optional[str] = ""
    biz_size: Optional[str] = ""
    country: Optional[str] = "INR"
    currency: Optional[str] = "INR"

@app.post("/api/auth/login")
def api_login(req: LoginRequest):
    ok, user, msg = db_manager.authenticate_user(req.email, req.password)
    if not ok:
        raise HTTPException(status_code=401, detail=msg)
    return {"ok": True, "user": user, "message": msg}

@app.post("/api/auth/reset-password")
def api_reset_password(req: ResetPasswordRequest):
    ok, msg = db_manager.reset_password(req.email, req.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}

@app.post("/api/auth/register")
def api_register(req: RegisterRequest):
    clean_email = (req.email or "").strip().lower()
    if not clean_email or "@" not in clean_email:
        raise HTTPException(status_code=400, detail="Invalid email address.")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    existing = db_manager.get_user_by_email(clean_email)
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists. Please log in.")

    uid = f"u_{int(time.time()*1000)}"
    user = db_manager.save_user(
        uid=uid,
        name=req.name,
        email=clean_email,
        biz_name=req.biz_name,
        biz_type=req.biz_type or "",
        biz_size=req.biz_size or "",
        country=req.country or "INR",
        currency=req.currency or "INR",
        password=req.password
    )
    return {"ok": True, "id": user.get("id", uid), "user": user}

@app.post("/api/users")
def api_save_user(u: UserProfile):
    uid = f"u_{int(time.time()*1000)}"
    saved = db_manager.save_user(
        uid=uid,
        name=u.name,
        email=u.email,
        biz_name=u.biz_name,
        biz_type=u.biz_type or "",
        biz_size=u.biz_size or "",
        country=u.country or "INR",
        currency=u.currency or "INR"
    )
    res_id = saved.get("id", uid) if isinstance(saved, dict) else uid
    return {"id": res_id, "ok": True, "user": saved}

@app.get("/api/users")
def api_get_users():
    return db_manager.get_users()

@app.get("/api/users/by-email/{email:path}")
def api_get_user_by_email(email: str):
    u = db_manager.get_user_by_email(email)
    if not u:
        raise HTTPException(404, "User not found")
    return u

@app.post("/api/transactions")
def api_add_transaction(
    t: TransactionCreate,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email")
):
    tid = f"t{int(time.time()*1000)}"
    cust = t.cust.strip() if t.cust and t.cust.strip() else None
    uid = t.user_id or x_user_id or x_user_email or None
    db_manager.add_transaction(tid, t.name, cust, t.type, t.dir, t.amount, t.day, t.delay, t.status, user_id=uid)
    return {"id": tid, "ok": True}

@app.put("/api/transactions/{tx_id}")
def api_update_transaction(tx_id: str, t: TransactionUpdate):
    cust = t.cust.strip() if (t.cust and t.cust.strip()) else None
    ok = db_manager.update_transaction(
        tx_id,
        name=t.name,
        cust=cust,
        type_=t.type,
        dir_=t.dir,
        amount=t.amount,
        day=t.day,
        delay=t.delay,
        status=t.status
    )
    if not ok:
        raise HTTPException(404, "Transaction not found")
    return {"ok": True}

@app.put("/api/transactions/{tx_id}/status")
def api_update_tx_status(tx_id: str, status: str = Query(...)):
    ok = db_manager.update_transaction_status(tx_id, status)
    if not ok:
        raise HTTPException(404, "Transaction not found")
    return {"ok": True}

@app.delete("/api/transactions/{tx_id}")
def api_delete_transaction(tx_id: str):
    ok = db_manager.delete_transaction(tx_id)
    if not ok:
        raise HTTPException(404, "Transaction not found")
    return {"ok": True}

@app.get("/api/customers")
def api_customers():
    return get_customers_dict()

@app.get("/api/customers/behaviour")
def r_behaviour(
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email")
):
    uid = user_id or x_user_id or x_user_email or None
    return behaviour(user_id=uid)

@app.get("/api/health-score")
def r_health(
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email")
):
    uid = user_id or x_user_id or x_user_email or None
    open_bal = db_manager.get_user_cash_balance(uid) if uid else OPEN
    return health(open_=open_bal, user_id=uid)

@app.get("/api/forecast/seasonal")
def r_seasonal(
    months: int = 6,
    uplift: float = 1.0,
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email")
):
    uid = user_id or x_user_id or x_user_email or None
    open_bal = db_manager.get_user_cash_balance(uid) if uid else OPEN
    res = seasonal(months, uplift, open_=open_bal)
    return res["forecast"]

@app.get("/api/fixes")
def r_fixes(
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email")
):
    uid = user_id or x_user_id or x_user_email or None
    open_bal = db_manager.get_user_cash_balance(uid) if uid else OPEN
    return compute_fixes(get_transactions_df(user_id=uid), open_=open_bal)

@app.post("/api/scenario/simulate")
def r_sim(
    s: dict,
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email")
):
    uid = s.get("user_id") or user_id or x_user_id or x_user_email or None
    req_open = s.get("open_balance") or s.get("open")
    if req_open is not None:
        open_bal = int(req_open)
    elif uid:
        open_bal = db_manager.get_user_cash_balance(uid)
    else:
        open_bal = OPEN

    base_tx = get_transactions_df(user_id=uid)
    mod_tx = apply_scenario(s, base_tx)
    base = forecast(base_tx, open_=open_bal)
    mod = forecast(mod_tx, open_=open_bal)
    fixes = compute_fixes(mod_tx, open_=open_bal)
    return {
        "baseline": base,
        "modified": mod,
        "baseline_metrics": metrics(base, open_=open_bal, tx=base_tx),
        "modified_metrics": metrics(mod, open_=open_bal, tx=mod_tx),
        "fixes": fixes["fixes"],
        "best_fix_index": fixes["best_index"]
    }

class Chat(BaseModel):
    message: str
    history: list = []

@app.post("/api/chat")
def r_chat(c: Chat):
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    tx = get_transactions_df()
    base = forecast(tx)
    ctx = json.dumps({
        "open_balance": OPEN,
        "safety_limit": SAFE,
        "weekly_balances": base,
        "metrics": metrics(base),
        "customers": behaviour(),
        "health": health(),
        "seasonal_forecast": seasonal(6)["forecast"]
    }, default=str)

    # 1. If Anthropic Claude API key is configured
    if anthropic_key:
        try:
            system_prompt = (
                "You are Ollie, the owl assistant in HisaabHoshiyaar, a cash-flow app for small businesses. "
                "Answer ONLY from the JSON data below; never invent figures. Be concise and practical, amounts in INR (₹). "
                "Suggest actionable solutions.\nDATA:\n" + ctx
            )
            hist = [{"role": h["role"], "content": str(h["content"])} for h in c.history[-8:] if h.get("role") in ("user", "assistant")]
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                timeout=25,
                headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={
                    "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
                    "max_tokens": 600,
                    "system": system_prompt,
                    "messages": [*hist, {"role": "user", "content": c.message}]
                }
            )
            r.raise_for_status()
            text = "".join(b["text"] for b in r.json()["content"] if b["type"] == "text")
            return {"reply": text, "html": text.replace("\n", "<br>")}
        except Exception as e:
            # Fallback to local AI advisor if external API fails
            pass

    # 2. Intelligent Built-in Advisor fallback (always works out-of-the-box!)
    return generate_ollie_reply(c.message)

class Reminder(BaseModel):
    customer_id: str
    channel: str  # "email" | "sms"
    message: str

def send_email(to, subject, body):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = os.environ["MAIL_FROM"], to, subject
    m.set_content(body)
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", 587))) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(m)

def send_sms(to, body):
    sid = os.environ["TWILIO_SID"]
    r = httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, os.environ["TWILIO_TOKEN"]),
        data={"From": os.environ["TWILIO_FROM"], "To": to, "Body": body},
        timeout=20
    )
    r.raise_for_status()

@app.post("/api/reminders")
def r_send(r: Reminder):
    cust_dict = get_customers_dict()
    if r.customer_id not in cust_dict:
        raise HTTPException(404, "Unknown customer")
    name, email, phone, _ = cust_dict[r.customer_id]
    channel = r.channel.lower()

    if channel == "email" and os.getenv("SMTP_HOST") and os.getenv("MAIL_FROM"):
        try:
            send_email(email, f"Payment reminder from {BIZ}", r.message)
            status = "Sent"
        except Exception as e:
            status = f"Failed: {type(e).__name__}"
    elif channel == "sms" and os.getenv("TWILIO_SID") and os.getenv("TWILIO_TOKEN"):
        try:
            send_sms(phone, r.message)
            status = "Sent"
        except Exception as e:
            status = f"Failed: {type(e).__name__}"
    else:
        # In demo / development mode: successfully log without throwing
        status = "Logged (Demo)"

    ts = int(time.time() * 1000)
    ch_label = "SMS" if channel == "sms" else "Email"
    res = db_manager.add_comm(ts, name, ch_label, r.message, status)
    return res

@app.get("/api/reminders")
def r_log():
    return db_manager.get_comms(limit=100)

@app.delete("/api/reminders")
def r_clear_log():
    db_manager.clear_comms()
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
