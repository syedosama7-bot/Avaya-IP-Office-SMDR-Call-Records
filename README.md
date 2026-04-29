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
