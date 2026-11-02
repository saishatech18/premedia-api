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

On an empty database, create the first user, which must be the admin. No token is needed for this one request:

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
| `Tenant or user not found` | Wrong project ref, region, or username in the URL. Copy it again from **Connect**. |
| `No module named 'psycopg'` (or `jwt`, `pwdlib`) | Dependencies are out of date. Run `pip install -r requirements.txt`. |
| `ValidationError` for `database_url` or `jwt_secret_key` on startup | The variable is missing from `.env`, or `JWT_SECRET_KEY` is shorter than 32 characters. |
| `401 Not authenticated` when creating the first user | The users table isn't empty, so an admin token is required. |

---

## API Endpoints

API endpoints live under `/api`, with no trailing slashes, to match the [premedia-frontend](https://github.com/saishatech18/premedia-frontend) API client.

| Method | Path | Access | Description |
|---|---|---|---|
| `GET` | `/` | Public | Health check (outside `/api`) |
| `POST` | `/api/auth/login` | Public | Log in: `{email, password}`. Returns `{token, user}`. |
| `GET` | `/api/users` | Any logged-in user | List all users with their role |
| `POST` | `/api/users` | Admin (no token needed for the first user) | Create a user: `{email, password, role, full_name?}`. `role` is a role slug. |

Authenticated requests send `Authorization: Bearer <token>`. Tokens are JWTs that expire after 8 hours (`ACCESS_TOKEN_EXPIRE_MINUTES`). A missing, invalid or expired token returns 401; a logged-in user without the required role gets 403.

Users are returned as `{id, email, full_name, role_id, role: {id, name, description}}`, where `role.name` is the slug and `role.description` is the display label.

> ⚠️ **Not production-ready yet:** CORS allows all origins and there is no login rate limiting. See the milestones below.

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

**Supabase security:** Row Level Security (RLS) is enabled, with no policies, on all tables. This blocks Supabase's public REST API. The backend connects as `postgres`, which bypasses RLS. **Enable RLS on any new table you add.**

---

## Current Status & Next Milestones

- [x] Frontend deployed & live on GitHub Pages
- [x] Backend structure & PostgreSQL (psycopg 3) driver configured
- [x] SQLAlchemy models for RBAC and artwork metadata
- [x] Tables auto-created on startup
- [x] Default roles seeded (`admin`, `project_manager`, `operator_retouching`, `operator_cgi`, `qc`, `client`)
- [x] Firestore code removed; PostgreSQL is the only datastore
- [x] User creation (admin-only) & login endpoints
- [x] RLS enabled on all Supabase tables
- [x] Password hashing (Argon2)
- [x] JWT authentication & role-based access checks
- [ ] Restrict CORS to the frontend origins
- [ ] Database migrations (Alembic)
- [ ] Artwork endpoints & approval workflow
- [ ] Object storage (S3/R2) pre-signed uploads
