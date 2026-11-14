# CLAUDE.md

Backend API for **Premedia Hub** (branded "PremediaOS" in the UI), a premedia / digital-asset-management (DAM) tool: job intake, operator allocation, retouching, QC, client proofing, and role-based access.

## Architecture

- **Frontend:** React 19 + Vite app in a separate private repo (`saishatech18/premedia-frontend`, checked out at `../premedia-frontend`), served under `/premedia/`. It calls this API under `/api` on the same domain. Locally, Vite proxies `/api` to `http://localhost:8000`, so dev needs no CORS. The older public `saishatech18/premedia` repo is the previous frontend and isn't used.
- **This repo:** FastAPI + SQLAlchemy 2.1 (sync) + PostgreSQL (hosted on Supabase; `DATABASE_URL` points there).
- **Planned:** artwork binaries go in object storage (S3/GCS/R2) through pre-signed URLs. The DB stores only metadata and `file_url`, never file bytes.

## Branch state

- `main` is the active branch. It is SQLAlchemy/Postgres only; all Firestore code and dependencies have been removed.
- `Postgresql` is stale: it has no commits that aren't on `main`, and its README still documents the old `/users/` and `/login/` paths. Don't use it as a reference.

## Code layout

| File | Purpose |
|---|---|
| `app/main.py` | App, CORS, `create_all`, startup role seeding (`DEFAULT_ROLES`, `seed_roles`), and **all live routes** |
| `app/auth.py` | Argon2 hashing (`pwdlib`), JWT creation (`PyJWT`), and the auth dependencies `get_optional_user`, `get_current_user`, `require_admin_or_first_user` |
| `app/db.py` | `engine` (`pool_pre_ping=True`), `SessionLocal`, `Base`, `get_db` dependency |
| `app/models.py` | `Role`, `User`, `Artwork`, `ArtworkStatus` enum (pending/approved/rejected) |
| `app/schemas.py` | Pydantic: `RoleResponse`, `UserCreate`, `UserResponse`, `LoginRequest`, `LoginResponse`; email normalisation types |
| `app/config.py` | `pydantic-settings` `Settings` (`app_name`, required `database_url` and `jwt_secret_key` (min 32 chars), `jwt_algorithm` (HS256/384/512), `access_token_expire_minutes` = 480) |

All configuration comes from `Settings` in `config.py`, which reads env vars and `.env`. Add new settings there rather than calling `os.getenv`.

## Live endpoints (`app/main.py`)

Routes are defined on an `APIRouter(prefix="/api")` with **no trailing slashes**. The frontend's `README.md` lists the endpoints it calls and its `CLAUDE.md` sets the API conventions (auth under `/api/auth`, users under `/api/users`, errors as `{detail}`, one `POST` per workflow action).

- `GET /`: health message (on `app`, outside `/api`).
- `POST /api/auth/login` (public): body `{email, password}`. Returns `{token, user: UserResponse}`, or 401 `Invalid email or password`. Unknown emails are verified against a dummy hash so timing doesn't reveal which emails exist.
- `GET /api/users` (any logged-in user, **including `client`**): lists all users as `UserResponse` (`id, email, full_name, role_id, role {id, name, description}`). No pagination.
- `POST /api/users` (admin): body `{email, password, role, full_name?}`, where `role` is a role **slug** (case-insensitive). Returns 201, or 400 for a duplicate email or an unknown role. **Bootstrap:** while the users table is empty, no token is needed. The first user is assumed to be the admin, but the role sent is **not checked or forced**.

## Frontend contract: what's built vs. what the UI calls

The frontend (`../premedia-frontend/src/api/client.js`) calls these paths. Only the first three exist here.

| Frontend call | Backend status |
|---|---|
| `POST /api/auth/login` | Built |
| `GET /api/users` | Built |
| `POST /api/users` | Built (Admin Console → Provision New User) |
| `GET /api/jobs` | **Missing.** The hub treats a 404 as "Jobs are not available on the server yet", so the eight job-based modules show no jobs and job actions fail. Only the Admin Console (user list and creation) is usable. |
| `POST /api/jobs` | **Missing** (Intake) |
| `PATCH /api/jobs/:id/allocate` | **Missing** (Allocation) |
| `PATCH /api/jobs/:id/command` with `{commandName, payload, auditDetails}` | **Missing.** Agreed target: one `POST /api/jobs/:id/<action>` per command instead, with the server appending to lists and writing the audit trail. |
| `POST /api/auth/register` | Missing; hidden in the UI (`SELF_REGISTRATION_ENABLED = false`). If built, it must assign a low-privilege role server-side. |
| `GET /api/auth/me` | Missing; the UI keeps the login-time user in localStorage and never refreshes it. |

### Job shape the frontend expects

The UI is built around **jobs**, not artworks. From `intake.jsx` and the other modules, a job has: `id`, `client`, `title`, `clientEmail`, `clientPoc`, `projectManager`, `category` (e.g. Digital/Print), `jobType`, `priority` (e.g. rush/high/normal), `dueDate`, `timeAllocated`/`timeSpent` (minutes), `status`, `assignedTo`, `checkedOut`, `attachments`, `fileNames`, `preflightStatus`, `specs {width, height, colorSpace, format}`, `versions [{v, operator, qcOperator, timestamp, comment}]`, `qcPins` and `pins` (`{id, x, y, v, author, comment, timestamp, resolved}`), `qcNotes`, `signedOffBy`, `signedOffAt`, and `auditTrail`. (Analytics derives SLA `margin` and `slaStatus` client-side from `timeAllocated` and `timeSpent`; they aren't API fields.)

Status pipeline: `new` → `active` (assigned) → `qc` → `review` (client proofing) → `approved`, with `rework` coming back from QC or the client and returning to `qc` on resubmission. Operator Studio also lists `new` (unassigned) jobs, so the UI lets an operator submit a job that was never assigned; the server should require assignment first.

Workflow commands the UI sends today: `CREATE_JOB`, `ASSIGN_OPERATOR`, `UPDATE_CHECKOUT_STATUS`, `SUBMIT_TO_QC`, `ADD_QC_PIN`, `APPROVE_QC`, `REJECT_TO_OPERATOR`, `ADD_CLIENT_PIN`, `CLIENT_SIGN_OFF`, `CLIENT_REQUEST_CHANGES`.

When designing the Jobs API, fix these frontend shortcuts server-side rather than copying them:
- The client generates the job id (`JOB-<random>`) and sends whole replacement arrays (`versions`, `pins`, `qcPins`). The server should assign ids and append.
- `assignedTo` and `projectManager` are display names (`'Unassigned'` when empty). Use user ids (FKs) and let the UI show names.
- `status` is sent by the client with each command. The server should derive it from the action and reject illegal transitions (409) and wrong roles (403).
- Timestamps are client-formatted strings. Use server `DateTime`s.

The existing `Artwork` model (3-state `pending/approved/rejected`, `file_size_mb` as Integer) predates this design and has no endpoints. Treat it as a candidate for job files/versions, not as the workflow entity. Its table already exists in Supabase.

## Supabase

- Row Level Security (RLS) is **enabled with no policies** on `roles`, `users` and `artworks`. This blocks Supabase's auto-generated REST API, and the app is unaffected because it connects as `postgres`, which bypasses RLS. **Enable RLS on every new table too.**
- No `supabase-js` is used. This API is the only path to the database.
- Connect through the **Session pooler** (port 5432), not Direct (IPv6 only) or the Transaction pooler (6543, which breaks psycopg 3 prepared statements). Special characters in the password must be URL-encoded in `DATABASE_URL`.

## Behaviors and gotchas

- **Tables are created at import time** by `models.Base.metadata.create_all(bind=engine)` in `main.py`, so importing `app.main` connects to the database. There are no migrations (no Alembic), so schema changes to existing tables are **not** applied automatically; they need manual SQL in Supabase.
- **Roles are seeded on startup** (`seed_roles()`, from the FastAPI `lifespan` handler) from `DEFAULT_ROLES`: `admin`, `project_manager`, `operator_retouching`, `operator_cgi`, `qc`, `client`. `Role.name` is the lowercase slug (the API identifier) and `Role.description` is the display label, which seeding keeps in sync. The frontend mirrors this list in `src/api/roles.js`; keep both in sync. Role lookups are case-insensitive. Seeding never deletes roles; the old `designer`, `production` and `quality` roles were removed from Supabase by hand.
- **Auth:** passwords are Argon2-hashed. Tokens are stateless JWTs carrying only `sub` (user id) and `exp` (default 8 hours); there is no refresh, logout or revocation. Each request reloads the user from the DB, so role changes and deleted users take effect immediately. Missing, invalid or expired tokens give 401 with `WWW-Authenticate: Bearer`; a wrong role gives 403. Inside the hub, the frontend signs the user out on any 401 (from loading data or from an action). Access checks that don't need the user object go in the route's `dependencies=[...]`.
- **Bootstrap risk:** `require_admin_or_first_user` lets anyone create a user, with any role, while the table is empty. If the first user isn't `admin`, no one can create users through the API and the fix is SQL. Two concurrent tokenless requests on an empty table can both succeed.
- **No admin-check helper exists yet.** `require_admin_or_first_user` hard-codes `role.name != "admin"` and the message "Only an admin can create users". Add a reusable `require_roles(*slugs)` dependency before adding more role-gated routes.
- CORS is `allow_origins=["*"]` with `allow_credentials=False`. Auth uses the `Authorization` header, not cookies, so credentials aren't needed.
- **Emails are trimmed and lowercased** before they're stored or looked up (`NormalizedEmail` and `LoginEmail` in `schemas.py`), so login and the duplicate check ignore case. `UserCreate.email` is validated as an `EmailStr`; login takes any string. Passwords must be 8–128 characters on create; login only enforces the 128 maximum, which bounds hashing work. A duplicate email that slips past the pre-check (concurrent requests) is caught as an `IntegrityError` and still returns 400.
- `ArtworkStatus` is a SQLAlchemy `Enum`, which stores the member **names** (`PENDING`), not the values.
- `Artwork.created_at` uses `datetime.utcnow`, which is deprecated since Python 3.12 and produces naive datetimes. Use `datetime.now(timezone.utc)` (or `server_default=func.now()`) in new models.
- `package-lock.json` in the repo root is a stray, empty npm lockfile (untracked). It isn't part of this project.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then set DATABASE_URL and JWT_SECRET_KEY (min 32 chars)
uvicorn app.main:app --reload
```

Startup fails at import time, because `Settings()`, `create_engine` and `create_all` all run then. The error depends on the cause:
- `DATABASE_URL` unset or empty, or `JWT_SECRET_KEY` unset or shorter than 32 characters: pydantic `ValidationError`. `database_url` only has `min_length=1`, so its format isn't validated here.
- A malformed URL: SQLAlchemy `ArgumentError`. A `postgres://` scheme gives `NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres`; it must be `postgresql://`.
- A database that can't be reached: psycopg `OperationalError` from `create_all`. `.env` is read once, so restart after editing it. There are no tests, linter config, CI, Dockerfile or deployment config in the repo.

## Current status & next milestones

Keep this in sync with the same section in `README.md`.

**Done:** Postgres/Supabase setup (Session pooler, psycopg 3, RLS on), models for roles/users/artworks, role seeding matching the frontend, Argon2 + JWT auth, login, admin-only user creation with first-user bootstrap, input normalisation, and `/api` paths matching the frontend. The frontend's login, user list and Admin Console user creation work end to end against this API.

**Next, in order:**

1. **Hardening before new tables.** Adopt Alembic (baseline the existing schema) so the Jobs tables don't need hand-written SQL; add a pytest + `TestClient` suite against a throwaway Postgres; move `create_all` out of import time; add `require_roles(...)`; force the bootstrap user's role to `admin`; add `GET /api/auth/me`; decide whether `client` users may list all users.
2. **Jobs API** (unblocks the eight job-based frontend modules). Models for jobs, versions, pins/annotations and audit events, using user-id FKs. Endpoints: `GET/POST /api/jobs`, `GET /api/jobs/{id}`, then one `POST /api/jobs/{id}/<action>` per workflow command (assign, checkout/checkin, submit, QC pin/approve/reject, client pin/sign-off/request-changes). Enforce the status machine and per-role permissions server-side and write the audit trail there. Update `../premedia-frontend/src/api/client.js` in step, since it still calls `PATCH .../allocate` and `PATCH .../command`.
3. **Object storage.** Pre-signed upload/download URLs (S3/R2/GCS) for job files and versions; the DAM module currently invents formats and sizes from `fileNames`.
4. **User management.** Update/deactivate users, change/reset password, optionally admin-created accounts via `/api/auth/register`; the Admin Console's demo "reset" button needs a backend endpoint or should be removed.
5. **Production deployment.** Host the API, route `/api/*` from the frontend's domain (or set `VITE_API_BASE`), restrict CORS origins via `Settings`, add login rate limiting, and CI (lint + tests).

## Conventions

- SQLAlchemy 2.1 makes `postgresql://` URLs use psycopg 3, so the driver is `psycopg[binary]`, not `psycopg2`.
- Sync SQLAlchemy sessions through `Depends(get_db)`. Use `db.query(...)` (1.x-style), which matches the existing code.
- Pydantic v2 is installed, but the schemas use the v1-style `class Config: from_attributes = True`. Match the style of the file you're editing.
- Error responses use FastAPI's `{detail}` (string for 400/401/403/404/409; list for 422). The frontend's `describeDetail` depends on this.
- Don't commit `.env` or `.DS_Store` (both are in `.gitignore`).
