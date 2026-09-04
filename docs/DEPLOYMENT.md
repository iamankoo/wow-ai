# Deployment (Phase 7)

## Backend: Render

The backend is deployed from `render.yaml` (a Render Blueprint) as a single
free-tier Docker web service:

- Service: `wow-ai-backend` at https://wow-ai-backend-4h49.onrender.com
- Build: `backend/Dockerfile` (unchanged production entrypoint - `uvicorn
  app.main:app`, now binding `$PORT` instead of a hardcoded 8000 so it
  matches the port Render actually health-checks)
- Health check: `GET /health`

### Database

Render allows only one active free-tier Postgres database per account, and
this account's existing one belongs to a different project. Production
therefore uses a free [Neon](https://neon.tech) Postgres project
(`wow-ai`, region `AWS US East 2 (Ohio)`) instead of a Render-managed
database. `DATABASE_URL` is set directly in the Render dashboard's
Environment tab (`render.yaml` declares it with `sync: false` so it's never
committed in plaintext) as:

```
postgresql+asyncpg://<user>:<password>@<neon-host>/neondb?ssl=require
```

pgvector isn't pre-enabled on a fresh Neon/Render Postgres instance (unlike
the local dev `pgvector/pgvector` Docker image), so `app/main.py`'s startup
lifespan now runs `CREATE EXTENSION IF NOT EXISTS vector` before
`Base.metadata.create_all` - idempotent, safe on every boot.

The fixed demo-user row the app hardcodes as `kDemoUserId`
(`00000000-0000-0000-0000-000000000001`, see `mobile/lib/core/constants.dart`)
isn't created by any onboarding flow when the row is missing entirely
(`SplashScreen._route` only routes to onboarding when a user row already
exists but is incomplete - see that file's doc comment). On a fresh
database this row was seeded once by hand via Neon's SQL editor with an
empty profile, which is what actually makes the app's onboarding flow run
on first real launch against production.

### Provider mode: zero-ML-dependency by default

Render's free plan (512MB RAM, no persistent disk) can't run the real
Brain v3 model or self-hosted faster-whisper/Piper, so production currently
runs the repository's existing zero-dependency defaults:

- `MODEL_PROVIDER=rule_based` (Brain v3/`local_wow` stays fully intact in
  the codebase and training pipeline - just not loaded in this deployment)
- `STT_PROVIDER=simulated`, `TTS_PROVIDER=simulated`

This is not a hosted AI API substitute - it's the same rule-based/simulated
code path the project already uses for dependency-free development and
tests (see `backend/app/config.py`). `/brain/voice-command` still runs the
full real `MediaPipeline`, including the real WebRTC VAD stage
(`webrtcvad-wheels`, added to the base `backend/requirements.txt` since it
runs unconditionally regardless of STT/TTS provider) - only transcription
and synthesis are simulated.

### Upgrading to the real self-hosted stack

To run real Brain v3 (`local_wow`) + real faster-whisper + real Piper in
production:

1. Move the Render web service to a paid plan with a persistent disk large
   enough for the model artifacts (Brain v3's deployable weights are
   ~1.5GB per `docs/implementation-status.md`; faster-whisper's `base`
   model and Piper voices are much smaller).
2. Package `training/models/wow-brain/v3` (config/weights/tokenizer only,
   no training checkpoints - matching the existing Kaggle packaging
   convention in `docs/implementation-status.md`) as a tar.gz and attach it
   to a dedicated GitHub Release (e.g. tag `models-v3`), then add a step to
   the Render build/start command that downloads and extracts it into
   `WOW_MODEL_DIR` on the persistent disk if not already present.
3. Set `MODEL_PROVIDER=local_wow`, `STT_PROVIDER=local_whisper`,
   `TTS_PROVIDER=local_piper`, and install
   `requirements-local-model.txt`/`requirements-local-stt.txt`/
   `requirements-local-tts.txt` in the Docker build.
4. Re-run the verification steps below against the upgraded service.

No hosted third-party AI API is introduced at any point in this path.

### CORS

`app/main.py` adds a permissive `CORSMiddleware` (`allow_origins=["*"]`).
The Android app is the only real client and carries no browser
cookies/session to protect, so there's no origin to restrict to - this
exists so the deployed API isn't blocked for any HTTP client (the app, or a
browser hitting it directly for debugging).

## Mobile: production backend URL

`mobile/lib/main.dart` picks the backend URL by build mode
(`kReleaseMode` from `package:flutter/foundation.dart`), not a hardcoded
constant:

- Debug builds: `http://10.0.2.2:8000` (Android emulator's alias for the
  developer's own laptop, unchanged from Phase 6)
- Release builds: `https://wow-ai-backend-4h49.onrender.com`

The native call-screening path
(`WowCallScreeningService.kt`/`WowAutoAnswer.kt`) reads the same URL from
`BuildConfig.BACKEND_BASE_URL`, set per Gradle build type in
`mobile/android/app/build.gradle.kts` the same way, so a release APK's
real incoming-call handling also reaches Render, not a laptop.

## Release signing

`v1.0.0` was debug-signed (`signingConfig = signingConfigs.getByName("debug")`
in `build.gradle.kts`, unchanged by Phase 7). An Android install can only be
upgraded in place by a build signed with the *same* key, so every future
release must keep using this exact `signingConfig` and the same
`~/.android/debug.keystore` file used to build `v1.0.0` (dated 2026-04-11,
predating the `v1.0.0` release) - never regenerate or replace that keystore
file on the build machine.
