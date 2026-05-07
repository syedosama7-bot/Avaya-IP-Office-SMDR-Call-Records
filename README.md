Below is the **final project structure** and a **professional technical write‑up** suitable for stakeholders, clients, or your GitHub repository.

---

## 📁 Final Project Folder Structure

```
project/
├── app.py                     # App factory – initializes Flask, registers all blueprints & services
├── config.py                  # Environment‑based configuration
├── extensions.py              # Flask‑Login initialisation
├── utils.py                   # Shared helper: apply_user_filter
├── models/
│   ├── __init__.py
│   ├── database.py            # Database initialisation & migration
│   ├── call.py                # Call record queries (fetch, summary, pagination)
│   ├── user.py                # User CRUD & session management
│   ├── tariff.py              # Tariff table queries
│   ├── audit.py               # Audit trail logic
│   └── settings.py            # System settings & PABX server management
├── services/
│   ├── smdr_parser.py         # Raw SMDR string parsing & database insertion
│   ├── smdr_listener.py       # TCP server – enforces allowed PABX IPs & updates live status
│   ├── backup_scheduler.py    # Automatic recurring backup (daily/weekly/monthly)
│   └── pabx_monitor.py        # Periodic connectivity checker (configurable interval)
├── blueprints/
│   ├── auth.py                # Login, logout, admin decorator, user management, settings, audit, maintenance
│   ├── dashboard.py           # Main dashboard, API endpoints, call volume, breakdown charts, connection status
│   ├── reports.py             # Reporting engine (20+ report types including call journey, duration distribution, etc.)
│   └── export.py              # CSV & PDF export for calls and reports
├── static/
│   └── js/
│       └── call_journey_diagram.js   # D3.js diagram for visual call journey
├── templates/
│   ├── index.html             # Main dashboard
│   ├── login.html
│   ├── report_view.html       # Generic report viewer with export & pagination
│   ├── reports.html           # Reporting centre
│   ├── system_status.html     # Live PABX connectivity status
│   ├── settings.html          # System & PABX configuration
│   ├── maintenance.html       # Backup/restore, logs, restart
│   ├── users.html             # User management (admin)
│   ├── edit_user.html
│   ├── change_password.html
│   ├── audit.html             # Audit trail viewer (paginated)
│   ├── active_sessions.html   # Force logout active users
│   └── ... (additional template files)
├── logs/                      # Rotating application logs (avaya_cdr.log)
├── run.py                     # Entry point
├── requirements.txt
└── README.md                  # This commercial write‑up
```

---

# Avaya Call Records Dashboard  
**Enterprise‑grade call logging, reporting, and analytics platform**

---

## Overview

The **Avaya Call Records Dashboard** is a full‑stack, on‑premises web application that captures, stores, and visualises **Station Message Detail Recording (SMDR)** data from **Avaya IP Office** systems. It transforms raw SMDR records into a secure, real‑time, and actionable dashboard with a comprehensive reporting centre, multi‑user role‑based access, complete audit trail, and multi‑site PABX monitoring – all from a single, self‑contained server.

The solution is designed for telecom administrators, business managers, managed‑service providers, and compliance officers who need instant insight into call activity, cost control, and system health.

---

## Key Features

### 🔴 Real‑Time Call Monitoring
- Dedicated TCP listener (configurable port) receives SMDR streams directly from one or multiple IP Office systems.
- Only authorised IP addresses are accepted (configured per PABX).
- All 30+ SMDR fields are parsed immediately and stored in a high‑performance SQLite database.
- The dashboard auto‑refreshes every 10 seconds, displaying the latest call records without manual reload.

### 📊 Customisable Dashboard
- **Summary Cards** – total calls, total talk time, average duration, ring/hold time, total cost (all filterable).
- **Filter Panel** – date range, direction, call type, and free‑text search.
- **Configurable Call Volume Chart** – last 24h / 7d / 30d / 3m / 1y, grouped by hour, day, month, or year.
- **Breakdown Doughnut Chart** – dynamically switch between Direction, Call Type, Top Callers, Top Called, and Trunk Usage, respecting active filters.
- **Dark / Light Mode** – user preference saved in browser.
- **Live Connection Status Bar** – shows connectivity per PABX (green/red), updates every 5 seconds.

### 📈 Reporting Centre (20+ Reports)
- **Daily Call Summary** – pick a single date.
- **Top Callers / Top Called Numbers** – ranking by call volume and cost.
- **Hourly Distribution (Busiest Hour)** – single‑day view.
- **Cost by Tariff Prefix** – month/year input.
- **Extension Usage Summary** – date range + comma‑separated extension(s).
- **Longest Ring Times** – answer SLA monitoring.
- **Abandoned / Short Calls** – zero‑duration or unanswered calls.
- **Call Heatmap** – day‑of‑week vs hour matrix.
- **Trunk Usage** – calls per trunk line.
- **Trunk Peak Utilisation** – peak concurrent calls per trunk and hour.
- **Period Comparison** – side‑by‑side two custom periods.
- **Detail Call Records** – full SMDR table with pagination.
- **Call Journey** – visual timeline (D3.js) of a single call’s entire lifecycle, including transfers, pauses, and voicemail.
- **Call Duration Distribution** – histogram buckets.
- **Abandoned Call Trend** – daily abandoned calls over time.
- **Caller Profile** – activity summary for a specific external number.
- **Extension Activity Scorecard** – per‑extension score based on calls and talk time.
- **Call Outcome Summary** – answered, abandoned, voicemail breakdown.
- **And many more** – all exportable as CSV or PDF.

### 📥 Export Capabilities
- Export the current call list (filtered) to CSV or PDF.
- Every report supports CSV and PDF download with applied filters.
- No row limit on exports – all matching records are included.

### 🔐 Multi‑User Authentication & Access Control
- **Flask‑Login**‑based authentication with hashed passwords.
- **Roles** – `admin` and `viewer`.
  - Admins see all data, manage users, configure system settings, view all reports & audit logs, and access raw SMDR data.
  - Viewers are restricted to their assigned extension (calls they sent or received). They can change their own password.
- Admin can **add, edit, and delete users** via a clean web interface.

### 🛡️ Audit Trail (Admin Only)
- Records every critical action: login, logout, password change, user management, settings update, report generation, and export.
- Logs include **timestamp, username, action description, and IP address**.
- Paginated viewer (50 per page) with CSV download.
- Automatic purging of oldest entries when count exceeds 100,000.

### ⚙️ Self‑Service & Configurability
- **Password Change** – all users can independently change their password (with confirmation).
- **Admin Settings** – configurable SMDR listener port, web interface host/port, PABX server list, online timeout, and check interval.
- **Backup Scheduler** – set a recurring backup path and interval (daily/weekly/monthly). Manual backup & restore also available.
- **System Maintenance** – download/restore database & configuration, view/download application logs, restart application.

### 🖥️ Multi‑Site PABX Management
- Add multiple IP Office servers via **Settings** with a friendly name and IP address.
- Only configured IPs are allowed to send SMDR data – automatic rejection of unauthorised sources.
- **Dedicated System Status page** shows online/offline status for each PABX, updating every few seconds.
- Background **connectivity monitor** pings each PABX on its SMDR port at configurable intervals, ensuring accurate status even when no calls are occurring.

### 🧱 Modular Architecture & Maintainability
- Well‑structured codebase following **MVC‑like** separation:  
  - **Models/** – direct SQLite access for calls, users, tariffs, settings, audit logs.  
  - **Blueprints/** – route handlers for dashboard, reports, exports, authentication, audit.  
  - **Services/** – background SMDR listener, parser, backup scheduler, PABX monitor.  
  - **Utils/** – shared helper functions.
- Easily extendable – new report types require only an additional `elif` branch and a card in `reports.html`.
- Configurable via a single `config.py` file; sensitive data can be moved to environment variables.

---

## Technical Architecture

| Component | Technology |
|-----------|------------|
| Backend | Python 3.10+, Flask, Flask‑Login |
| Database | SQLite 3 (single file, zero‑setup, 140 TB max) |
| Frontend | Bootstrap 5, Chart.js, D3.js, vanilla JavaScript (AJAX) |
| PDF Generation | ReportLab |
| Authentication | Werkzeug password hashing, Flask‑Login sessions |
| Real‑time Data Ingestion | TCP socket listener (multi‑record batch processing) |
| Connectivity Monitoring | Active TCP ping to each configured PABX |

The application is deployed on‑premises and requires **no external cloud services**. It runs on any Windows, Linux, or macOS machine with Python 3.8+.

---

## Deployment

1. Install Python 3.8+ and required packages (`pip install -r requirements.txt`).
2. Configure each Avaya IP Office to send SMDR to the machine’s IP on the configured port (default 9001).
3. Run `python run.py` – the web dashboard becomes available at `http://<server_ip>:5000`.
4. Default admin credentials: `admin` / `admin123` (change immediately).
5. Add each IP Office’s name and IP address in **Settings → PABX Servers**.

The SQLite database (`smdr_records.db`) is created automatically in the project folder. Historical records are retained permanently with no size limit – SQLite handles hundreds of millions of records efficiently.

---

## Security

- All routes are protected by `@login_required`; admin‑restricted functions are enforced by a custom decorator.
- Passwords are hashed with Werkzeug’s `generate_password_hash`.
- Users cannot delete themselves.
- The audit trail provides full accountability for every administrative action.
- The session secret key is configurable for production environments.
- Only authorised IP addresses can send SMDR data – unauthorised connections are rejected and logged.

---

## Performance & Scalability

- SQLite can hold **140 TB** of data, enough for decades of typical call volume.
- For 10,000 calls per day, yearly storage is approximately **0.9 GB**.
- The application can be containerised with Docker for easier orchestration.
- For higher load, SQLite can be replaced with PostgreSQL/MySQL by swapping the `models/database.py` layer.

---

## Licensing & Commercialisation

The application’s architecture supports **perpetual** and **subscription‑based licensing** with minimal changes:
- A license key validation module can be added via a `license.py` file that verifies a digitally‑signed JSON (ECDSA or HMAC).
- Feature tiers (Starter, Professional, Enterprise) can restrict access to certain reports, multi‑user roles, or export capabilities.
- Hardware binding (fingerprinting) ensures licenses cannot be transferred between servers.

---

## Summary

The Avaya Call Records Dashboard transforms raw SMDR records into a **clear, actionable, and secure web interface**. It replaces spreadsheets and manual log inspection with a professional, real‑time tool that helps organisations:

- Monitor call activity across multiple sites,
- Control telecommunications costs,
- Improve customer service through detailed call journey analysis,
- Ensure regulatory compliance with a tamper‑proof audit trail,
- Collaborate securely with role‑based access.

Its modular design, comprehensive reporting, and full multi‑site management make it an excellent foundation for both internal use and commercial productisation.
