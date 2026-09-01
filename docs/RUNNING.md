# Running WOW AI locally

## Prerequisites

- Docker Desktop (Postgres + Redis + backend container)
- Python 3.10+ (only needed to run the backend outside Docker, or its tests)
- Flutter SDK (only needed for the mobile app - not required for the backend)

## 1. Backend + database via Docker Compose

```bash
cp .env.example .env
docker compose up -d db redis backend
```

- Postgres (with pgvector) is exposed on host port **5433** (mapped to the
  container's 5432, to avoid clashing with any other local Postgres).
- Redis is exposed on host port **6380** (mapped to the container's 6379).
- The backend is exposed on **8000** and creates its schema automatically on
  startup.

Verify:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## 2. Backend without Docker (venv)

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

# point at the Dockerized Postgres/Redis (see step 1), or your own instances
export DATABASE_URL=postgresql+asyncpg://wow:wow@localhost:5433/wow_ai
export REDIS_URL=redis://localhost:6380/0

uvicorn app.main:app --reload
```

## 3. Backend tests

```bash
cd backend
.venv/Scripts/activate
python -m pytest -v
```

Most tests (brain logic, rule-based NLU, model metadata, health endpoint) run
without any database. One test (`tests/test_integration_db.py`) exercises the
full stack - contacts, context profiles, pgvector memory search, and the
brain - against a real Postgres instance. It's skipped automatically unless
`TEST_DATABASE_URL` is set:

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://wow:wow@localhost:5433/wow_ai
python -m pytest -v
```

## 4. Try the brain over HTTP

```bash
USER_ID=$(curl -s -X POST localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"display_name":"Aniket","phone_number":"+10000000000"}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -s -X POST localhost:8000/contacts \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$USER_ID\",\"name\":\"Priya\",\"phone_number\":\"+19999999999\"}"

curl -s -X POST localhost:8000/brain/command \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$USER_ID\",\"text\":\"Hello there\",\"caller_number\":\"+19999999999\"}"
```

## 5. Mobile app

The Flutter project under `mobile/` was hand-scaffolded (`lib/`, `test/`,
`android/`) because the Flutter SDK isn't installed in this environment - it
has **not** been run or built yet. Once Flutter is installed:

```bash
cd mobile
flutter pub get
flutter test
flutter run   # Android emulator or device
```

The app assumes the backend is reachable at `http://10.0.2.2:8000` from an
Android emulator (the emulator's alias for the host's `localhost`) - see
`mobile/lib/main.dart`. Update `kDefaultBackendBaseUrl` for a physical device
on the same network.

If `android/` fails to sync in Android Studio, the safest fix is to run
`flutter create .` inside `mobile/` once the SDK is present - it will
regenerate/repair the Gradle wrapper and any platform boilerplate in place
without touching `lib/`.
