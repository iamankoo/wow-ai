# WOW AI - security boundary (Phase 1)

Scope of this document: what protects the backend **today**, what it does not,
and what is deliberately deferred. It is written for the first real Plivo test,
where the backend is reachable from the public internet through a tunnel.

## What was wrong before Phase 1 (audit finding, 2026-10-01)

- No REST route required authentication. Anyone who knew a user UUID (the demo
  UUID is public in the repository) could read profile/call data and call
  `POST /users/{id}/activation` to switch WOW on.
- `WS /telephony/plivo/stream` accepted any connection: anyone who found the URL
  could run STT/TTS/Brain and write fake call records.
- The Plivo Answer webhook skipped signature validation when
  `PLIVO_AUTH_TOKEN` was unset.
- Spoken OTP/PIN/card numbers were stored verbatim in call transcripts.

## What protects the backend now

### 1. Plivo Answer webhook - `POST /telephony/plivo/answer`

- Verified with Plivo's documented `X-Plivo-Signature-V3` (HMAC-SHA256, constant
  time). **Fails closed**: with no `PLIVO_AUTH_TOKEN` it answers `503`, never
  "skip validation". The only exception is the explicit, local-only
  `PLIVO_ALLOW_UNSIGNED_WEBHOOKS=true`, which is ignored whenever
  `PUBLIC_BASE_URL` is set.
- Behind a tunnel uvicorn sees `http://localhost:8000/...` but Plivo signed the
  public `https://...` URL; the signed URL is therefore rebuilt from
  `PUBLIC_BASE_URL`.
- The activation gate runs next: WOW off/expired, no `CallUUID`, a DB error, the
  concurrent-stream cap, or a full token store all answer `<Hangup/>` - no
  stream, no token, no STT/Brain/TTS.

### 2. Plivo media WebSocket - `WS /telephony/plivo/stream`

Plivo documents **no signature on the WebSocket handshake** (its `extraHeaders`
attribute is delivered in the `start` event, after the socket is open). So:

- the *signed* Answer webhook mints a **short-lived (default 120 s), single-use,
  unpredictable** token (`secrets.token_urlsafe(32)`, stored only as a SHA-256
  digest, never logged) bound to that call's `CallUUID`, and puts it in the
  Stream URL (`wss://.../telephony/plivo/stream?token=...`);
- the token is validated and **consumed before the WebSocket is accepted** (first
  dependency of the route, before the pipeline/recorder are even built). Missing,
  unknown, expired or replayed -> handshake refused;
- the `start` event's call id must equal the CallUUID the token was minted for
  (mismatch -> connection dropped, nothing recorded). If Plivo's start event
  carries no recognisable call id this check is skipped with a warning and the
  token alone authenticates the connection (Plivo publishes no verbatim JSON for
  inbound events - to be confirmed by the first real call);
- caps: `PLIVO_MAX_CONCURRENT_STREAMS` (default 2), `PLIVO_MAX_CALL_SECONDS`
  (default 1800), bounded audio queue, oversized media frames dropped.

Limit: token state is in process memory -> single backend process only.

### 3. Every other REST route - shared API key

All routers except `/health` and the Plivo routes depend on `require_api_key`
(`app/security.py`): header `X-WOW-API-Key`, constant-time compare against
`API_ACCESS_KEY`.

- **Fail-closed startup:** the backend refuses to start when `PUBLIC_BASE_URL`
  is set but `API_ACCESS_KEY` or `PLIVO_AUTH_TOKEN` is not.
- OpenAPI/`/docs` are not served when a key or public URL is configured.
- Exposed state-changing/private routes this closes: `POST /users`,
  `PATCH /users/{id}`, `POST /users/{id}/activation`, verification, `/brain/*`,
  `/calls/*`, `/users/{id}/calls*`, `/contacts`, `/memories`, `/feedback/*`
  (including export/delete/consent).
- The Android app sends the key (`--dart-define=WOW_API_KEY=...` for Dart, the
  `WOW_API_KEY` env var at build time for the native call-screening code).

**What this is not:** it is one shared secret for a single-tenant deployment,
not per-user authentication, and a key compiled into an APK can be extracted by
someone with the APK. It stops the open internet; it does not isolate users from
each other, and it is not a substitute for real accounts (Phase 3).

### 4. Secrets handling

All credentials are environment-only (`Settings`): `PLIVO_AUTH_ID`,
`PLIVO_AUTH_TOKEN`, `API_ACCESS_KEY`, `SECRET_KEY`, `DATABASE_URL`. `.env` is
git-ignored; `.env.example` holds placeholders only. A repository scan (tracked +
untracked files + history) found no committed credentials. Credentials, tokens
and transcripts are never logged or returned by an API; tests assert this for the
Plivo token and the stream token.

### 5. Stored transcripts

`CallRecorder.record_turn` redacts **card-like numbers and OTP/PIN codes** before
persisting any turn (both speakers). Phone numbers, emails and names are
**deliberately kept** in the owner's own call history - a message-taking
assistant exists to preserve callback details, and the data sits behind the API
key and the retention window (`CALL_RETENTION_DAYS`, 15). Regex redaction is
best-effort (see `docs/SELF_LEARNING.md`).

## Deferred to Phase 3 (known, accepted for the first Plivo test)

| Item | Why deferred |
|---|---|
| Per-user accounts/authorization (real auth, user ownership checks) | Needs an account system; single shared key is the minimum boundary for one owner. |
| Production (Render) is **not** yet key-protected | The installed app (v1.2.0) sends no key; enforcing it before a build that does would lock the app out. Set `API_ACCESS_KEY` on Render together with the next mobile release. Also: production OTP codes are still exposed to the client (`OTP_EXPOSE_DEV_CODE=true`). |
| Shared token store (Redis) / multi-worker | In-process store is fine for one uvicorn process. |
| Full PII redaction of stored transcripts, per-call delete, in-app data deletion | Needs product decisions + endpoints; the app's privacy screen states plainly that there is no in-app delete yet. |
| Agent conversation state/memory may hold raw utterances | Same reason; unchanged by Phase 1. |
| Caller-facing recording/AI disclosure on the call | Product/legal decision (the greeting is a bare "Hello."). |
| Rate limiting on REST routes | Not needed behind a secret key for one owner. |
| Restrictive CORS | No browser/cookie client; header-key auth. |

## Verifying it

`backend/tests/`: `test_plivo_stream_tokens.py`, `test_plivo_ws_security.py`,
`test_telephony_plivo_answer.py`, `test_api_key_security.py`,
`test_plivo_stream_parser.py`, `test_activation_and_consent_api.py`. None of these
proves a real Plivo call works - only a real external call can.
