# VFF Integrated Management System (IMS)

The internal management system for Vets For Future (VFF), plus its public website. Staff use it for HR and payroll, finance, inventory, programs and clinics, rescue cases and dispatch, and volunteers. The public side has the homepage, case reporting, volunteer sign-up, donations and an outbreak map. Every change to money, people or stock is written to a tamper-evident audit log, and each role only sees the modules it needs.

CSC3213 Group C project.

## Tech stack

| Part | Uses |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4 with shadcn/ui, TanStack Query, Zustand, Recharts, Leaflet |
| Backend | FastAPI on Python 3.12 |
| Database and auth | Supabase (PostgreSQL, Auth, Realtime) |
| External services | An OpenAI-compatible LLM (Google Gemini by default), OpenRouteService, Brevo email, PayHere sandbox |

```text
CSC3213_20_Group_C/
├── backend/
│   ├── app/            FastAPI app: api/ (routes), schemas/, services/, core/ (config, permissions, audit)
│   ├── db/             init.sql, numbered migrations, holiday CSVs
│   ├── scripts/        seed and diagnostic scripts
│   └── tests/          pytest suite
├── frontend/
│   └── src/            app/ (pages), components/, hooks/, services/ (API calls), lib/, types/
└── features/           Gherkin feature specs
```

## Prerequisites

- **Python 3.12.** Some dependencies don't build on 3.13 or 3.14 yet.
- **Node.js 20.9 or newer** (Next.js 16 needs it).
- **Git.**
- **Supabase credentials.** The easiest route is the team's existing project: ask a team member for its URL, anon key and service_role key. Setting up a new project is covered under [Using your own Supabase project](#using-your-own-supabase-project).
- **An LLM API key.** The backend won't start without one. A free key from [Google AI Studio](https://aistudio.google.com/apikey) works with the default settings.

## Setup

### 1. Clone

```bash
git clone https://github.com/shamilaw-sci/CSC3213_20_Group_C
cd CSC3213_20_Group_C
```

### 2. Backend

Create the virtual environment in `backend/venv`, not at the repository root, so everyone uses the same layout.

**Windows (PowerShell)**
```powershell
cd backend
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

**macOS / Linux**
```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `backend/.env` and fill in the required values: `SUPABASE_URL`, `SUPABASE_KEY` (the service_role key), `SUPABASE_ANON_KEY` and `LLM_API_KEY`. Everything marked optional can stay commented out (see [Optional services](#optional-services)).

Start the API from the `backend/` folder, with the venv active:

```bash
uvicorn app.main:app --port 8000
```

Check it at http://localhost:8000. It should answer `"VFF Integrated Management System API is online"`. Interactive API docs are at http://localhost:8000/docs.

### 3. Frontend

In a second terminal:

```bash
cd frontend
npm install
```

Copy `frontend/.env.example` to `frontend/.env.local` and fill in `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Use the same Supabase project as the backend, with the **anon** key, never the service_role key.

```bash
npm run dev
```

Open http://localhost:3000. The frontend forwards `/api` calls to the backend on port 8000, so both need to be running.

### 4. Sign in

On the team's Supabase project, these demo logins exist, one per role. They all use the password `Password123!`.

| Login | Role |
|---|---|
| `admin@vff.org` | Admin |
| `director@vff.org` | Director |
| `finance@vff.org` | Finance Officer |
| `hr@vff.org` | HR Officer |
| `staff@vff.org` | Operations Lead |
| `fieldofficer@vff.org` | General Staff |
| `sysadmin@vff.org` | System Administrator |

## Roles

| Role | Main access |
|---|---|
| Admin | Everything, including user and role management |
| Director | Dashboards, finance (read), payroll approval, inventory, audit log, case assignment, volunteer approval, monthly reports |
| Finance Officer | Finance ledger, payables and receivables, inventory, programs (read) |
| HR Officer | Employees, attendance, schedules and holidays, leave, payroll generation, volunteer approval |
| Operations Lead | Programs and clinics, inventory stock, rescue cases, volunteer shift rota |
| General Staff | Rescue cases, issuing stock to cases, programs (read). New sign-ups get this role. |
| System Administrator | User accounts and the audit log only, with no business data |

Every role except System Administrator can also clock in, see their own attendance and request leave. Permissions are defined in `backend/app/core/permissions.py` and mirrored in `frontend/src/lib/permissions.ts`, so change both together.

## Optional services

The app runs without any of these. Each one adds a feature, and leaving it out falls back gracefully.

| Service | Env vars (`backend/.env`) | Without it |
|---|---|---|
| [OpenRouteService](https://openrouteservice.org/dev/#/signup) (free) | `ORS_API_KEY` | Dispatch orders visits by straight-line distance instead of road distance |
| [Brevo](https://www.brevo.com) email (free tier) | `BREVO_API_KEY`, `BREVO_SENDER_EMAIL` | No volunteer or donation emails; staff copy links and send them by hand |
| [PayHere sandbox](https://sandbox.payhere.lk) (test cards only) | `PAYHERE_*`, `PUBLIC_API_URL` | The donate page says online donations aren't set up. Full steps are in [backend/DONATION_SETUP.md](backend/DONATION_SETUP.md). |

Restart the backend after any change to `.env`.

## Using your own Supabase project

Skip this if you're using the team's project.

1. Create a project at [supabase.com](https://supabase.com) and copy its URL, anon key and service_role key from **Project Settings > API**.
2. In the **SQL Editor**, run `backend/db/init.sql`, then every file in `backend/db/migrations/` **in number order** (`001_…` through the highest number).
3. Create the demo logins with `python scripts/seed_demo_users.py`, run from `backend/` with the venv active.
4. For six months of sample data on every page, also run `python scripts/seed_presentation.py`. It's safe to run again: it tops up anything missing and never duplicates.
5. Load public holidays from **HR > Schedules & Holidays > Import** (the CSVs are in `backend/db/holidays/`).

> **Known gap:** three tables the app uses (`rescue_cases`, `program_assignments` and `outbreak_zones`) were created directly in the team's Supabase project and have no SQL file in the repo yet. A brand-new project will be missing them, so rescue cases, program staffing and the outbreak map won't work there until their SQL is added. Use the team's project if you need those features.

## Running the tests

Backend, from `backend/` with the venv active:

```bash
pip install -r requirements-dev.txt
python -m pytest tests --ignore=tests/e2e
```

Do this after step 2: the tests need a filled-in `backend/.env`, because the Supabase client is created when the app loads. They run against an in-memory fake database, though, so they never read or change real data. The `tests/e2e` folder currently doesn't load, so it's skipped above.

Frontend, from `frontend/`:

```bash
npm run lint
npx tsc --noEmit
```

## Troubleshooting

- **`ValueError: LLM_API_KEY not found`** when starting the backend: add `LLM_API_KEY` to `backend/.env`.
- **`ModuleNotFoundError: No module named 'app'`**: run uvicorn from inside `backend/`.
- **A package is missing even though you installed it**: you're using a different Python. `python -c "import sys; print(sys.executable)"` should point inside `backend/venv`.
- **Every page shows "Network Error" or fails to load data**: the backend isn't running on port 8000, or `NEXT_PUBLIC_API_URL` points somewhere else.
- **CORS errors in the browser console**: the frontend isn't on `PUBLIC_APP_URL`. If you open it as `http://127.0.0.1:3000`, add that to `CORS_ORIGINS`.
- **The backend still runs old code after an edit (Windows)**: `uvicorn --reload` can hang or keep serving the old version on Windows. Stop it and start it again.
- **Sign-in works but pages say you don't have access**: that login's role doesn't include the module. See [Roles](#roles).

## License

Internal use by VFF. CSC3213 Group C coursework.
