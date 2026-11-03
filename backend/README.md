# Rohingya Learning App — Mock Backend

A FastAPI server that returns **made-up sample data** for every endpoint in the API spec, plus a PostgreSQL database. It's for frontend development only: nothing is saved, and every Rohingya text field is `null` on purpose.

## Run it

You only need **Docker Desktop** (Windows/macOS) or **Docker Engine** (Linux). Run this from inside the `backend/` folder:

```bash
docker compose up
```

The first run takes a minute to build. After that:

- Interactive API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health (should say `"database": "up"`)

## Seed the vocabulary database

The optional seed command imports `rohingya_greetings_40.json` and `rohingya_phrases_18.json` from `ml/translation/data/` into PostgreSQL. Run it from `backend/` after the database is healthy:

```bash
docker compose run --rm api python -m app.seed
```

To import another JSON dataset, pass its path relative to the repository root as seen inside the API container (the `ml/` directory is included):

```bash
docker compose run --rm api python -m app.seed /app/ml/translation/data/rohingya_phrases_18.json
```

For host development, start PostgreSQL with `docker compose up db`, then from `backend/` run `python -m app.seed` with the backend dependencies installed. The command creates the vocabulary tables as needed and uses an upsert key, so rerunning it updates entries rather than duplicating them. It does not delete database entries omitted from later dataset revisions.

After seeding, the existing `/api/categories`, `/api/categories/{category_id}/words`, `/api/words`, and `/api/words/{word_id}` endpoints serve seeded entries when present; mock responses remain available before seeding. Dataset entries retain their original JSON metadata in the database. Content statuses remain unverified unless the source explicitly marks them verified; seeding does not constitute language review.

Browser CORS origins are controlled by `CORS_ORIGINS` in `backend/.env`, as a comma-separated list. The development default allows common local frontend ports. For temporary public tunnels, allow only the frontend's exact origin, share the URL narrowly, and use non-sensitive test data; this API has no authentication.

## Shared dev server (no Docker for teammates)

`backend/scripts/shared-dev.sh` starts the API and Postgres, seeds the data, and opens a temporary Cloudflare tunnel (`brew install cloudflared`). Send the printed `https://*.trycloudflare.com` URL to the frontend pair and the Centre; they only need that URL as their API base, no Docker. The URL changes each run, and the server stops when you press `Ctrl+C`. Set `CORS_ORIGINS` to the frontend's origin if it runs in a browser:

```bash
CORS_ORIGINS=https://my-frontend.example ./scripts/shared-dev.sh
```

Press `Ctrl+C` to stop. Run `docker compose down -v` to also wipe the database.

## Calling it from Expo

`localhost` only works from the iOS simulator or a browser. From anything else:

| Where the app runs | Base URL |
| --- | --- |
| iOS simulator / Expo web | `http://localhost:8000` |
| Android emulator | `http://10.0.2.2:8000` |
| Physical phone (same Wi-Fi) | `http://<your computer's LAN IP>:8000` |

Find your LAN IP with `ipconfig` (Windows) or `ipconfig getifaddr en0` (macOS). On Windows, allow Docker through the firewall if the phone can't connect.

## Endpoints

| Method | Path |
| --- | --- |
| GET | `/api/categories` |
| GET | `/api/categories/{category_id}/words` |
| GET | `/api/words?category=healthcare&limit=20&offset=0` |
| GET | `/api/words/{word_id}?script=latn` |
| GET | `/api/words/{word_id}/scripts` |
| GET | `/api/words/{word_id}/examples` |
| GET | `/api/words/{word_id}/audio` |
| GET | `/api/words/{word_id}/images` |
| GET | `/api/words/{word_id}/forms` |
| POST | `/api/translate` (JSON body) |
| POST | `/api/pronunciation/score` (multipart: `word_id`, `language`, `reference_id`, `audio` file) |
| GET | `/api/lessons/{lesson_id}/next` |
| POST | `/api/progress` (JSON body: `word_id`, `completed`) |
| GET | `/api/progress` |

Try `word_001` (Doctor). It has the fullest sample data. Category and lesson IDs are `healthcare`, `education`, `housing`, `daily_life`, `transportation`, `employment`. Unknown IDs return 404.

## Editing

- Sample data is in `app/mock_data.py`, and routes are in `app/main.py`.
- Saving a file reloads the server automatically. You don't need to restart.
- After changing `requirements.txt`, run `docker compose up --build`.

## Running without Docker (optional)

You need Python 3.12+. Postgres still runs in Docker (`docker compose up db`). The API works without it, but `/health` will report the database as down.

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

macOS / Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
