"""Database Service for HisaabHoshiyaar.
Supports dual backend:
1. Supabase (PostgreSQL in the cloud)
   - Uses the official supabase-py SDK for legacy JWT keys (eyJ...)
   - Uses a direct httpx REST client for the new publishable keys (sb_publishable_...)
     because supabase-py currently puts the key into the Authorization header as a JWT,
     which breaks with non-JWT keys (PGRST301). The direct client only sets 'apikey'.
2. SQLite (local fallback hh.db)

Automatically selects Supabase when SUPABASE_URL and SUPABASE_KEY are provided.
Falls back safely to local SQLite if Supabase is unconfigured or unreachable.
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
import numpy as np
import pandas as pd
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(dotenv_path=None):
        paths = [dotenv_path] if dotenv_path else [".env"]
        for p in paths:
            if p and os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            if "=" in line:
                                k, v = line.split("=", 1)
                                k = k.strip()
                                v = v.strip().strip("'\"")
                                if k and k not in os.environ:
                                    os.environ[k] = v
                except Exception:
                    pass

# Configure logging
logger = logging.getLogger("hh.db")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Base directory for resolving relative paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load .env file (first from current folder, then parent folder)
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.join(os.path.dirname(BASE_DIR), ".env"))
load_dotenv()

# SQLite setup
DB_PATH = os.path.join(BASE_DIR, "hh.db")
sqlite_conn = sqlite3.connect(DB_PATH, check_same_thread=False)

# Optional psycopg2 import for direct Supabase PostgreSQL pooler connection
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Seed Data
SEED_CUSTOMERS = [
    {
        "id": "kiran",
        "name": "Kiran Enterprises",
        "email": "accounts@kiran.example",
        "phone": "+919800000001",
        "history": [0, 0, 1, 0, 2, 0],
    },
    {
        "id": "sharma",
        "name": "Sharma Traders",
        "email": "pay@sharma.example",
        "phone": "+919800000002",
        "history": [0, 3, 0, 5, 2, 4],
    },
    {
        "id": "lakshmi",
        "name": "Lakshmi Stores",
        "email": "pay@lakshmi.example",
        "phone": "+919800000003",
        "history": [4, 9, 6, 12, 8, 11],
    },
    {
        "id": "metro",
        "name": "Metro Mart",
        "email": "ap@metro.example",
        "phone": "+919800000004",
        "history": [6, 9, 12, 10, 14, 16],
    },
    {
        "id": "anand",
        "name": "Anand Retail",
        "email": "pay@anand.example",
        "phone": "+919800000005",
        "history": [15, 22, 30, 28, 35, 41],
    },
]

SEED_TRANSACTIONS = [
    {"id": "c0", "name": "Kiran Enterprises - Inv #1030", "cust": "kiran", "type": "customer", "dir": "in", "amount": 90000, "day": -3, "delay": 0, "status": "settled"},
    {"id": "c1", "name": "Anand Retail - Inv #1042", "cust": "anand", "type": "customer", "dir": "in", "amount": 75000, "day": -6, "delay": 10, "status": "overdue"},
    {"id": "c2", "name": "Metro Mart - Inv #1051", "cust": "metro", "type": "customer", "dir": "in", "amount": 320000, "day": 20, "delay": 8, "status": "expected"},
    {"id": "c3", "name": "Lakshmi Stores - Inv #1058", "cust": "lakshmi", "type": "customer", "dir": "in", "amount": 260000, "day": 33, "delay": 0, "status": "expected"},
    {"id": "c4", "name": "Sharma Traders - Inv #1063", "cust": "sharma", "type": "customer", "dir": "in", "amount": 200000, "day": 47, "delay": 0, "status": "expected"},
    {"id": "e0", "name": "Electricity bill", "cust": None, "type": "expense", "dir": "out", "amount": 18000, "day": -2, "delay": 0, "status": "settled"},
    {"id": "e1", "name": "Shop rent", "cust": None, "type": "expense", "dir": "out", "amount": 60000, "day": 5, "delay": 0, "status": "expected"},
    {"id": "e2", "name": "Shop rent", "cust": None, "type": "expense", "dir": "out", "amount": 60000, "day": 35, "delay": 0, "status": "expected"},
    {"id": "p1", "name": "Fresh Foods Co.", "cust": None, "type": "supplier", "dir": "out", "amount": 150000, "day": 10, "delay": 0, "status": "expected"},
    {"id": "p2", "name": "Gupta Wholesale", "cust": None, "type": "supplier", "dir": "out", "amount": 520000, "day": 31, "delay": 0, "status": "expected"},
    {"id": "pr1", "name": "Staff salaries", "cust": None, "type": "payroll", "dir": "out", "amount": 280000, "day": 34, "delay": 0, "status": "expected"},
    {"id": "l1", "name": "Bank loan instalment", "cust": None, "type": "loan", "dir": "out", "amount": 45000, "day": 25, "delay": 0, "status": "expected"},
    {"id": "l2", "name": "Bank loan instalment", "cust": None, "type": "loan", "dir": "out", "amount": 45000, "day": 53, "delay": 0, "status": "expected"},
]


# ---------------------------------------------------------------------------
# Direct REST client for new-format Supabase keys (sb_publishable_* / sb_secret_*)
#
# supabase-py currently injects the API key into both 'apikey' AND 'Authorization'
# headers. For the new non-JWT key format this causes PostgREST to return:
#   PGRST301: "Expected 3 parts in JWT; got 1"
#
# This thin httpx wrapper only sets 'apikey' (and omits Authorization for
# unauthenticated requests), which is what PostgREST expects for the new keys.
# ---------------------------------------------------------------------------

class _SupabaseRestClient:
    """Minimal PostgREST/Supabase REST client that works with new-format API keys."""

    TIMEOUT = 15.0  # seconds

    def __init__(self, url: str, key: str):
        self.base = url.rstrip("/") + "/rest/v1"
        self._headers = {
            "apikey": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # -- helpers --

    def _get(self, table: str, params: Optional[Dict] = None) -> List[Dict]:
        r = httpx.get(
            f"{self.base}/{table}",
            headers=self._headers,
            params=params or {},
            timeout=self.TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    def _post(self, table: str, data: Any, params: Optional[Dict] = None) -> List[Dict]:
        hdrs = {**self._headers, "Prefer": "return=representation"}
        r = httpx.post(
            f"{self.base}/{table}",
            headers=hdrs,
            json=data,
            params=params or {},
            timeout=self.TIMEOUT,
        )
        r.raise_for_status()
        return r.json() if r.text else []

    def _patch(self, table: str, filters: Dict, data: Dict) -> List[Dict]:
        hdrs = {**self._headers, "Prefer": "return=representation"}
        params = {k: f"eq.{v}" for k, v in filters.items()}
        r = httpx.patch(
            f"{self.base}/{table}",
            headers=hdrs,
            json=data,
            params=params,
            timeout=self.TIMEOUT,
        )
        r.raise_for_status()
        return r.json() if r.text else []

    def _delete(self, table: str, filters: Dict) -> List[Dict]:
        hdrs = {**self._headers, "Prefer": "return=representation"}
        params = {k: f"eq.{v}" for k, v in filters.items()}
        r = httpx.delete(
            f"{self.base}/{table}",
            headers=hdrs,
            params=params,
            timeout=self.TIMEOUT,
        )
        r.raise_for_status()
        return r.json() if r.text else []

    def _upsert(self, table: str, data: Any) -> List[Dict]:
        hdrs = {**self._headers, "Prefer": "return=representation,resolution=merge-duplicates"}
        r = httpx.post(
            f"{self.base}/{table}",
            headers=hdrs,
            json=data,
            timeout=self.TIMEOUT,
        )
        r.raise_for_status()
        return r.json() if r.text else []

    # -- public API (mirrors the subset used in DatabaseManager) --

    def select(self, table: str, columns: str = "*", limit: int = 1000,
               order_by: Optional[str] = None, order_desc: bool = False,
               gte_filter: Optional[Tuple[str, Any]] = None,
               eq_filters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        params: Dict[str, Any] = {"select": columns, "limit": limit}
        if order_by:
            params["order"] = f"{order_by}.{'desc' if order_desc else 'asc'}"
        if gte_filter:
            params[gte_filter[0]] = f"gte.{gte_filter[1]}"
        if eq_filters:
            for k, v in eq_filters.items():
                params[k] = f"eq.{v}"
        return self._get(table, params)

    def insert(self, table: str, row: Dict) -> List[Dict]:
        return self._post(table, row)

    def upsert(self, table: str, rows: Any) -> List[Dict]:
        return self._upsert(table, rows)

    def update(self, table: str, filters: Dict, data: Dict) -> List[Dict]:
        return self._patch(table, filters, data)

    def delete(self, table: str, filters: Dict) -> List[Dict]:
        return self._delete(table, filters)

    def delete_gte(self, table: str, column: str, value: Any) -> List[Dict]:
        hdrs = {**self._headers, "Prefer": "return=representation"}
        params = {column: f"gte.{value}"}
        r = httpx.delete(
            f"{self.base}/{table}",
            headers=hdrs,
            params=params,
            timeout=self.TIMEOUT,
        )
        r.raise_for_status()
        return r.json() if r.text else []


def _is_jwt_key(key: str) -> bool:
    """Return True if the key looks like a legacy JWT (3 dot-separated base64 parts)."""
    return key.startswith("eyJ") and key.count(".") >= 2


VALID_TX_TYPES = {'customer', 'supplier', 'expense', 'payroll', 'loan', 'cust', 'sup', 'pay', 'exp'}

def normalize_tx_type(t: Optional[str], dir_: Optional[str] = "in") -> str:
    """Ensures transaction type conforms to Supabase and database CHECK constraints."""
    val = (t or "").strip().lower()
    if val in VALID_TX_TYPES:
        return val
    d = (dir_ or "in").strip().lower()
    if d == "in":
        return "customer"
    if "pay" in val or "salar" in val:
        return "payroll"
    if "loan" in val or "emi" in val or "borrow" in val:
        return "loan"
    if "sup" in val or "vendor" in val or "invent" in val or "stock" in val:
        return "supplier"
    return "expense"


class DatabaseManager:
    """Manages database connections, queries, and failover between Supabase and SQLite."""

    def __init__(self):
        self.sqlite_conn = sqlite_conn
        self.supabase_client = None   # supabase-py Client (legacy JWT keys only)
        self._rest_client: Optional[_SupabaseRestClient] = None  # direct REST (new keys)
        self._pg_conn_str: Optional[str] = None
        self.provider = "sqlite"
        self._connected = False
        self._init_sqlite()
        self._init_connection()

    # ------------------------------------------------------------------
    # Internal helpers that dispatch to whichever Supabase backend is active
    # ------------------------------------------------------------------

    def _sb_select(self, table: str, columns: str = "*", limit: int = 1000,
                   order_by: Optional[str] = None, order_desc: bool = False,
                   eq_filters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        if self._rest_client:
            return self._rest_client.select(table, columns, limit, order_by, order_desc, eq_filters=eq_filters)
        res = self.supabase_client.table(table).select(columns).limit(limit)
        if eq_filters:
            for k, v in eq_filters.items():
                res = res.eq(k, v)
        if order_by:
            res = res.order(order_by, desc=order_desc)
        return res.execute().data or []

    def _sb_insert(self, table: str, row: Dict) -> List[Dict]:
        if self._rest_client:
            return self._rest_client.insert(table, row)
        res = self.supabase_client.table(table).insert(row).execute()
        return res.data or []

    def _sb_upsert(self, table: str, rows: Any) -> List[Dict]:
        if self._rest_client:
            return self._rest_client.upsert(table, rows)
        res = self.supabase_client.table(table).upsert(rows).execute()
        return res.data or []

    def _sb_update(self, table: str, filters: Dict, data: Dict) -> List[Dict]:
        if self._rest_client:
            return self._rest_client.update(table, filters, data)
        q = self.supabase_client.table(table).update(data)
        for k, v in filters.items():
            q = q.eq(k, v)
        return q.execute().data or []

    def _sb_delete(self, table: str, filters: Dict) -> List[Dict]:
        if self._rest_client:
            return self._rest_client.delete(table, filters)
        q = self.supabase_client.table(table).delete()
        for k, v in filters.items():
            q = q.eq(k, v)
        return q.execute().data or []

    def _sb_delete_gte(self, table: str, column: str, value: Any) -> List[Dict]:
        if self._rest_client:
            return self._rest_client.delete_gte(table, column, value)
        return self.supabase_client.table(table).delete().gte(column, value).execute().data or []

    # ------------------------------------------------------------------
    # Connection initialisation
    # ------------------------------------------------------------------

    def _init_connection(self):
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

        if not (url and key):
            self.provider = "sqlite"
            self._connected = True
            logger.info("SUPABASE_URL not configured. Operating in local SQLite mode at %s.", DB_PATH)
            return

        # Check for direct Supabase PostgreSQL connection string (DATABASE_URL)
        db_url = os.getenv("DATABASE_URL", "").strip()
        if db_url and PSYCOPG2_AVAILABLE:
            try:
                test_conn = psycopg2.connect(db_url, connect_timeout=8)
                test_cur = test_conn.cursor()
                test_cur.execute("SELECT 1;")
                test_cur.close()
                test_conn.close()
                self._pg_conn_str = db_url
                logger.info("Direct Supabase PostgreSQL Pooler connection verified.")
            except Exception as e:
                logger.warning("Could not connect directly to Supabase Postgres pooler (%s).", e)

        # Decide which Supabase client to use based on key format
        if _is_jwt_key(key):
            # Legacy JWT key — use the official supabase-py SDK
            try:
                from supabase import create_client, Client
                client: Client = create_client(url, key)
                # Lightweight connectivity check
                client.table("customers").select("id").limit(1).execute()
                self.supabase_client = client
                self.provider = "supabase"
                self._connected = True
                logger.info("Connected to Supabase via supabase-py (JWT key) at %s", url)
            except Exception as e:
                logger.warning(
                    "supabase-py connection failed (%s). Falling back to SQLite at %s.", e, DB_PATH
                )
                self.provider = "sqlite"
                self._connected = True
        else:
            # New-format key (sb_publishable_* / sb_secret_*) — use direct REST client
            try:
                rest = _SupabaseRestClient(url, key)
                # Lightweight connectivity check
                rest.select("customers", "id", limit=1)
                self._rest_client = rest
                self.provider = "supabase"
                self._connected = True
                logger.info(
                    "Connected to Supabase via direct REST client (publishable key) at %s", url
                )
            except Exception as e:
                logger.warning(
                    "Supabase REST connection failed (%s). Falling back to SQLite at %s.", e, DB_PATH
                )
                self.provider = "sqlite"
                self._connected = True

    # ------------------------------------------------------------------

    def init_db(self):
        """Initializes tables and seeds initial data if database is empty."""
        # Always ensure SQLite schema is ready (as primary or offline fallback)
        self._init_sqlite()

        if self.is_supabase:
            try:
                self._seed_supabase_if_empty()
            except Exception as e:
                logger.error("Error verifying/seeding Supabase tables: %s", e)

    def _init_sqlite(self):
        with sqlite_conn:
            sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    email TEXT UNIQUE,
                    biz_name TEXT,
                    biz_type TEXT,
                    biz_size TEXT,
                    country TEXT DEFAULT 'INR',
                    currency TEXT DEFAULT 'INR',
                    cash_balance INTEGER DEFAULT 430000
                )
            """)
            try:
                sqlite_conn.execute("ALTER TABLE users ADD COLUMN cash_balance INTEGER DEFAULT 430000")
            except Exception:
                pass
            sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS users_auth (
                    email TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS comms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER,
                    cust TEXT,
                    ch TEXT,
                    msg TEXT,
                    status TEXT
                )
            """)
            sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    email TEXT,
                    phone TEXT,
                    history TEXT
                )
            """)
            sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    cust TEXT,
                    type TEXT,
                    dir TEXT,
                    amount INTEGER,
                    day INTEGER,
                    delay INTEGER,
                    status TEXT,
                    note TEXT
                )
            """)
            try:
                sqlite_conn.execute("ALTER TABLE transactions ADD COLUMN note TEXT")
            except Exception:
                pass

        # Seed SQLite customers if empty
        cur = sqlite_conn.execute("SELECT COUNT(*) FROM customers")
        if cur.fetchone()[0] == 0:
            seed_cust = [
                (c["id"], c["name"], c["email"], c["phone"], json.dumps(c["history"]))
                for c in SEED_CUSTOMERS
            ]
            with sqlite_conn:
                sqlite_conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", seed_cust)

        # Seed SQLite transactions if empty
        cur = sqlite_conn.execute("SELECT COUNT(*) FROM transactions")
        if cur.fetchone()[0] == 0:
            seed_tx = [
                (t["id"], t["name"], t["cust"], t["type"], t["dir"], t["amount"], t["day"], t["delay"], t["status"])
                for t in SEED_TRANSACTIONS
            ]
            with sqlite_conn:
                sqlite_conn.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?)", seed_tx)

    def _seed_supabase_if_empty(self):
        # Check customers
        rows = self._sb_select("customers", "id", limit=1)
        if not rows:
            logger.info("Supabase 'customers' table is empty. Seeding initial customers...")
            self._sb_upsert("customers", SEED_CUSTOMERS)

        # Check transactions
        rows_tx = self._sb_select("transactions", "id", limit=1)
        if not rows_tx:
            logger.info("Supabase 'transactions' table is empty. Seeding initial transactions...")
            self._sb_upsert("transactions", SEED_TRANSACTIONS)

    @property
    def is_supabase(self) -> bool:
        return self.provider == "supabase" and (
            self.supabase_client is not None or self._rest_client is not None
        )

    def get_provider(self) -> str:
        return self.provider

    # ------------------------------------------------------------------
    # CRUD — Customers
    # ------------------------------------------------------------------

    def get_customers_dict(self) -> Dict[str, Tuple[str, str, str, list]]:
        if self.is_supabase:
            try:
                rows = self._sb_select("customers", "id,name,email,phone,history")
                out = {}
                for row in rows:
                    hist = row.get("history")
                    if isinstance(hist, str):
                        try:
                            hist = json.loads(hist)
                        except Exception:
                            hist = []
                    elif not isinstance(hist, list):
                        hist = []
                    out[row["id"]] = (
                        row.get("name") or "",
                        row.get("email") or "",
                        row.get("phone") or "",
                        hist,
                    )
                return out
            except Exception as e:
                logger.error("Supabase get_customers_dict failed: %s. Falling back to SQLite.", e)

        # Fallback / Local SQLite
        cur = sqlite_conn.execute("SELECT id, name, email, phone, history FROM customers")
        out = {}
        for row in cur.fetchall():
            try:
                h = json.loads(row[4]) if row[4] else []
            except Exception:
                h = []
            out[row[0]] = (row[1], row[2], row[3], h)
        return out

    # ------------------------------------------------------------------
    # CRUD — Transactions
    # ------------------------------------------------------------------

    def get_transactions_df(self, user_id: Optional[str] = None) -> pd.DataFrame:
        cols = ["id", "name", "cust", "type", "dir", "amount", "day", "delay", "status"]
        if self.is_supabase:
            try:
                eq_filters = {"note": f"uid:{user_id}"} if user_id else None
                rows = self._sb_select("transactions", ",".join(cols + ["note"]), eq_filters=eq_filters)
                # If specific user requested but no user-specific rows exist, return shared seed records (with empty note or None)
                if user_id and not rows:
                    all_rows = self._sb_select("transactions", ",".join(cols + ["note"]))
                    rows = [r for r in all_rows if not r.get("note") or r.get("note") == f"uid:{user_id}"]
                df = pd.DataFrame(rows)
                if df.empty:
                    df = pd.DataFrame(columns=cols)
                else:
                    for c in cols:
                        if c not in df.columns:
                            df[c] = None
                    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0).astype("int64")
                    df["day"] = pd.to_numeric(df["day"], errors="coerce").fillna(0).astype("int64")
                    df["delay"] = pd.to_numeric(df["delay"], errors="coerce").fillna(0).astype("int64")
                return df[cols].replace({np.nan: None})
            except Exception as e:
                logger.error("Supabase get_transactions_df failed: %s. Falling back to SQLite.", e)

        # Fallback / Local SQLite
        if user_id:
            df = pd.read_sql_query("SELECT id, name, cust, type, dir, amount, day, delay, status FROM transactions WHERE note = ?", sqlite_conn, params=(f"uid:{user_id}",))
        else:
            df = pd.read_sql_query("SELECT id, name, cust, type, dir, amount, day, delay, status FROM transactions", sqlite_conn)
        return df.replace({np.nan: None})

    def add_transaction(
        self,
        tid: str,
        name: str,
        cust: Optional[str],
        type_: str,
        dir_: str,
        amount: int,
        day: int,
        delay: int,
        status: str,
        user_id: Optional[str] = None,
    ) -> bool:
        clean_cust = cust.strip() if (cust and isinstance(cust, str) and cust.strip()) else None
        clean_type = normalize_tx_type(type_, dir_)
        clean_dir = "in" if dir_ == "in" else "out"
        clean_status = status if status in ("expected", "settled", "overdue") else "expected"
        clean_amt = int(amount)
        clean_day = int(day)
        clean_delay = int(delay)
        note_val = f"uid:{user_id}" if user_id else None

        if self.is_supabase:
            try:
                row = {
                    "id": tid, "name": name, "cust": clean_cust, "type": clean_type,
                    "dir": clean_dir, "amount": clean_amt, "day": clean_day,
                    "delay": clean_delay, "status": clean_status,
                    "note": note_val,
                }
                self._sb_insert("transactions", row)
                # Mirror to SQLite for offline resilience
                try:
                    with sqlite_conn:
                        sqlite_conn.execute(
                            "INSERT OR REPLACE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (tid, name, clean_cust, clean_type, clean_dir, clean_amt, clean_day, clean_delay, clean_status, note_val),
                        )
                except Exception:
                    pass
                return True
            except Exception as e:
                logger.error("Supabase add_transaction failed: %s. Falling back to SQLite.", e)

        # Fallback / Local SQLite
        with sqlite_conn:
            sqlite_conn.execute(
                "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (tid, name, clean_cust, clean_type, clean_dir, clean_amt, clean_day, clean_delay, clean_status, note_val),
            )
        return True

    def update_transaction(
        self,
        tx_id: str,
        name: Optional[str] = None,
        cust: Optional[str] = None,
        type_: Optional[str] = None,
        dir_: Optional[str] = None,
        amount: Optional[int] = None,
        day: Optional[int] = None,
        delay: Optional[int] = None,
        status: Optional[str] = None,
    ) -> bool:
        update_fields: Dict[str, Any] = {}
        if name is not None: update_fields["name"] = name
        if cust is not None:
            clean_cust = cust.strip() if (isinstance(cust, str) and cust.strip()) else None
            update_fields["cust"] = clean_cust
        if type_ is not None:
            clean_type = normalize_tx_type(type_, dir_ or "in")
            update_fields["type"] = clean_type
        if dir_ is not None: update_fields["dir"] = "in" if dir_ == "in" else "out"
        if amount is not None: update_fields["amount"] = int(amount)
        if day is not None: update_fields["day"] = int(day)
        if delay is not None: update_fields["delay"] = int(delay)
        if status is not None:
            update_fields["status"] = status if status in ("expected", "settled", "overdue") else "expected"

        if not update_fields:
            return True

        updated = False
        if self.is_supabase:
            try:
                res = self._sb_update("transactions", {"id": tx_id}, update_fields)
                updated = bool(res)
            except Exception as e:
                logger.error("Supabase update_transaction failed: %s", e)

        # Mirror / fallback to SQLite
        try:
            set_clause = ", ".join(f"{k} = ?" for k in update_fields.keys())
            vals = list(update_fields.values()) + [tx_id]
            with sqlite_conn:
                cur = sqlite_conn.execute(
                    f"UPDATE transactions SET {set_clause} WHERE id = ?", vals
                )
                if not self.is_supabase:
                    updated = cur.rowcount > 0
                elif cur.rowcount > 0:
                    updated = True
        except Exception as e:
            logger.error("SQLite update_transaction failed: %s", e)

        return updated

    def update_transaction_status(self, tx_id: str, status: str) -> bool:
        updated = False
        if self.is_supabase:
            try:
                res = self._sb_update("transactions", {"id": tx_id}, {"status": status})
                updated = bool(res)
                with sqlite_conn:
                    sqlite_conn.execute(
                        "UPDATE transactions SET status = ? WHERE id = ?", (status, tx_id)
                    )
                return updated
            except Exception as e:
                logger.error(
                    "Supabase update_transaction_status failed: %s. Falling back to SQLite.", e
                )

        with sqlite_conn:
            cur = sqlite_conn.execute(
                "UPDATE transactions SET status = ? WHERE id = ?", (status, tx_id)
            )
            updated = cur.rowcount > 0
        return updated

    def delete_transaction(self, tx_id: str) -> bool:
        deleted = False
        if self.is_supabase:
            try:
                res = self._sb_delete("transactions", {"id": tx_id})
                deleted = bool(res)
                with sqlite_conn:
                    sqlite_conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
                return deleted
            except Exception as e:
                logger.error("Supabase delete_transaction failed: %s. Falling back to SQLite.", e)

        with sqlite_conn:
            cur = sqlite_conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
            deleted = cur.rowcount > 0
        return deleted

    # ------------------------------------------------------------------
    # CRUD — Comms (payment reminders log)
    # ------------------------------------------------------------------

    def add_comm(self, ts: int, cust: str, ch: str, msg: str, status: str) -> Dict[str, Any]:
        if self.is_supabase:
            try:
                row = {"ts": ts, "cust": cust, "ch": ch, "msg": msg, "status": status}
                res = self._sb_insert("comms", row)
                row_id = res[0].get("id", ts) if res else ts
                # Mirror to SQLite
                try:
                    with sqlite_conn:
                        sqlite_conn.execute(
                            "INSERT INTO comms (ts, cust, ch, msg, status) VALUES (?,?,?,?,?)",
                            (ts, cust, ch, msg, status),
                        )
                except Exception:
                    pass
                return {"id": row_id, "ts": ts, "cust": cust, "ch": ch, "msg": msg, "status": status}
            except Exception as e:
                logger.error("Supabase add_comm failed: %s. Falling back to SQLite.", e)

        with sqlite_conn:
            cur = sqlite_conn.execute(
                "INSERT INTO comms (ts, cust, ch, msg, status) VALUES (?,?,?,?,?)",
                (ts, cust, ch, msg, status),
            )
        return {"id": cur.lastrowid, "ts": ts, "cust": cust, "ch": ch, "msg": msg, "status": status}

    def get_comms(self, limit: int = 100) -> List[Dict[str, Any]]:
        if self.is_supabase:
            try:
                rows = self._sb_select(
                    "comms", "id,ts,cust,ch,msg,status",
                    limit=limit, order_by="id", order_desc=True
                )
                return rows
            except Exception as e:
                logger.error("Supabase get_comms failed: %s. Falling back to SQLite.", e)

        cur = sqlite_conn.execute(
            "SELECT id, ts, cust, ch, msg, status FROM comms ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [
            {"id": r[0], "ts": r[1], "cust": r[2], "ch": r[3], "msg": r[4], "status": r[5]}
            for r in cur.fetchall()
        ]

    def clear_comms(self) -> bool:
        if self.is_supabase:
            try:
                # PostgREST requires a filter on DELETE; gte id 0 matches all rows
                self._sb_delete_gte("comms", "id", 0)
                with sqlite_conn:
                    sqlite_conn.execute("DELETE FROM comms")
                return True
            except Exception as e:
                logger.error("Supabase clear_comms failed: %s. Falling back to SQLite.", e)

        with sqlite_conn:
            sqlite_conn.execute("DELETE FROM comms")
        return True

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # User Account & Authentication Management
    # ------------------------------------------------------------------

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using PBKDF2-HMAC-SHA256 with 100,000 rounds and random salt."""
        salt = secrets.token_hex(16)
        pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
        return f"{salt}:{pw_hash}"

    @staticmethod
    def verify_password(stored: str, password: str) -> bool:
        """Verify password against salt:hash string."""
        if not stored or ":" not in stored:
            return False
        try:
            salt, pw_hash = stored.split(":", 1)
            test_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
            return hmac.compare_digest(pw_hash, test_hash)
        except Exception:
            return False

    @staticmethod
    def _clean_user_dict(u: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Removes internal auth/balance markers when exposing to API or UI, and surfaces cash_balance."""
        if not u or not isinstance(u, dict):
            return u
        cleaned = dict(u)
        raw_size = cleaned.get("biz_size") or ""
        if "###auth:" in raw_size:
            size_part, _ = raw_size.split("###auth:", 1)
            cleaned["biz_size"] = size_part
        raw_type = cleaned.get("biz_type") or ""
        if "###bal:" in raw_type:
            type_part, bal_str = raw_type.split("###bal:", 1)
            cleaned["biz_type"] = type_part
            try:
                cleaned["cash_balance"] = int(bal_str)
            except Exception:
                cleaned["cash_balance"] = 430000
        elif "cash_balance" not in cleaned or cleaned["cash_balance"] is None:
            cleaned["cash_balance"] = 430000
        else:
            try:
                cleaned["cash_balance"] = int(cleaned["cash_balance"])
            except Exception:
                cleaned["cash_balance"] = 430000
        return cleaned

    def get_user_cash_balance(self, email_or_id: str) -> int:
        """Retrieves manually set cash balance for an authenticated user."""
        target = (email_or_id or "").strip()
        if not target:
            return 430000
        # Check Supabase
        if self.is_supabase:
            try:
                users = self._sb_select("users", "*", limit=100)
                for u in users:
                    if u.get("id") == target or (u.get("email") or "").strip().lower() == target.lower():
                        cleaned = self._clean_user_dict(u)
                        return int(cleaned.get("cash_balance", 430000))
            except Exception as e:
                logger.error("Supabase get_user_cash_balance error: %s", e)
        # Check SQLite
        try:
            cur = sqlite_conn.execute(
                "SELECT cash_balance, biz_type FROM users WHERE id = ? OR LOWER(email) = ?",
                (target, target.lower())
            )
            row = cur.fetchone()
            if row:
                if row[0] is not None:
                    return int(row[0])
                if row[1] and "###bal:" in row[1]:
                    return int(row[1].split("###bal:")[1])
        except Exception:
            pass
        return 430000

    def set_user_cash_balance(self, email_or_id: str, balance: int) -> bool:
        """Saves manually edited opening cash balance for the user in Supabase & SQLite."""
        target = (email_or_id or "").strip()
        bal_int = int(balance)
        success = False
        # Save in Supabase
        if self.is_supabase:
            try:
                users = self._sb_select("users", "*", limit=100)
                for u in users:
                    if u.get("id") == target or (u.get("email") or "").strip().lower() == target.lower():
                        raw_type = u.get("biz_type") or ""
                        clean_type = raw_type.split("###bal:")[0].strip()
                        new_type = f"{clean_type}###bal:{bal_int}"
                        self._sb_update("users", {"id": u["id"]}, {"biz_type": new_type})
                        success = True
                        break
            except Exception as e:
                logger.error("Supabase set_user_cash_balance failed: %s", e)
        # Mirror to SQLite
        try:
            with sqlite_conn:
                cur = sqlite_conn.execute(
                    "UPDATE users SET cash_balance = ? WHERE id = ? OR LOWER(email) = ?",
                    (bal_int, target, target.lower())
                )
                if cur.rowcount > 0:
                    success = True
        except Exception as e:
            logger.error("SQLite set_user_cash_balance failed: %s", e)
        return success

    def get_user_password_hash(self, email: str) -> Optional[str]:
        clean_email = (email or "").strip().lower()
        if not clean_email:
            return None
        # 1. Check local SQLite users_auth
        try:
            cur = sqlite_conn.execute("SELECT password_hash FROM users_auth WHERE LOWER(email) = ?", (clean_email,))
            row = cur.fetchone()
            if row and row[0]:
                return row[0]
        except Exception:
            pass
        # 2. Check Supabase user row encoded in biz_size
        if self.is_supabase:
            try:
                users = self._sb_select("users", "*", limit=100)
                for u in users:
                    if (u.get("email") or "").strip().lower() == clean_email:
                        raw_size = u.get("biz_size") or ""
                        if "###auth:" in raw_size:
                            _, hash_part = raw_size.split("###auth:", 1)
                            if hash_part:
                                return hash_part
            except Exception as e:
                logger.error("Supabase get_user_password_hash error: %s", e)
        return None

    def set_user_password_hash(self, email: str, pw_hash: str):
        clean_email = (email or "").strip().lower()
        if not clean_email or not pw_hash:
            return
        # Store in SQLite users_auth
        try:
            with sqlite_conn:
                sqlite_conn.execute("INSERT OR REPLACE INTO users_auth (email, password_hash) VALUES (?, ?)", (clean_email, pw_hash))
        except Exception as e:
            logger.error("SQLite set_user_password_hash failed: %s", e)
        # Store in Supabase
        if self.is_supabase:
            try:
                users = self._sb_select("users", "*", limit=100)
                for u in users:
                    if (u.get("email") or "").strip().lower() == clean_email:
                        raw_size = u.get("biz_size") or ""
                        clean_size = raw_size.split("###auth:")[0].strip()
                        new_size = f"{clean_size}###auth:{pw_hash}"
                        self._sb_update("users", {"id": u["id"]}, {"biz_size": new_size})
                        break
            except Exception as e:
                logger.error("Supabase set_user_password_hash failed: %s", e)

    def authenticate_user(self, email: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        clean_email = (email or "").strip().lower()
        if not clean_email:
            return False, None, "Email address is required."
        if not password:
            return False, None, "Password is required."

        user = self.get_user_by_email(clean_email)
        if not user:
            return False, None, "No account found with this email. Please register first."

        stored_hash = self.get_user_password_hash(clean_email)
        if stored_hash:
            if self.verify_password(stored_hash, password):
                return True, user, "Login successful."
            else:
                return False, None, "Incorrect password. Please try again."
        else:
            return False, None, "Password not set for this account. Please re-register or reset password."

    def reset_password(self, email: str, new_password: str) -> Tuple[bool, str]:
        clean_email = (email or "").strip().lower()
        if not clean_email:
            return False, "Email address is required."
        if not new_password or len(new_password) < 8:
            return False, "Password must be at least 8 characters with letters and numbers."

        user = self.get_user_by_email(clean_email)
        if not user:
            return False, "No account found with this email. Please check the email address."

        pw_hash = self.hash_password(new_password)
        self.set_user_password_hash(clean_email, pw_hash)
        logger.info("Successfully reset password for %s in Supabase and SQLite", clean_email)
        return True, "Password has been successfully reset! You can now log in."

    def save_user(self, uid: str, name: str, email: str, biz_name: str, biz_type: str = "", biz_size: str = "", country: str = "INR", currency: str = "INR", password: Optional[str] = None) -> Dict[str, Any]:
        """Persists or updates user account details in Supabase and local SQLite with secure password hashing."""
        clean_email = (email or "").strip().lower()
        clean_name = (name or "").strip() or "Business Owner"
        clean_biz = (biz_name or "").strip() or "My Business"
        clean_size = (biz_size or "").split("###auth:")[0].strip()

        # Handle password hashing
        if password:
            pw_hash = self.hash_password(password)
            stored_size = f"{clean_size}###auth:{pw_hash}"
            self.set_user_password_hash(clean_email, pw_hash)
        else:
            # Preserve existing hash if recorded
            existing_hash = self.get_user_password_hash(clean_email)
            stored_size = f"{clean_size}###auth:{existing_hash}" if existing_hash else clean_size

        user_row = {
            "id": uid,
            "name": clean_name,
            "email": clean_email,
            "biz_name": clean_biz,
            "biz_type": biz_type or "",
            "biz_size": stored_size,
            "country": country or "INR",
            "currency": currency or "INR",
        }
        if self.is_supabase:
            try:
                # Check if a user with this email already exists
                existing = self._sb_select("users", "*", limit=100)
                matched = next((r for r in existing if (r.get("email") or "").strip().lower() == clean_email), None)
                if matched:
                    user_row["id"] = matched["id"]
                    self._sb_update("users", {"id": matched["id"]}, user_row)
                    logger.info("Updated existing user profile in Supabase: %s", clean_email)
                else:
                    self._sb_upsert("users", [user_row])
                    logger.info("Saved new user profile to Supabase: %s (%s)", clean_email, clean_biz)
            except Exception as e:
                logger.error("Supabase save_user failed: %s", e)

        # Mirror/fallback to SQLite
        try:
            with sqlite_conn:
                cur = sqlite_conn.execute("SELECT id FROM users WHERE LOWER(email) = ?", (clean_email,))
                existing_row = cur.fetchone()
                if existing_row:
                    user_row["id"] = existing_row[0]
                    sqlite_conn.execute("""
                        UPDATE users SET name=?, biz_name=?, biz_type=?, biz_size=?, country=?, currency=?
                        WHERE id=?
                    """, (clean_name, clean_biz, biz_type, clean_size, country, currency, existing_row[0]))
                else:
                    sqlite_conn.execute("""
                        INSERT INTO users (id, name, email, biz_name, biz_type, biz_size, country, currency)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (user_row["id"], clean_name, clean_email, clean_biz, biz_type, clean_size, country, currency))
        except Exception as e:
            logger.error("SQLite save_user failed: %s", e)
        return self._clean_user_dict(user_row)

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        clean_email = (email or "").strip().lower()
        if not clean_email:
            return None
        if self.is_supabase:
            try:
                users = self._sb_select("users", "*", limit=100)
                for u in users:
                    if (u.get("email") or "").strip().lower() == clean_email:
                        return self._clean_user_dict(u)
            except Exception as e:
                logger.error("Supabase get_user_by_email failed: %s", e)
        try:
            cur = sqlite_conn.execute(
                "SELECT id, name, email, biz_name, biz_type, biz_size, country, currency FROM users WHERE LOWER(email) = ?",
                (clean_email,)
            )
            r = cur.fetchone()
            if r:
                return self._clean_user_dict({
                    "id": r[0], "name": r[1], "email": r[2], "biz_name": r[3],
                    "biz_type": r[4], "biz_size": r[5], "country": r[6], "currency": r[7]
                })
        except Exception as e:
            logger.error("SQLite get_user_by_email failed: %s", e)
        return None

    def get_users(self) -> List[Dict[str, Any]]:
        if self.is_supabase:
            try:
                res = self._sb_select("users", "*", limit=50)
                return [self._clean_user_dict(u) for u in res]
            except Exception as e:
                logger.error("Supabase get_users failed: %s", e)
        try:
            cur = sqlite_conn.execute("SELECT id, name, email, biz_name, biz_type, biz_size, country, currency FROM users")
            return [
                self._clean_user_dict({"id": r[0], "name": r[1], "email": r[2], "biz_name": r[3], "biz_type": r[4], "biz_size": r[5], "country": r[6], "currency": r[7]})
                for r in cur.fetchall()
            ]
        except Exception:
            return []

    def sync_sqlite_to_supabase(self) -> Dict[str, Any]:
        """Uploads all local SQLite data to Supabase (upsert mode)."""
        if not self.is_supabase:
            raise RuntimeError(
                "Supabase client is not connected. "
                "Configure SUPABASE_URL and SUPABASE_KEY in .env first."
            )

        # 1. Sync Customers
        cur_c = sqlite_conn.execute("SELECT id, name, email, phone, history FROM customers")
        cust_rows = []
        for r in cur_c.fetchall():
            try:
                hist = json.loads(r[4])
            except Exception:
                hist = []
            cust_rows.append({"id": r[0], "name": r[1], "email": r[2], "phone": r[3], "history": hist})
        if cust_rows:
            self._sb_upsert("customers", cust_rows)

        # 2. Sync Transactions
        cur_t = sqlite_conn.execute(
            "SELECT id, name, cust, type, dir, amount, day, delay, status FROM transactions"
        )
        tx_rows = []
        for r in cur_t.fetchall():
            tx_rows.append({
                "id": r[0], "name": r[1], "cust": r[2], "type": r[3], "dir": r[4],
                "amount": int(r[5]), "day": int(r[6]), "delay": int(r[7]), "status": r[8],
            })
        if tx_rows:
            self._sb_upsert("transactions", tx_rows)

        # 3. Sync Comms
        cur_m = sqlite_conn.execute("SELECT ts, cust, ch, msg, status FROM comms")
        comm_rows = [
            {"ts": r[0], "cust": r[1], "ch": r[2], "msg": r[3], "status": r[4]}
            for r in cur_m.fetchall()
        ]
        if comm_rows:
            self._sb_insert("comms", comm_rows)

        return {
            "ok": True,
            "synced_customers": len(cust_rows),
            "synced_transactions": len(tx_rows),
            "synced_comms": len(comm_rows),
        }

    def get_status(self) -> Dict[str, Any]:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        masked_key = f"{key[:6]}...{key[-4:]}" if len(key) > 10 else ("***" if key else "")
        db_url = os.getenv("DATABASE_URL", "")
        masked_db_url = f"{db_url.split('@')[0].split(':')[0]}://***@{db_url.split('@')[1]}" if '@' in db_url else (db_url[:12] + "..." if db_url else None)

        tx_df = self.get_transactions_df()
        cust_dict = self.get_customers_dict()
        comms = self.get_comms(limit=10)

        return {
            "provider": self.provider,
            "connected": self._connected,
            "is_supabase": self.is_supabase,
            "supabase_url": url if url else None,
            "supabase_key_configured": bool(key),
            "masked_key": masked_key if key else None,
            "direct_postgres_connected": bool(self._pg_conn_str),
            "masked_database_url": masked_db_url,
            "sqlite_path": DB_PATH,
            "counts": {
                "customers": len(cust_dict),
                "transactions": len(tx_df),
                "recent_comms": len(comms),
            },
        }


# Singleton instance
db_manager = DatabaseManager()
