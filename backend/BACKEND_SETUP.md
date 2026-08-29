# FastAPI Backend Setup Guide (VFF IMS)

This guide provides instructions for setting up the backend services to integrate with the VFF IMS Frontend.

## Recommended Tech Stack
- **Framework**: FastAPI (Python 3.10+)
- **Database**: PostgreSQL
- **ORM**: SQLAlchemy or Tortoise ORM
- **Auth**: JWT (OAuth2 with Password Flow)

## Project Structure

```text
ims-backend/
├── app/
│   ├── api/                # API Endpoints
│   │   ├── v1/
│   │   │   ├── auth.py
│   │   │   ├── hr.py
│   │   │   ├── finance.py
│   │   │   └── inventory.py
│   ├── core/               # Configuration & Security
│   │   ├── config.py
│   │   └── security.py
│   ├── models/             # Database Schemas (SQLAlchemy)
│   ├── schemas/            # Pydantic Schemas (Validation)
│   ├── crud/               # Database Operations
│   └── main.py             # FastAPI App Entrypoint
├── migrations/             # Alembic Migrations
├── requirements.txt
└── .env
```

## Basic Installation

Run everything below from the `backend/` directory. The virtual environment
belongs at `backend/venv` — do not create one at the repository root, or you
will end up with two interpreters and dependencies installed into the wrong
one. Python 3.12 is required; some dependencies do not yet build on 3.14.

1. Create a virtual environment:

   **macOS / Linux**
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   ```

   **Windows (PowerShell)**
   ```powershell
   py -3.12 -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2. Install dependencies from the pinned list rather than by hand, so every
   environment matches:
   ```bash
   pip install -r requirements.txt
   ```
   For test and lint tooling as well: `pip install -r requirements-dev.txt`

3. Run the development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   Interactive API docs are then at `http://localhost:8000/docs`.

### Troubleshooting

- **`ModuleNotFoundError: No module named 'app'`** — you are not in the
  `backend/` directory. `uvicorn` resolves `app.main` relative to the current
  working directory.
- **A module is missing even though you installed it** — you are likely running
  a different interpreter than the one you installed into. Check with
  `python -c "import sys; print(sys.executable)"`; it should be inside
  `backend/venv`.

## Key API Endpoints to Implement

### Auth
- `POST /api/v1/auth/login` -> Returns JWT token & User Role.

### HR
- `GET /api/v1/hr/employees` -> List of employees.
- `GET /api/v1/hr/attendance?date={date}` -> Daily logs.
- `PATCH /api/v1/hr/attendance/lock` -> Logic: prevents edits to logs for {date}.

### Finance
- `GET /api/v1/finance/transactions` -> List of income/expenses.
- `GET /api/v1/finance/summary` -> Aggregates: Cash Available, Receivables.

### Audit
- `POST /api/v1/admin/audit` -> Logger middleware to capture user actions.

## Integration Config
The frontend is configured to point to `/api` by default. Update `NEXT_PUBLIC_API_URL` in `.env.local` to point to your FastAPI server (e.g., `http://localhost:8000`).
