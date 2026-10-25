# HisaabHoshiyaar (हिसाबहोशियार / ಹಿಸಾಬ್‌ಹೋಶಿಯಾರ್) 🦉

<div align="center">

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![SQLite](https://img.shields.io/badge/SQLite-Offline_Fallback-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![Tests](https://img.shields.io/badge/Tests-Passing_24/24-brightgreen?style=for-the-badge&logo=checkmarx&logoColor=white)](HisaabHoshiyaar/test_app.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

**"Because Every Rupee Has a Tomorrow"**  
*Intelligent cash-flow management, rolling 8-week predictive forecasting, what-if stress testing, customer payment behaviour analysis, and proactive working-capital recommendations for small business owners.*

[Explore Features](#-key-features) • [Quick Start](#-quick-start) • [Architecture](#-architecture--data-flow) • [API Documentation](#-api-reference) • [Tests](#-testing)

</div>

---

## 🌟 Overview

Cash flow failure is the #1 reason why profitable small businesses shut down. **HisaabHoshiyaar** solves this by providing business owners with forward-looking financial foresight. Rather than simply logging historical accounting entries, HisaabHoshiyaar projects where bank balances will be over the next **8 weeks**, warns of upcoming cash shortages before they occur, and simulates actionable solutions in real-time.

---

## 🚀 Key Features

### 1. 📊 Reconciled Cash Overview
- **Real-Time Position**: Calculates true available cash (`Opening Balance + Settled Inflows - Settled Outflows`).
- **Rolling 8-Week Predictive Forecast**: Incorporates expected invoice dates and scheduled bills to chart future liquidity.
- **Proactive Shortage Warnings**: Detects future low points and alerts when cash dips below the ₹1,00,000 safety reserve buffer or risks dropping below ₹0.

### 2. 💸 Synchronized Money In & Out
- **Full Transaction Lifecycle**: Track client payments, sales receipts, rent, vendor commitments, salaries, and tax outlays.
- **Settled vs. Pending Distinction**: Pending transactions automatically project into the forward forecast; settled transactions immediately update current bank cash.
- **Zero-Latency Cross-Module Sync**: Any addition, modification, status flip, or deletion immediately synchronizes across Cash Overview, What-If Simulator, Fix Comparison, and Health Score.

### 3. 🔮 Dynamic What-If Scenario Simulator
- **Stress-Test Working Capital**:
  - Customer Payment Delays (0 to 30 days)
  - Unexpected Expenses (e.g. equipment breakdown, sudden tax demand)
  - Reduced Sales Revenue (percentage drop in future incoming invoices)
  - Delayed Vendor Payments (holding bills to preserve cash)
- **Immediate Visual Feedback**: Dual-series interactive graph comparing Baseline trajectory vs. Modified scenario against safety buffer and ₹0 lines.
- **Dynamic Scenario Metrics**: Computes lowest projected balance, shortage week, duration of negative balance, and impact delta in real time without altering actual database records.

### 4. ⚖️ Fix Comparison Engine
- Evaluates practical cash-flow rescue strategies when a shortage is detected:
  1. **Invoice Discounting / Early Payment Incentives**: Accelerate receivables with 2% discount.
  2. **Supplier Payment Terms Negotiation**: Defer supplier obligations by 15–30 days.
  3. **Short-Term Working Capital Credit Line**: Emergency low-interest overdraft or invoice financing.
- Ranks solutions by effectiveness, interest cost, and timeline feasibility.

### 5. 👥 Customer Payment Behaviour & 1-Click Reminders
- Automatically monitors customer payment reliability, average delay days, overdue balances, and on-time settlement percentages.
- Generates personalized WhatsApp and Email payment follow-ups in English, Hindi, or Kannada.

### 6. 🩺 360° Financial Health Score (0–100)
- Assesses financial resilience across 5 weighted pillars:
  - **Liquidity Buffer** (Cash vs. Monthly Burn)
  - **Shortage Vulnerability** (Forecasted low-point severity)
  - **Receivables Quality** (Customer payment timeliness)
  - **Fixed Obligations Burden** (Salaries and rent vs. monthly revenue)
  - **Operating Margin** (Inflows vs. Outflows ratio)

### 7. 🗓️ Indian Seasonal Forecast
- 6-month seasonal projection factoring in Indian festive cycles (Diwali, Holi, Dussehra, Pongal/Sankranti, Eid, Wedding seasons) and quarterly tax cycles.

### 8. 🦉 Ask Ollie: AI Financial Advisory
- Built-in contextual AI advisor grounded directly in the user's live financial data.
- Answers questions about cash flow, upcoming payroll risks, vendor priority, and working capital optimization in natural language.

### 9. 🔐 Multi-User Authentication & Isolation
- Secure user registration and login with encrypted password verification.
- **Complete Data Isolation**: Each authenticated user has their own private opening balance, transactions, customer profiles, and scenario models.
- Clean session persistence with instant logout and protected view routing.

---

## 🏗 Architecture & Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    Single-Page Frontend                      │
│             (Vanilla HTML5 / Modern CSS / ES6+)              │
│       • Multilingual (EN, HI, KN)  • SVG Visualisations      │
│       • LocalStorage Session Tokens • Real-Time Interactivity│
└──────────────────────────────┬───────────────────────────────┘
                               │ JSON REST API
┌──────────────────────────────▼───────────────────────────────┐
│                    FastAPI Backend (Python)                  │
│       • main.py: Endpoints, Auth & CORS Router               │
│       • db_service.py: Reconciled Balance & Forecast Logic   │
│       • Multi-user row scoping & Note UID Tagging            │
└──────────────┬───────────────────────────────┬───────────────┘
               │ (Primary)                     │ (Offline Fallback)
┌──────────────▼───────────────┐┌──────────────▼───────────────┐
│   Supabase Cloud Database    ││      Local SQLite Database   │
│     (PostgreSQL + RLS)       ││            (hh.db)           │
│  • Direct REST & Pooler      ││  • Zero-config auto-fallback │
│  • Production persistence    ││  • Seamless offline mode     │
└──────────────────────────────┘└──────────────────────────────┘
```

### Cash Reconciliation Formula
$$\text{Current Available Cash} = \text{Opening Balance} + \sum \text{Settled Incomes} - \sum \text{Settled Expenses}$$

$$\text{Forecast Week } W_i = \text{Current Cash} + \sum_{t \le W_i} \text{Expected Pending Incomes} - \sum_{t \le W_i} \text{Scheduled Pending Bills}$$

---

## 🛠️ Tech Stack

- **Backend**: Python 3.10+, [FastAPI](https://fastapi.tiangolo.com/), Uvicorn, Pandas, HTTPX
- **Database**: [Supabase](https://supabase.com/) (PostgreSQL) with automatic zero-configuration [SQLite](https://sqlite.org/) fallback
- **Frontend**: Responsive Single-Page Application (HTML5, Modern CSS Variables, Modular Vanilla JavaScript, Custom SVG Charts)
- **AI Engine**: Context-aware Ollama / Claude / Gemini bridge + Deterministic Rule Engine
- **Internationalization**: Full i18n support for English (`en`), Hindi (`hi`), and Kannada (`kn`)

---

## ⚡ Quick Start

### 1. Prerequisites
- Python 3.10 or higher installed ([Download Python](https://python.org))
- Git installed (optional)

### 2. Clone the Repository
```bash
git clone https://github.com/<your-username>/HisaabHoshiyaar.git
cd HisaabHoshiyaar/HisaabHoshiyaar
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables (Optional for Supabase)
By default, HisaabHoshiyaar automatically starts in **SQLite local mode** with no setup needed!

To enable **Supabase Cloud persistence**, copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your Supabase project credentials in `.env`:
```ini
SUPABASE_URL=https://<your-project-id>.supabase.co
SUPABASE_KEY=<your-anon-or-service-role-key>
```
*(Run `supabase_schema.sql` in your Supabase SQL editor once to create the schema).*

### 5. Launch the Application

**Option A — Windows Shortcut:**
Double-click `run.bat` or run:
```powershell
.\run.ps1
```

**Option B — Direct Command:**
```bash
python -m uvicorn main:app --reload --port 8000
```
or:
```bash
python main.py
```

### 6. Open in Browser
Visit:
```
http://localhost:8000
```
- Click **Sign Up** to create a user account or test with sample credentials.
- The header badge displays `⚡ Supabase Cloud` or `● SQLite Local`. Click it anytime to view real-time database connection telemetry.

---

## 📖 API Reference

### Authentication & Users
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/auth/register` | Register a new user account with hashed password |
| `POST` | `/api/auth/login` | Authenticate user and issue session token |
| `GET` | `/api/users/by-email` | Fetch user profile by email |
| `POST` | `/api/users` | Update user business profile, safety buffer, and currency |

### Cash Overview & Balance
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/status` | Server status, DB engine, and active user stats |
| `GET` | `/api/overview` | Current cash, opening balance, metrics, and 8-week forecast |
| `GET` | `/api/balance` | Read current cash balance and opening balance |
| `POST` | `/api/balance` | Update user opening cash balance |

### Transactions (Money In & Out)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/transactions` | List all transactions scoped to authenticated user |
| `POST` | `/api/transactions` | Create a new income or expense transaction |
| `PUT` | `/api/transactions/{id}/status`| Toggle payment status (`Pending` ↔ `Received` / `Paid`) |
| `DELETE`| `/api/transactions/{id}`| Remove transaction from database |

### What-If Simulation & Fixes
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/scenario/simulate` | Run temporary stress test (delays, unexpected costs, sales drops) |
| `GET` | `/api/fixes` | Get ranked solutions to resolve forecasted cash shortages |

### Intelligence, Reminders & AI Chat
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/customers/behaviour` | Customer payment delay analysis and reliability metrics |
| `POST` | `/api/reminders` | Log and dispatch WhatsApp / Email reminder |
| `GET` | `/api/health-score` | Compute 0–100 Financial Health Score across 5 pillars |
| `GET` | `/api/forecast/seasonal` | 6-month seasonal forecast with Indian festival calendar |
| `POST` | `/api/chat` | Ask Ollie financial AI chatbot |
| `GET` | `/api/db/status` | View database connection telemetry and record counts |

---

## 🧪 Testing

The repository includes a comprehensive 24-point end-to-end integration test suite covering authentication, database failover, data isolation, exact transaction balances, What-If simulation calculations, and AI responses.

Run the test suite:
```bash
python test_app.py
```

Run Supabase cloud integration tests:
```bash
python test_supabase.py
```

**Expected Result:**
```
[PASS] Static route '/' successfully serves index.html
[PASS] /api/overview endpoint works
[PASS] test_money_in_out_exact_nine_records passed: All 9 test transaction calculations match expected values!
[PASS] /api/scenario/simulate baseline vs modified
[PASS] /api/fixes calculated 3 solutions
[PASS] /api/auth/login correctly rejected WRONG password
[PASS] /api/auth/login correctly accepted CORRECT password
==========================================
ALL INTEGRATION TESTS PASSED SUCCESSFULLY!
==========================================
```

---

## 📂 Project Structure

```
HisaabHoshiyaar/
├── main.py                 # FastAPI application, route handlers, auth endpoints
├── db_service.py           # Unified Database Service (Supabase REST + SQLite fallback)
├── test_app.py             # 24-point automated integration test suite
├── test_supabase.py        # Dedicated Supabase cloud connectivity test
├── index.html              # Frontend SPA (Views: Overview, Transactions, What-If, etc.)
├── style.css               # Neumorphic / Neo-brutalist responsive styling
├── supabase_schema.sql     # PostgreSQL schema, indexes, and RLS policies
├── migrate_to_supabase.py  # 1-click migration script from local SQLite to Supabase
├── setup_supabase.py       # Automated Supabase table provisioner
├── hh.db                   # Local SQLite database mirror (auto-generated)
├── requirements.txt        # Python package dependencies
├── run.bat / run.ps1       # One-click Windows startup scripts
└── README.md               # Project documentation
```

---

## 🌐 Multilingual Support

HisaabHoshiyaar was designed with local Indian business owners in mind:
- **English**: Default international business terminology.
- **Hindi (हिंदी)**: Accessible terminology (जमा राशि, आगामी भुगतान, नकदी संकट, समाधान).
- **Kannada (ಕನ್ನಡ)**: Localized phrasing for regional MSME enterprise adoption.

---

## 🛡️ Security & Privacy
- **User Scoping**: All database queries filter strictly by user identifier (`uid`).
- **Data Protection**: What-If scenario simulations operate strictly in-memory or on non-persistent copies; no actual financial records are altered unless explicitly saved.
- **Fallback Isolation**: Offline SQLite mirrors maintain the identical schema and authorization constraints as production Supabase.

---

## 🤝 Contributing

Contributions, bug reports, and feature requests are welcome!
1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---

<div align="center">
  <b>HisaabHoshiyaar</b> — <i>Be Smart With Money. Stay Ahead of Tomorrow.</i> 🦉
</div>
#   S r u j a n a _ h a c k a t h o n 2 0 2 6 _ H i s a a b H o s h i y a a r  
 