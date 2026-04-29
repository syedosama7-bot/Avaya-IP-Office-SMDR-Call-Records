Here’s a package you can deliver to stakeholders or clients – the **final folder structure** plus a **commercial‑ready technical write‑up** that describes the application’s value, capabilities, and architecture.

---

## 📁 Final Folder Structure

```
project/
├── app.py                  # App factory – initialises Flask and registers blueprints
├── config.py               # All configurable parameters (secret key, database path, ports)
├── extensions.py           # Flask‑Login initialisation
├── utils.py                # Shared helper: apply_user_filter
├── models/
│   ├── __init__.py
│   ├── database.py         # Database initialisation, connection helper
│   ├── call.py             # Call record queries (insert, fetch, summary)
│   ├── user.py             # User CRUD (create, read, update, delete)
│   └── tariff.py           # Tariff table queries
├── services/
│   ├── smdr_parser.py      # Parses raw SMDR strings and stores them
│   └── smdr_listener.py    # TCP server that receives SMDR streams from Avaya
├── blueprints/
│   ├── auth.py             # Login, logout, admin decorator, user management
│   ├── dashboard.py        # Main dashboard, API endpoints, raw debug
│   ├── reports.py          # Reporting engine (10+ report types)
│   └── export.py           # CSV/PDF export for calls and reports
├── templates/              # Jinja2 HTML templates
│   ├── index.html
│   ├── login.html
│   ├── report_view.html
│   ├── reports.html
│   ├── users.html
│   └── edit_user.html
├── run.py                  # Entry point – runs the Flask app
└── requirements.txt        # Python dependencies
```

---

## 📄 Commercial Technical Functionality Write‑up

# Avaya IP Office SMDR Dashboard  
*Enterprise‑grade call logging, reporting, and analytics platform*

---

## Overview

The **Avaya CDR Dashboard** is a full‑stack web application that captures, stores, and visualises **Station Message Detail Recording (SMDR)** data from Avaya IP Office systems. It provides a modern, real‑time dashboard, a comprehensive reporting centre, and multi‑user access with role‑based security. The system is installed on‑premises, requires no external cloud services, and runs on any Windows or Linux machine with Python 3.

---

## Key Features

### 🔴 Real‑Time Call Monitoring
- TCP listener on a configurable port (default 9001) receives SMDR streams directly from the IP Office.
- Parses all 30+ SMDR fields immediately upon arrival.
- Auto‑refresh dashboard updates every 10 seconds without manual reload.

### 📊 Customisable Dashboard
- **Summary Cards** – total calls, total talk time, average duration, total ring/hold time, total cost.
- **Filter Panel** – date range, direction (Inbound/Outbound), call type (Internal/External), and free‑text search.
- **Configurable Call Volume Chart** – choose from last 24 hours / 7 days / 30 days / 3 months / 1 year, with hourly, daily, monthly, or yearly grouping.
- **Dark/Light Mode** – user preference saved in browser.

### 📈 Reporting Centre (10+ Reports)
- Daily Call Summary  
- Top Callers / Top Called Numbers  
- Hourly Distribution (Busiest hour)  
- Cost by Tariff Prefix (month/year input)  
- Extension Usage Summary (date range + extension filter)  
- Longest Ring Times (Answer SLA)  
- Abandoned / Short Calls  
- Call Heatmap (Day of Week vs Hour)  
- Trunk Usage  
- Period Comparison (side‑by‑side two custom periods)

All reports display in a responsive table and can be **exported as CSV or PDF** with a single click.

### 📥 Export Capabilities
- Export the **current call list** (filtered) to CSV or PDF.
- Every report supports CSV and PDF download, preserving the selected filters.

### 🔐 Multi‑User Authentication & Access Control
- **Login system** with hashed passwords (Werkzeug).
- **Roles** – `admin` and `viewer`.
  - Admins see all data, manage users, and access raw SMDR logs.
  - Viewers are restricted to their assigned extension (calls they sent or received).
- Admin can add, edit (password/role/extension), and delete users via a web interface.

### 🧱 Modular & Maintainable Architecture
- Well‑structured codebase (blueprints, models, services) for easy maintenance and further development.
- Configurable via a single `config.py` file (secret key, database path, ports).
- SMDR collector runs independently from the web server in a background thread.

---

## Technical Architecture

| Component | Technology |
|-----------|------------|
| Backend | Python 3, Flask, Flask‑Login |
| Database | SQLite (single file, zero‑setup) |
| Frontend | Bootstrap 5, Chart.js, plain JavaScript (AJAX) |
| PDF Generation | ReportLab |
| Authentication | Werkzeug password hashing, Flask‑Login sessions |
| Real‑time Data Ingestion | TCP socket listener (multi‑record batch processing) |

The application follows an **MVC‑like** separation:  
- **Models/** – direct SQLite access for calls, users, tariffs.  
- **Blueprints/** – route handlers for dashboard, reports, exports, authentication.  
- **Services/** – background SMDR listener and parser.  
- **Utils/** – shared helper functions.

---

## Deployment

1. Install Python 3.8+ and required packages (`pip install -r requirements.txt`).
2. Configure Avaya IP Office to send SMDR to the machine’s IP on port 9001 (TCP client mode).
3. Run `python run.py` – the web dashboard becomes available at `http://<server_ip>:5000`.
4. Default admin credentials: `admin` / `admin123` (change immediately).

The database (`smdr_records.db`) is created automatically in the project folder. Historical records are retained permanently with no size limit – SQLite handles millions of records efficiently.

---

## Security

- All routes are protected by `@login_required`.
- Admin‑restricted functions (`/raw`, user management, etc.) are enforced by a custom decorator.
- Passwords are hashed with Werkzeug’s `generate_password_hash`.
- Users cannot delete themselves.
- Session secret key is configurable for production.

---

## Customisation & Scaling

- Tariff prefixes can be added directly in the database (or via a simple UI – can be added on request).
- The report engine can be extended by adding a new `elif` branch in `blueprints/reports.py` and a card in `reports.html`.
- For higher load, SQLite can be replaced with PostgreSQL/MySQL by swapping the `models/database.py` layer.
- The application can be containerised with Docker for easier distribution.

---

## Summary

The Avaya CDR Dashboard transforms raw SMDR records into a **clear, actionable, and secure web interface**. It replaces spreadsheets and manual log inspection with a professional, real‑time tool that helps organisations monitor call activity, control costs, and improve telecommunications management.
