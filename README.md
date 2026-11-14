# premedia-api

Backend API for **Premedia Hub**, a premedia / digital asset management (DAM) tool for artwork upload, approval workflow, and role-based access.

## System Overview (3-Tier Architecture)

- **Tier 1 (Presentation):** React frontend ([saishatech18/premedia-frontend](https://github.com/saishatech18/premedia-frontend)), served under `/premedia/`. It calls this API under `/api`.
- **Tier 2 (Logic):** this repo, a FastAPI Python backend. It is the **only** gateway to the database (the frontend does not use `supabase-js`).
- **Tier 3 (Data):** PostgreSQL hosted on Supabase, holding RBAC and DAM metadata.
- **Storage Layer (DAM assets, planned):** external object storage (S3 / GCS / R2) for large artwork files via pre-signed upload URLs. The database stores metadata and file URLs only.

---

## Getting Started

### Prerequisites

- Python 3.12+
- A PostgreSQL database: either a Supabase project or a local Docker container

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure the environment

```bash
cp .env.example .env
```

Then set `DATABASE_URL` and `JWT_SECRET_KEY` in `.env`.

#### `DATABASE_URL`

Use **one** of the options below.

**Option A: Supabase**

1. In the Supabase dashboard, click **Connect** and copy the **Session pooler** connection string.
2. Replace the password placeholder with your **database password** (Project Settings → Database), not your Supabase account login. Don't keep the `[ ]` brackets.
3. URL-encode any special characters in the password (`@` → `%40`, `!` → `%21`, `#` → `%23`).

```
DATABASE_URL=postgresql://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

> Use the **Session pooler** (port 5432). The *Direct connection* host is IPv6-only and fails on most networks. The *Transaction pooler* (port 6543) doesn't support the prepared statements psycopg 3 uses.

**Option B: local Postgres in Docker**

```bash
docker run -d --name premedia-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=premedia -p 5432:5432 postgres:16
```

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/premedia
```

#### `JWT_SECRET_KEY`

The key that signs login tokens. Set it to a random string of at least 32 characters, and use a different one in each environment:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Changing it signs everyone out, because all existing tokens become invalid.

### 3. Run the API

```bash
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Interactive docs (Swagger UI): http://localhost:8000/docs

On startup the app creates any missing tables and seeds the default roles. `.env` is read once at startup, so **restart** the server after editing it; `--reload` only watches code changes.

### 4. Try it

On an empty database, create the first user, which must be the admin. No token is needed for this one request. The API doesn't check the role on this request, so make sure you send `"role":"admin"`; otherwise nobody can create users afterwards (see Troubleshooting).

```bash
curl -X POST http://localhost:8000/api/users \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"changeme","role":"admin","full_name":"Admin"}'
```

After that, every user must be created by an admin. Log in to get a token, then pass it as a Bearer token:

```bash
# Log in (returns {token, user})
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"changeme"}' | python -c "import sys, json; print(json.load(sys.stdin)['token'])")

# Create another user (role is a slug, case-insensitive)
curl -X POST http://localhost:8000/api/users \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"email":"operator@example.com","password":"changeme","role":"operator_retouching","full_name":"Op Erator"}'
```

In Swagger UI (`/docs`), click **Authorize** and paste the token.

### Troubleshooting

| Error | Cause |
|---|---|
| `failed to resolve host '...@aws-0-...'` | Unencoded `@` (or other special character) in the password. URL-encode it. |
| `password authentication failed for user "postgres"` | Wrong password. Use the database password; reset it in Project Settings → Database if unsure. |
| `Can't load plugin: sqlalchemy.dialects:postgres` | The URL starts with `postgres://`. Change it to `postgresql://`. |
| `Tenant or user not found` | Wrong project ref, region, or username in the URL. Copy it again from **Connect**. |
| `No module named 'psycopg'` (or `jwt`, `pwdlib`) | Dependencies are out of date. Run `pip install -r requirements.txt`. |
| `ValidationError` for `database_url` or `jwt_secret_key` on startup | The variable is missing from `.env`, or `JWT_SECRET_KEY` is shorter than 32 characters. |
| `401 Not authenticated` when creating the first user | The users table isn't empty, so an admin token is required. |
| `403 Only an admin can create users` | The token belongs to a non-admin. If the first user was created with a non-admin role, fix it in SQL: set that user's `role_id` to the `admin` role's id. |

---

## API Endpoints

API endpoints live under `/api`, with no trailing slashes, to match the [premedia-frontend](https://github.com/saishatech18/premedia-frontend) API client.

| Method | Path | Access | Description |
|---|---|---|---|
| `GET` | `/` | Public | Health check (outside `/api`) |
| `POST` | `/api/auth/login` | Public | Log in: `{email, password}`. Returns `{token, user}`. |
| `GET` | `/api/users` | Any logged-in user | List all users with their role |
| `POST` | `/api/users` | Admin (no token needed for the first user) | Create a user: `{email, password, role, full_name?}`. `role` is a role slug; the password must be 8–128 characters. |

Authenticated requests send `Authorization: Bearer <token>`. Tokens are JWTs that expire after 8 hours (`ACCESS_TOKEN_EXPIRE_MINUTES`). A missing, invalid or expired token returns 401; a logged-in user without the required role gets 403.

Emails are case-insensitive: they are stored lowercased, and login matches any casing. Users are returned as `{id, email, full_name, role_id, role: {id, name, description}}`, where `role.name` is the slug and `role.description` is the display label.

### Planned endpoints (called by the frontend, not built yet)

The frontend's workflow modules (Intake, Allocation, Timeline, DAM, Operator Studio, QC, Client Proofing, Analytics) all run on **jobs**. Until these exist, the frontend gets a 404 from `GET /api/jobs` and shows the modules as "not available yet".

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/auth/me` | Current user, so the frontend can refresh its stored session |
| `GET` | `/api/jobs` | List jobs |
| `POST` | `/api/jobs` | Create a job (Intake) |
| `POST` | `/api/jobs/{id}/<action>` | One endpoint per workflow action: assign, checkout/checkin, submit to QC, QC pin/approve/reject, client pin/sign-off/request changes |

The frontend currently calls `PATCH /api/jobs/{id}/allocate` and a generic `PATCH /api/jobs/{id}/command`; both repos have agreed to move to one `POST` per action, with the server enforcing status transitions and roles and writing the audit trail.

Job status pipeline expected by the frontend:

```
new ──assign──▶ active ──submit──▶ qc ──approve──▶ review ──sign-off──▶ approved
                                   │ ▲               │
                            reject │ │ resubmit      │ request changes
                                   ▼ │               │
                                  rework ◀───────────┘
```

> ⚠️ **Not production-ready yet:** CORS allows all origins, there is no login rate limiting, and any logged-in user (including `client`) can list every user. See the milestones below.

---

## Project Structure

```
premedia-api/
├── app/
│   ├── __init__.py
│   ├── auth.py         # Password hashing (Argon2), JWT tokens, auth dependencies
│   ├── config.py       # pydantic-settings Settings: DATABASE_URL, JWT settings (from env / .env)
│   ├── db.py           # SQLAlchemy engine (from settings), session maker, get_db dependency
│   ├── models.py       # DB schema: Role, User, Artwork, ArtworkStatus
│   ├── schemas.py      # Pydantic request/response schemas
│   └── main.py         # App, CORS, table creation, role seeding, API endpoints
├── .env.example        # Template for .env
├── .env                # Local secrets (gitignored)
└── requirements.txt    # fastapi, uvicorn, sqlalchemy, psycopg[binary], pydantic-settings, pwdlib[argon2], PyJWT
```

---

## Database Schema (`models.py`)

1. **`roles`** (RBAC)
   - `id` (PK, Integer)
   - `name` (String, unique, lowercase slug): `admin`, `project_manager`, `operator_retouching`, `operator_cgi`, `qc`, `client`
   - `description` (String): display label, e.g. `Operator (Retouching)`

2. **`users`**
   - `id` (PK, Integer)
   - `email` (String, unique)
   - `hashed_password` (String; Argon2 hash)
   - `full_name` (String)
   - `role_id` (FK → `roles.id`)

3. **`artworks`** (DAM metadata)
   - `id` (PK, Integer)
   - `title` (String)
   - `file_url` (String: path in object storage; files are never stored in the DB)
   - `file_size_mb` (Integer)
   - `status` (Enum, stored as `PENDING` / `APPROVED` / `REJECTED`)
   - `created_at` (DateTime)
   - `owner_id` (FK → `users.id`)

Tables are created automatically on startup (`create_all`). It only creates **missing** tables and never alters existing ones. There are no migrations yet.

`artworks` has no endpoints yet. Its three-state status predates the frontend's job pipeline (`new → active → qc → review → approved`, plus `rework`), so the Jobs work will likely reuse it for job files and versions rather than as the workflow entity.

**Supabase security:** Row Level Security (RLS) is enabled, with no policies, on all tables. This blocks Supabase's public REST API. The backend connects as `postgres`, which bypasses RLS. **Enable RLS on any new table you add.**

---

## Current Status & Next Milestones

**Where things stand:** the foundation and authentication are done. With [premedia-frontend](https://github.com/saishatech18/premedia-frontend), login, the user list and Admin Console → Provision New User work end to end. Every workflow module is blocked on the Jobs API.

### Done

- [x] FastAPI app with all routes under `/api`, no trailing slashes, matching the frontend API client
- [x] PostgreSQL on Supabase via the Session pooler, psycopg 3 driver, `pool_pre_ping`
- [x] Configuration through `pydantic-settings` (`.env` / env vars), validated at startup
- [x] Firestore code removed; PostgreSQL is the only datastore
- [x] SQLAlchemy models for roles, users and artwork metadata; tables auto-created on startup
- [x] RLS enabled (no policies) on all Supabase tables, blocking Supabase's public REST API
- [x] Six roles seeded to match the frontend (`admin`, `project_manager`, `operator_retouching`, `operator_cgi`, `qc`, `client`)
- [x] Argon2 password hashing; JWT (HS256, 8-hour) Bearer auth; 401/403 handling the frontend relies on
- [x] `POST /api/auth/login`, `GET /api/users`, `POST /api/users` (admin-only, first-user bootstrap)
- [x] Input hardening: normalised emails, password length limits, duplicate-email race handled

### Milestone 1: Hardening (before adding tables)

- [ ] Database migrations with Alembic, baselined on the current Supabase schema
- [ ] Test suite (pytest + `TestClient` against a throwaway Postgres); stop running `create_all` at import time so tests can import the app
- [ ] Reusable `require_roles(...)` dependency for role-gated routes
- [ ] Force the bootstrap (first) user's role to `admin`
- [ ] `GET /api/auth/me` so the frontend can refresh the stored session user
- [ ] Decide whether `client` users may list all users (`GET /api/users`)

### Milestone 2: Jobs API and approval workflow (unblocks the frontend)

- [ ] Models for jobs, versions, QC/client pins and an audit trail, with user-id foreign keys for operator and project manager (the frontend matches by display name today)
- [ ] `GET /api/jobs`, `POST /api/jobs`, `GET /api/jobs/{id}`, with server-assigned ids
- [ ] One `POST /api/jobs/{id}/<action>` per workflow action, enforcing status transitions (409) and roles (403) server-side
- [ ] Update the frontend API client from `PATCH .../allocate` and `PATCH .../command` to the new endpoints

### Milestone 3: Object storage

- [ ] Pre-signed upload/download URLs (S3/R2/GCS) for job files and versions; the database keeps only metadata and `file_url`
- [ ] Back the DAM module with real file metadata (format, size, versions)

### Milestone 4: User management

- [ ] Update and deactivate users; change and reset passwords
- [ ] Decide on `/api/auth/register` (hidden in the frontend): admin-only, or self-registration with a low-privilege default role

### Milestone 5: Production deployment

- [ ] Host the API and route `/api/*` from the frontend's domain (or set `VITE_API_BASE`)
- [ ] Restrict CORS to the frontend origins (configured in `Settings`)
- [ ] Login rate limiting
- [ ] CI: lint and tests on pull requests
