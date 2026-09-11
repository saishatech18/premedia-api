# PreMedia API

A minimal REST API backend for Saisha Technologies' PreMedia portal. It uses Python 3.13+, FastAPI, and the Google Cloud Firestore server SDK.

## Project structure

```text
premedia-api/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   └── routes.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Prerequisites

- Python 3.13 or newer
- An existing Google Cloud project with Firestore enabled in Native mode
- A downloaded service-account JSON key with Firestore access

## Google Cloud configuration

Place the service-account JSON file in the project root, or use an absolute path. Keep it private; `.gitignore` excludes service-account filenames.

Create `.env` from `.env.example` and set:

```dotenv
GOOGLE_APPLICATION_CREDENTIALS=./premedia-service-account.json
GOOGLE_CLOUD_PROJECT=premedia-ap
FIRESTORE_COLLECTION=artwork_tasks
```

`GOOGLE_APPLICATION_CREDENTIALS` points to the JSON key, `GOOGLE_CLOUD_PROJECT` is the Google Cloud project ID, and `FIRESTORE_COLLECTION` defaults to `artwork_tasks`. For Google Cloud deployment, omit the key path and use the runtime's Application Default Credentials instead.

## Set up the local project

From the project root:

### Windows PowerShell

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

### macOS / Linux

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

## Run the API

With the virtual environment activated:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open the interactive API documentation at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

The configured browser origins are `http://localhost:3001` and `https://premedia.saishatech.in`. CORS does not affect direct curl requests.

## Test the endpoints

### Health check

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","service":"premedia-api"}
```

### Create an artwork task

```bash
curl.exe -X POST http://127.0.0.1:8000/api/v1/tasks -H "Content-Type: application/json" -d '{"title":"Summer catalogue artwork","client_name":"Example Client","task_type":"Master AW"}'
```

`status` is optional and defaults to `draft`. Other example task types include `Reprographics` and `KLD Amendment`.

A successful response has HTTP `201` and includes the generated Firestore document ID:

```json
{
  "title": "Summer catalogue artwork",
  "client_name": "Example Client",
  "task_type": "Master AW",
  "status": "draft",
  "id": "generated-firestore-document-id",
  "created_at": "2026-09-11T12:00:00Z"
}
```

### List tasks

```bash
curl http://127.0.0.1:8000/api/v1/tasks
```

The API iterates over the Firestore collection stream and returns all task documents as a JSON array.

## Deployment note

For Google Cloud deployment, prefer Application Default Credentials from the attached runtime service account or another managed identity. Do not upload `service-account.json` to the server. Set `GOOGLE_CLOUD_PROJECT` or configure the platform's project context as appropriate for the selected Google Cloud service.
