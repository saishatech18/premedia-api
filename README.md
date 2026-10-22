# premedia-api

Backend API for **Premedia Hub**, a premedia / digital asset management (DAM) tool for artwork upload, approval workflow, and role-based access.

## System Overview (3-Tier Architecture)

- **Tier 1 (Presentation):** React frontend hosted on GitHub Pages (`saishatech18/premedia`), served at `saishatech.in/premedia` via a Vercel rewrite.
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

### 2. Configure the database

```bash
cp .env.example .env
```

Then set `DATABASE_URL` in `.env` using **one** of the options below.

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

### 3. Run the API

```bash
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Interactive docs (Swagger UI): http://localhost:8000/docs

On startup the app creates any missing tables and seeds the default roles. `DATABASE_URL` is read once at startup, so **restart** the server after editing `.env`; `--reload` only watches code changes.

### 4. Try it

```bash
# Create a user (role names are case-insensitive)
curl -X POST http://localhost:8000/users/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"designer@example.com","password":"changeme","role":"designer"}'

# Log in
curl -X POST http://localhost:8000/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"designer@example.com","password":"changeme"}'
```

### Troubleshooting

| Error | Cause |
|---|---|
| `failed to resolve host '...@aws-0-...'` | Unencoded `@` (or other special character) in the password. URL-encode it. |
| `password authentication failed for user "postgres"` | Wrong password. Use the database password; reset it in Project Settings → Database if unsure. |
| `Tenant or user not found` | Wrong project ref, region, or username in the URL. Copy it again from **Connect**. |
| `No module named 'psycopg'` | Dependencies are out of date. Run `pip install -r requirements.txt`. |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/users/` | List all users with their role |
| `POST` | `/users/` | Create a user: `{email, password, role}`. `role` is a role name. |
| `POST` | `/login/` | Check credentials: `{email, password}`. Returns user info (no token yet). |

> ⚠️ **Not production-ready yet:** passwords are stored in plain text, there is no authentication or role enforcement on any endpoint, and CORS allows all origins. See the milestones below.

---

## Project Structure

```
premedia-api/
├── app/
│   ├── __init__.py
│   ├── config.py       # pydantic-settings Settings (app_name)
│   ├── db.py           # Reads DATABASE_URL; SQLAlchemy engine, session maker, get_db dependency
│   ├── models.py       # DB schema: Role, User, Artwork, ArtworkStatus
│   ├── schemas.py      # Pydantic request/response schemas
│   └── main.py         # App, CORS, table creation, role seeding, API endpoints
├── .env.example        # Template for .env
├── .env                # Local secrets (gitignored)
└── requirements.txt    # fastapi, uvicorn, sqlalchemy, psycopg[binary], pydantic-settings
```

---

## Database Schema (`models.py`)

1. **`roles`** (RBAC)
   - `id` (PK, Integer)
   - `name` (String, unique, lowercase): `admin`, `designer`, `client`, `production`, `quality`
   - `description` (String)

2. **`users`**
   - `id` (PK, Integer)
   - `email` (String, unique)
   - `hashed_password` (String; currently plain text, hashing pending)
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

**Supabase security:** Row Level Security (RLS) is enabled, with no policies, on all tables. This blocks Supabase's public REST API. The backend connects as `postgres`, which bypasses RLS. **Enable RLS on any new table you add.**

---

## Current Status & Next Milestones

- [x] Frontend deployed & live on GitHub Pages
- [x] Backend structure & PostgreSQL (psycopg 3) driver configured
- [x] SQLAlchemy models for RBAC and artwork metadata
- [x] Tables auto-created on startup
- [x] Default roles seeded (`admin`, `designer`, `client`, `production`, `quality`)
- [x] Firestore code removed; PostgreSQL is the only datastore
- [x] User registration & login endpoints
- [x] RLS enabled on all Supabase tables
- [ ] Password hashing
- [ ] JWT authentication & role-based access checks
- [ ] Restrict CORS to the frontend origins
- [ ] Database migrations (Alembic)
- [ ] Artwork endpoints & approval workflow
- [ ] Object storage (S3/R2) pre-signed uploads
