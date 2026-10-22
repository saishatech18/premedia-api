# Premedia Architecture & Progress Notes

## System Overview (3-Tier Architecture)
- **Tier 1 (Presentation):** React frontend hosted via GitHub Pages (`saishatech18/premedia`), served at `saishatech.in/premedia` via Vercel rewrite.
- **Tier 2 (Logic / Middle Tier):** FastAPI Python backend (`saishatech18/premedia-api`). Sole gateway to the data layer.
- **Tier 3 (Data):** PostgreSQL relational database handling RBAC and DAM metadata.
- **Storage Layer (DAM Assets):** External Object Storage (S3 / GCS / R2) for large artwork and design files using pre-signed upload URLs. The database stores metadata and file URLs only.

---

## Backend (`premedia-api`) Structure

premedia-api/
├── app/
│   ├── init.py
│   ├── config.py       # pydantic-settings Settings (app_name)
│   ├── db.py           # Reads DATABASE_URL; SQLAlchemy engine, session maker, get_db dependency
│   ├── models.py       # DB schema: Role, User, Artwork, ArtworkStatus
│   ├── schemas.py      # Pydantic request/response schemas
│   └── main.py         # App, CORS, table creation, role seeding, API endpoints
├── .env                # Local secrets (ignored by git)
├── .gitignore
└── requirements.txt    # fastapi, uvicorn, sqlalchemy, psycopg[binary], pydantic-settings


---

## Database Schema (`models.py`)

1. **`roles` Table (RBAC)**
   - `id` (PK, Integer)
   - `name` (String, unique: e.g., admin, designer, client)
   - `description` (String)

2. **`users` Table**
   - `id` (PK, Integer)
   - `email` (String, unique)
   - `hashed_password` (String)
   - `full_name` (String)
   - `role_id` (FK -> `roles.id`)

3. **`artworks` Table (DAM Metadata)**
   - `id` (PK, Integer)
   - `title` (String)
   - `file_url` (String: target path in Object Storage, never stored as raw binary)
   - `file_size_mb` (Integer)
   - `status` (Enum: `pending`, `approved`, `rejected`)
   - `created_at` (DateTime)
   - `owner_id` (FK -> `users.id`)

---

## Current Status & Next Milestones
- [x] Frontend deployed & live on GitHub Pages
- [x] Backend folder structure & PostgreSQL driver configured
- [x] SQLAlchemy models defined for RBAC and Artwork metadata
- [x] Database auto-creation hook added to `main.py`
- [x] Seed default roles (`admin`, `designer`, `client`, `production`, `quality`)
- [x] Firestore code removed; PostgreSQL is the only datastore
- [x] User registration & login endpoints (`main.py`)
- [ ] Password hashing (passwords are currently stored in plain text)
- [ ] Add JWT authentication & role-verification middleware
- [ ] Connect object storage (S3/R2) for DAM pre-signed uploads