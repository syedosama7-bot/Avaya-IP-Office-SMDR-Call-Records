Your project has grown into a fully‑fledged, commercially‑viable telephony analytics platform. Below is the **final folder structure** and a **professional technical write‑up** suitable for proposals, stakeholder presentations, or your GitHub README.

---

## 📁 Final Folder Structure

```
project/
├── app.py                  # App factory – initialises Flask, registers blueprints, starts SMDR listener
├── config.py               # All configurable parameters (secret key, database path, ports)
├── extensions.py           # Flask‑Login initialisation
├── utils.py                # Shared helper: apply_user_filter
├── models/
│   ├── __init__.py
│   ├── database.py         # Database initialisation (calls, tariffs, users, settings, audit_log)
│   ├── call.py             # Call record queries (insert, fetch, summary)
│   ├── user.py             # User CRUD (create, read, update, delete, password reset)
│   ├── tariff.py           # Tariff table queries
│   ├── audit.py            # Audit log insertion helper
│   └── settings.py         # Configurable SMDR/Web port persistence
├── services/
│   ├── smdr_parser.py      # Parses raw SMDR strings and stores them
│   └── smdr_listener.py    # TCP server, maintains connection status for UI
├── blueprints/
│   ├── auth.py             # Login, logout, admin decorator, user management, settings, audit view
│   ├── dashboard.py        # Main dashboard, API endpoints, raw debug, call volume, breakdown
│   ├── reports.py          # Reporting engine (10+ report types)
│   └── export.py           # CSV/PDF export for calls and reports
├── templates/              # Jinja2 HTML templates
│   ├── index.html          # Main dashboard (with charts, status bar, audit link)
│   ├── login.html
│   ├── report_view.html
│   ├── reports.html        # Reporting centre (with per‑report filters)
│   ├── users.html          # Admin user management (list, add, delete, edit)
│   ├── edit_user.html      # Edit user form (password, role, extension)
│   ├── change_password.html # Self‑service password change
│   ├── audit.html          # Admin audit log viewer
│   └── settings.html       # Admin settings (SMDR/web port configuration)
├── run.py                  # Entry point – runs the Flask app
└── requirements.txt        # Python dependencies
```

---

## 📄 Commercial Technical Functionality Write‑up

# Avaya Call Records Dashboard  
*Enterprise‑grade call logging, reporting, and analytics platform*

---

## Overview

The **Avaya CDR Dashboard** is a full‑stack, on‑premises web application that captures, stores, and visualises **Station Message Detail Recording (SMDR)** data from **Avaya IP Office** systems. It transforms raw SMDR records into a secure, real‑time, and actionable dashboard with a comprehensive reporting centre, multi‑user role‑based access, and complete audit trail. The solution is designed for telecom administrators, business managers, and managed‑service providers who need instant insight into call activity, cost control, and compliance.

---

## Key Features

### 🔴 Real‑Time Call Monitoring
- A dedicated TCP listener (configurable port, default 9001) receives SMDR streams directly from the IP Office.
- All 30+ SMDR fields are parsed immediately and stored in an SQLite database.
- The dashboard auto‑refreshes every 10 seconds, displaying the latest call records without manual reload.

### 📊 Customisable Dashboard
- **Summary Cards** – total calls, total talk time, average duration, total ring/hold time, total cost (all filterable).
- **Filter Panel** – date range, direction (Inbound/Outbound), call type (Internal/External), and free‑text search.
- **Configurable Call Volume Chart** – choose from last 24 hours / 7 days / 30 days / 3 months / 1 year, with hourly, daily, monthly, or yearly grouping.
- **Breakdown Doughnut Chart** – dynamically switch between Direction, Call Type, Top Callers, Top Called Numbers, and Trunk Usage, all respecting active filters.
- **Dark/Light Mode** – user preference saved in browser.
- **Live Connection Status Bar** – displays the IP Office connection state, IP address, and last‑seen timestamp; updates every 5 seconds.

### 📈 Reporting Centre (10+ Reports)
- **Daily Call Summary** – pick a single date.
- **Top Callers / Top Called Numbers** – ranking by call volume and cost.
- **Hourly Distribution (Busiest Hour)** – single‑day view.
- **Cost by Tariff Prefix** – month/year input, utilises configurable tariff table.
- **Extension Usage Summary** – date range + comma‑separated extension(s).
- **Longest Ring Times** – answer SLA monitoring.
- **Abandoned / Short Calls** – zero‑duration or unanswered calls.
- **Call Heatmap** – day‑of‑week vs hour matrix.
- **Trunk Usage** – calls per trunk line.
- **Period Comparison** – side‑by‑side comparison of two custom date ranges.

All reports can be **exported as CSV or PDF** with a single click, including the currently filtered call list.

### 📥 Export Capabilities
- Export the **current call list** (filtered) to CSV or PDF, preserving date range, direction, call type, and search.
- Every report supports CSV and PDF download with applied filters.

### 🔐 Multi‑User Authentication & Access Control
- **Flask‑Login**‑based authentication with hashed passwords (Werkzeug).
- **Roles** – `admin` and `viewer`.
  - Admins see all data, manage users, configure system settings, view audit logs, and access raw SMDR data.
  - Viewers are restricted to their assigned extension (calls they sent or received). They can change their own password.
- Admin can **add, edit (password/role/extension), and delete users** via a clean web interface.

### 🛡️ Audit Trail (Admin Only)
- Records every critical action: login, logout, password change, user management, settings update, report generation, and export.
- Logs include **timestamp, username, action description, and IP address**.
- Accessible exclusively by admin users via a dedicated interface.

### ⚙️ Self‑Service & Configurability
- **Password Change** – all users can independently change their password (with confirmation).
- **Admin Settings** – configurable SMDR listener port, web interface host/port, stored persistently. Changes take effect after restart.

### 🧱 Modular Architecture & Maintainability
- Well‑structured codebase following **MVC‑like** separation:  
  - **Models/** – direct SQLite access for calls, users, tariffs, settings, audit logs.  
  - **Blueprints/** – route handlers for dashboard, reports, exports, authentication, audit.  
  - **Services/** – background SMDR listener and parser.  
  - **Utils/** – shared helper functions.
- Easily extendable – new report types require only an additional `elif` branch and a card in `reports.html`.
- Configurable via a single `config.py` file; sensitive data can be moved to environment variables.

---

## Technical Architecture

| Component | Technology |
|-----------|------------|
| Backend | Python 3, Flask, Flask‑Login |
| Database | SQLite 3 (single file, zero‑setup, 140 TB max) |
| Frontend | Bootstrap 5, Chart.js, vanilla JavaScript (AJAX) |
| PDF Generation | ReportLab |
| Authentication | Werkzeug password hashing, Flask‑Login sessions |
| Real‑time Data Ingestion | TCP socket listener with multi‑record batch processing |

The application is deployed on‑premises and requires no external cloud services. It runs on any Windows, Linux, or macOS machine with Python 3.8+.

---

## Deployment

1. Install Python 3.8+ and required packages (`pip install -r requirements.txt`).
2. Configure Avaya IP Office to send SMDR to the machine’s IP on port 9001 (TCP client mode).
3. Run `python run.py` – the web dashboard becomes available at `http://<server_ip>:5000` (or custom port if configured).
4. Default admin credentials: `admin` / `admin123` (change immediately).

The SQLite database (`smdr_records.db`) is created automatically in the project folder. Historical records are retained permanently with no size limit – SQLite handles hundreds of millions of records efficiently.

---

## Security

- All routes are protected by `@login_required`; admin‑restricted functions are enforced by a custom decorator.
- Passwords are hashed with Werkzeug’s `generate_password_hash`.
- Users cannot delete themselves.
- The audit trail provides full accountability for every administrative action.
- The session secret key is configurable for production environments.

---

## Customisation & Scaling

- Tariff prefixes can be managed via the admin interface or directly in the database.
- The reporting engine is easily extensible by adding a new report type in `blueprints/reports.py` and a corresponding card in `templates/reports.html`.
- For higher load, SQLite can be replaced with PostgreSQL/MySQL by swapping the `models/database.py` layer.
- The application can be containerised with Docker for easier distribution and orchestration.
- The frontend theme and visuals can be further customised using the provided CSS variables.

---

## Licensing & Commercialisation (Ready)

The application’s architecture supports **perpetual** and **subscription‑based licensing**:
- **License key validation** can be added via a simple `license.py` module that verifies a digitally‑signed JSON file (ECDSA or HMAC).
- **Feature tiers** (Starter, Professional, Enterprise) can restrict access to certain reports, multi‑user roles, or export capabilities.
- **Hardware binding** (fingerprinting) ensures licenses cannot be transferred between servers.
- A **14‑day free trial** mode is easily implemented by checking the database’s first‑use date.

---

## Summary

The Avaya CDR Dashboard transforms raw SMDR records into a **clear, actionable, and secure web interface**. It replaces spreadsheets and manual log inspection with a professional, real‑time tool that helps organisations monitor call activity, control costs, and improve telecommunications management. Its modular design, comprehensive reporting, and full audit trail make it an excellent foundation for both internal use and commercial productisation.
