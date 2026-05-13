Here's the updated project structure and technical write‑up reflecting all the enhancements we've made.

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
│   ├── database.py            # Database initialisation & migration (calls, users, settings, email_log, subscriptions)
│   ├── call.py                # Call record queries (fetch, summary, pagination)
│   ├── user.py                # User CRUD, session management, email preferences
│   ├── tariff.py              # Tariff table queries
│   ├── audit.py               # Audit trail logic
│   └── settings.py            # System settings, PABX servers, SMTP configuration
├── services/
│   ├── smdr_parser.py         # Raw SMDR string parsing & database insertion (30+ fields)
│   ├── smdr_listener.py       # TCP server – enforces allowed PABX IPs & updates live status
│   ├── backup_scheduler.py    # Automatic recurring backup (daily/weekly/monthly)
│   ├── pabx_monitor.py        # Periodic connectivity checker (configurable monitor port)
│   ├── email_sender.py        # Universal SMTP sender (supports STARTTLS, SSL, certificate toggle, presets)
│   └── email_scheduler.py     # Background thread – automatically sends scheduled report emails
├── blueprints/
│   ├── auth.py                # Login, logout, admin decorator, user management, settings, audit, maintenance,
│   │                          #   my preferences, manual email, schedule management, live PABX ping, SMTP status
│   ├── dashboard.py           # Main dashboard, API endpoints, call volume, breakdown charts, connection status
│   ├── reports.py             # Reporting engine (25+ report types, pagination, filter-aware)
│   └── export.py              # CSV & PDF export for calls and reports, internal report generator
├── static/
│   └── js/
│       └── call_journey_diagram.js   # D3.js diagram for visual call journey (3D, transfer detection)
├── templates/
│   ├── base.html              # Common layout (sidebar, top bar, footer, theme toggle)
│   ├── index.html             # Main dashboard (gradient cards, skeleton loading, chart gradients)
│   ├── login.html             # Polished login page (animated background, glass card)
│   ├── report_view.html       # Generic report viewer (export, pagination, filter badges, sticky headers)
│   ├── reports.html           # Reporting centre (categorised, searchable, email buttons per card)
│   ├── system_status.html     # Live PABX & SMTP connectivity, system health (CPU, memory, disk)
│   ├── settings.html          # System & SMTP configuration (presets, protocol, certificate toggle)
│   ├── maintenance.html       # Backup/restore, logs, restart
│   ├── users.html             # User management (email status, schedule button)
│   ├── edit_user.html         # Edit user (role, extension, email, enable/disable email features)
│   ├── change_password.html
│   ├── my_preferences.html    # Self‑service email settings
│   ├── user_schedule.html     # Admin schedules per user (daily/weekly/monthly + filters)
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

**Enterprise‑grade call logging, reporting, analytics, and automated email delivery platform**

---

## Overview

The **Avaya Call Records Dashboard** is a full‑stack, on‑premises web application that captures, stores, and visualises **Station Message Detail Recording (SMDR)** data from **Avaya IP Office** systems. It transforms raw SMDR records into a secure, real‑time, and actionable dashboard with a comprehensive reporting centre, multi‑user role‑based access, complete audit trail, multi‑site PABX monitoring, and an **advanced email subsystem** for scheduled report delivery and instant alerts – all from a single, self‑contained server.

The solution is designed for telecom administrators, business managers, managed‑service providers, and compliance officers who need instant insight into call activity, cost control, system health, and automated distribution of intelligence.

---

## Key Features

### 🔴 Real‑Time Call Monitoring
- Dedicated TCP listener (configurable port) receives SMDR streams directly from one or multiple IP Office systems.
- Only authorised IP addresses are accepted (configured per PABX).
- All 30+ SMDR fields are parsed immediately and stored in a high‑performance SQLite database.
- The dashboard auto‑refreshes every 10 seconds, displaying the latest call records without manual reload.

### 📊 Customisable Dashboard
- **Summary Cards** – total calls, total talk time, average duration, ring/hold time, total cost (all filterable, with gradient backgrounds).
- **Filter Panel** – date range, direction, call type, and free‑text search.
- **Configurable Call Volume Chart** – last 24h / 7d / 30d / 3m / 1y, grouped by hour, day, month, or year, with gradient fill.
- **Breakdown Doughnut Chart** – dynamically switch between Direction, Call Type, Top Callers, Top Called, and Trunk Usage, respecting active filters.
- **Dark / Light Mode** – user preference saved in browser.
- **Live Connection Status Bar** – shows connectivity per PABX (green/red), updates every 5 seconds.
- **Skeleton Loading** – modern loading placeholders for a polished UX.

### 📈 Reporting Centre (25+ Reports)
- **Daily Call Summary** – pick a single date.
- **Top Callers / Top Called Numbers** – ranking by call volume and cost, with date range filters.
- **Hourly Distribution (Busiest Hour)** – single‑day view.
- **Cost by Tariff Prefix** – month/year input.
- **Extension Usage Summary** – date range + comma‑separated extension(s).
- **Longest Ring Times** – answer SLA monitoring.
- **Abandoned / Short Calls** – zero‑duration or unanswered calls.
- **Call Heatmap** – day‑of‑week vs hour matrix (day names, not numbers).
- **Trunk Usage** – calls per trunk line.
- **Trunk Peak Utilisation** – peak concurrent calls per trunk and hour.
- **Period Comparison** – side‑by‑side two custom periods.
- **Detail Call Records** – full SMDR table with pagination, including forwarding cause, authorisation status, and multi‑leg flag.
- **Call Journey** – visual timeline (D3.js) of a single call's entire lifecycle, with transfer highlighting, icons, and descriptions.
- **Call Duration Distribution** – histogram buckets.
- **Abandoned Call Trend** – daily abandoned calls over time.
- **Caller Profile** – activity summary for a specific external number.
- **Extension Activity Scorecard** – per‑extension score based on calls and talk time.
- **Call Outcome Summary** – answered, abandoned, voicemail breakdown.
- **Authorization Code Audit** – every call with authorisation status (valid/invalid) and code.
- **Forwarding & Redirect Analysis** – who is forwarding externally, to which number, and why (Unconditional, Hunt Group, etc.).
- **Hunt Group Activity** – calls routed through hunt groups and the agents involved.
- **Conferenced Calls** – all calls involving a conference bridge.
- **And many more** – all exportable as CSV or PDF.

Every report supports **pagination** and shows the exact filters applied (date, direction, call type, search, etc.).

### 📥 Export Capabilities
- Export the current call list (filtered) to CSV or PDF.
- Every report supports CSV and PDF download with applied filters.
- No row limit on exports – all matching records are included.
- Exports carry the company brand, report name, filter description, and exporter identity.

### 📧 Advanced Email Subsystem
- **Manual Email** – one‑click email PDF/CSV from any report viewer (visible only to users with email rights).
- **Scheduled Reports** – admin configures per‑user subscriptions (daily/weekly/monthly + time + filters).
- **Background Scheduler** – a dedicated thread checks every minute and delivers reports automatically.
- **Email Alerts (ready to enable)** – alert subscriptions for PABX offline, high abandon rate, etc. (infrastructure in place).
- **SMTP Configuration** – preset providers (Gmail, Office365, Yahoo), protocol selector (STARTTLS/SSL/None), certificate verification toggle, and a Test Email button.
- All emails are logged in the database for audit.

### 🔐 Multi‑User Authentication & Access Control
- **Flask‑Login**‑based authentication with hashed passwords.
- **Roles** – `admin` and `viewer`.
- Admins see all data, manage users, configure system settings, view all reports & audit logs, and access raw SMDR data.
- Viewers are restricted to their assigned extension (calls they sent or received). They can change their own password and manage their email preferences.
- Admin can **add, edit, and delete users** via a clean web interface, and **enable/disable email reports & alerts** per user.

### 🛡️ Audit Trail (Admin Only)
- Records every critical action: login, logout, password change, user management, settings update, report generation, and export.
- Logs include **timestamp, username, action description, and IP address**.
- Paginated viewer (50 per page) with CSV download.
- Automatic purging of oldest entries when count exceeds 100,000.

### ⚙️ Self‑Service & Configurability
- **Password Change** – all users can independently change their password (with confirmation).
- **My Preferences** – users set their email address and enable/disable reports & alerts.
- **Admin Settings** – configurable SMDR listener, web interface, company branding, SMTP email settings, PABX server list, online timeout, monitor interval, and monitor port.
- **Backup Scheduler** – set a recurring backup path and interval (daily/weekly/monthly). Manual backup & restore also available.
- **System Maintenance** – download/restore database & configuration, view/download application logs, restart application.

### 🖥️ Multi‑Site PABX Management
- Add multiple IP Office servers via **Settings** with a friendly name, IP address, and monitor port.
- Only configured IPs are allowed to send SMDR data – automatic rejection of unauthorised sources.
- **Dedicated System Status page** shows online/offline status for each PABX, SMTP connectivity, and system health (CPU, memory, disk, uptime).
- **Live Connectivity Check** – a “Verify PABX Now” button pings the selected port in real time.
- Background **connectivity monitor** pings each PABX on its **configurable monitor port** at configurable intervals, ensuring accurate status even when no calls are occurring.

### 🧱 Modular Architecture & Maintainability
- Well‑structured codebase following **MVC‑like** separation:
  - **Models/** – direct SQLite access for calls, users, tariffs, settings, audit logs, email logs, subscriptions.
  - **Blueprints/** – route handlers for dashboard, reports, exports, authentication, audit, email, scheduling.
  - **Services/** – background SMDR listener, parser, backup scheduler, PABX monitor, email sender, email scheduler.
  - **Utils/** – shared helper functions.
- Easily extendable – new report types require only an additional `elif` branch and a card in `reports.html`.
- Configurable via a single `config.py` file; sensitive data can be moved to environment variables.
- Cross‑platform system health monitoring with `psutil` (fallback to built‑in tools).

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
| Email Delivery | smtplib + SSL/TLS, presets for popular providers, certificate handling |
| Background Scheduling | Python threading (backup, email, monitor) |

The application is deployed on‑premises and requires **no external cloud services**. It runs on any Windows, Linux, or macOS machine with Python 3.8+.

---

## Deployment

1. Install Python 3.8+ and required packages (`pip install -r requirements.txt`).
2. Configure each Avaya IP Office to send SMDR to the machine's IP on the configured port (default 9001).
3. Run `python run.py` – the web dashboard becomes available at `http://<server_ip>:5000`.
4. Default admin credentials: `admin` / `admin123` (change immediately).
5. Add each IP Office's name and IP address in **Settings → PABX Servers**.
6. Set up SMTP in **Settings → Email Configuration** (use a preset or custom server).
7. Enable email reports for users and configure schedules via **User Management**.
8. The SQLite database (`smdr_records.db`) is created automatically in the project folder. Historical records are retained permanently with no size limit.

---

## Security

- All routes are protected by `@login_required`; admin‑restricted functions are enforced by a custom decorator.
- Passwords are hashed with Werkzeug's `generate_password_hash`.
- Users cannot delete themselves.
- The audit trail provides full accountability for every administrative action.
- The session secret key is configurable for production environments.
- Only authorised IP addresses can send SMDR data – unauthorised connections are rejected and logged.
- SMTP certificate verification can be toggled for internal/self‑signed servers.

---

## Performance & Scalability

- SQLite can hold **140 TB** of data, enough for decades of typical call volume.
- For 10,000 calls per day, yearly storage is approximately **0.9 GB**.
- Background threads (listener, monitor, backup, email scheduler) run independently without blocking the web server.
- The application can be containerised with Docker for easier orchestration.
- For higher load, SQLite can be replaced with PostgreSQL/MySQL by swapping the `models/database.py` layer.

---

## Licensing & Commercialisation

The application's architecture supports **perpetual** and **subscription‑based licensing** with minimal changes:

- A license key validation module can be added via a `license.py` file that verifies a digitally‑signed JSON (ECDSA or HMAC).
- Feature tiers (Starter, Professional, Enterprise) can restrict access to certain reports, multi‑user roles, email scheduling, or export capabilities.
- Hardware binding (fingerprinting) ensures licenses cannot be transferred between servers.

---

## Summary

The Avaya Call Records Dashboard transforms raw SMDR records into a **clear, actionable, secure, and automated web interface**. It replaces spreadsheets and manual log inspection with a professional, real‑time tool that helps organisations:

- Monitor call activity across multiple sites,
- Control telecommunications costs,
- Improve customer service through detailed call journey analysis,
- Ensure regulatory compliance with a tamper‑proof audit trail,
- Collaborate securely with role‑based access,
- Automate report distribution and receive instant alerts.

Its modular design, comprehensive reporting, multi‑site management, and advanced email capabilities make it an excellent foundation for both internal use and commercial productisation.
