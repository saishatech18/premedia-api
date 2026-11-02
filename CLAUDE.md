# CLAUDE.md

Backend API for **Premedia Hub**, a premedia / digital-asset-management (DAM) tool: artwork upload, approval workflow, and role-based access.

## Architecture

- **Frontend:** React app in a separate repo (`saishatech18/premedia`), on GitHub Pages, served at `saishatech.in/premedia` (via a Vercel rewrite) and `premedia.saishatech.in`.
- **This repo:** FastAPI + SQLAlchemy (sync) + PostgreSQL (hosted on Supabase; `DATABASE_URL` points there).
- **Planned:** artwork binaries go in object storage (S3/GCS/R2) through pre-signed URLs. The DB stores only metadata and `file_url`, never file bytes.

## Branch state

- `main` has only the initial commit: an old **Firestore** version. Don't use it as a reference.
- `Postgresql` (the active branch) is SQLAlchemy/Postgres only. All Firestore code and dependencies have been removed.
- All configuration comes from `Settings` in `config.py` (`pydantic-settings`), which reads env vars and `.env`. `db.py` uses `settings.database_url`; add new settings there rather than calling `os.getenv`.
- All live endpoints are defined directly in `app/main.py`.

## Supabase

- Row Level Security (RLS) is **enabled with no policies** on `roles`, `users` and `artworks`. This blocks Supabase's auto-generated REST API, and the app is unaffected because it connects as `postgres`, which bypasses RLS. Enable RLS on every new table too.
- No `supabase-js` is used. This API is the only path to the database.
- Connect through the **Session pooler** (port 5432), not Direct (IPv6 only) or the Transaction pooler (6543, which breaks psycopg 3 prepared statements). Special characters in the password must be URL-encoded in `DATABASE_URL`.

## Code layout

| File | Purpose |
|---|---|
| `app/main.py` | App, CORS, startup role seeding, and all live routes |
| `app/db.py` | `engine`, `SessionLocal`, `Base`, `get_db` dependency |
| `app/models.py` | `Role`, `User`, `Artwork`, `ArtworkStatus` enum (pending/approved/rejected) |
| `app/schemas.py` | Pydantic: `RoleResponse`, `UserCreate`, `UserResponse`, `LoginRequest`, `LoginResponse` |
| `app/config.py` | `pydantic-settings` `Settings` (`app_name`, required `database_url`) |

## Live endpoints (`app/main.py`)

Routes are defined on an `APIRouter(prefix="/api")` with **no trailing slashes**. The paths follow the frontend contract ([saishatech18/premedia-frontend](https://github.com/saishatech18/premedia-frontend), checked out at `../premedia-frontend`). Its README lists the endpoints it calls and its `CLAUDE.md` sets the API conventions: auth under `/api/auth`, users under `/api/users`.

- `GET /`: health message (on `app`, outside `/api`)
- `GET /api/users`: lists users as `UserResponse` (`id, email, full_name, role_id, role {id, name, description}`)
- `POST /api/users`: body `{email, password, role, full_name?}`, where `role` is a role **slug**. Returns 201, or 400 for a duplicate email or an unknown role.
- `POST /api/auth/login`: body `{email, password}`. Returns `{user: UserResponse}` and **no token**, so the frontend (which requires `{token, user}`) can't log in until JWT is added.

## Behaviors and gotchas

- **Tables are created at import time** by `models.Base.metadata.create_all(bind=engine)` in `main.py`. There are no migrations (no Alembic), so schema changes to existing tables are **not** applied automatically.
- **Roles are seeded on startup** (deprecated `@app.on_event("startup")`) from `DEFAULT_ROLES` in `main.py`: `admin`, `project_manager`, `operator_retouching`, `operator_cgi`, `qc`, `client`. `Role.name` is the lowercase slug (the API identifier) and `Role.description` is the display label, which seeding keeps in sync. Role lookups are case-insensitive. Seeding never deletes roles; the old `designer`, `production` and `quality` roles were removed from Supabase by hand.
- **Passwords are stored and compared in plaintext**, even though the column is `hashed_password`. Hashing (e.g. passlib/bcrypt) and JWT auth are planned but not done. There is no auth or role enforcement on any endpoint yet.
- CORS on this branch is `allow_origins=["*"]` with `allow_credentials=True`. On `main` it was an explicit list (`http://localhost:3001`, `https://premedia.saishatech.in`).
- `UserCreate.email` is a plain `str`, even though `email-validator` is installed (it could be `EmailStr`).
- `Artwork` has a model but no endpoints yet.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# .env (gitignored) must contain:
#   DATABASE_URL=postgresql://user:pass@host:5432/dbname
uvicorn app.main:app --reload
```

Startup fails if `DATABASE_URL` is unset/empty (pydantic `ValidationError`) or the DB is unreachable, because `create_engine` and `create_all` run at import time. There are no tests, linter config, or CI in the repo.

## Roadmap (from README)

1. Hash passwords and add JWT auth with role-checking dependencies.
2. Add Artwork CRUD and the approval workflow (pending, then approved or rejected).
3. Add pre-signed uploads to object storage.

## Conventions

- SQLAlchemy 2.1 makes `postgresql://` URLs use psycopg 3, so the driver is `psycopg[binary]`, not `psycopg2`.
- Sync SQLAlchemy sessions through `Depends(get_db)`. Use `db.query(...)` (1.x-style), which matches the existing code.
- Pydantic v2 is installed, but the schemas use the v1-style `class Config: from_attributes = True`. Match the style of the file you're editing.
- Don't commit `.env` or `.DS_Store` (`.DS_Store` is currently tracked by mistake and isn't in `.gitignore`).
