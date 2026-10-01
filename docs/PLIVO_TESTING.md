# Real Plivo call test - PC + Cloudflare Tunnel + Plivo trial

The first real-caller milestone: a real phone dials a real Plivo India
number, WOW answers with a real Piper "Hello.", the caller speaks, real
faster-whisper transcribes it, WOW Brain v3 + Agent Core decide what to
do, and a real Piper female voice replies - multiple turns, ending in a
real saved transcript/summary. Everything except the phone network and
Plivo's own infrastructure runs on your own PC. No simulated caller audio
anywhere in this path - see docs/ARCHITECTURE.md "Real telephony" for the
architecture and what was/wasn't independently verified before this was
built.

## What this needs (nothing purchased by an agent - you do this part)

1. **Udyam MSME registration** (or GST/COI) - required by Plivo before
   renting an Indian number (`plivo.com/docs/numbers/rent-india-numbers`).
2. **A Plivo account**, KYC'd, with a rented India number and Audio
   Streaming enabled on it. Plivo's own no-card trial credit (₹1,000, per
   `plivo.com/pricing/`) covers the number rental and far more than 10
   test calls - see the session's Plivo verification findings, quoted in
   docs/ARCHITECTURE.md.
3. **Cloudflare Tunnel** (`cloudflared`) or ngrok - Plivo must reach this
   backend over a public `https`/`wss` URL; `localhost` cannot work.
4. **WOW Brain v3 artifacts** present at `training/models/wow-brain/v3`
   (already on disk if you've trained/recovered it - `metadata.json`
   should exist there).
5. Real STT/TTS installed: `pip install -r backend/requirements-local-stt.txt -r backend/requirements-local-tts.txt -r backend/requirements-local-model.txt`
   (faster-whisper, piper-tts, torch/transformers).

## 1. Make sure the demo user has a female voice set

The Plivo bridge handles every call as the one configured WOW user
(`Settings.demo_user_id`, same `00000000-0000-0000-0000-000000000001`
convention the Android app already hardcodes). For Piper's real
`en_US-hfc_female-medium` (or `hi_IN-priyamvada-medium`) voice to be
picked automatically (`app/media/voice_selection.py`), that user row
needs `voice_gender=FEMALE`. If it doesn't exist yet or isn't set:

```
POST /users          (header X-WOW-API-Key required - see 1c)
{"display_name": "Aniket", "phone_number": "+91...", "preferred_language": "english", "voice_gender": "female"}
```

(or `PATCH /users/{demo_user_id}` if the row already exists from earlier
onboarding). Confirm with `GET /users/{demo_user_id}`.

## 1b. Activate WOW before calling (new: a real safety gate, not optional)

WOW must never activate itself. `POST /telephony/plivo/answer` now checks
the same `call_assistant_enabled`/`active_until` fields the Android app's
activation UI writes - if WOW isn't activated, the call is hung up
(`<Hangup/>`) instead of being answered. Turn it on the same way the app
does, before your test call:

```
POST /users/{demo_user_id}/activation
{"duration": "1h"}
```

(`"15m" | "1h" | "5h" | "until_stop"`.) If you skip this, the call will
ring and then immediately disconnect - that's this gate working
correctly, not a bug.

## 1c. Required secrets - the backend will not start without them

Because the backend is reachable from the internet through the tunnel, Phase 1
(see `docs/SECURITY.md`) makes two secrets **mandatory** whenever
`PUBLIC_BASE_URL` is set - the backend refuses to start otherwise:

- `PLIVO_AUTH_TOKEN` - from the Plivo console. Used to verify
  `X-Plivo-Signature-V3` on the Answer webhook. Without it the webhook answers
  `503` (it no longer "skips validation"). `PLIVO_AUTH_ID` is optional, reserved
  for Plivo REST calls.
- `API_ACCESS_KEY` - a long random value you generate
  (`python -c "import secrets; print(secrets.token_urlsafe(32))"`). Every REST
  route (`/users/...`, `/calls/...`, `/brain/...`) now requires it in the
  `X-WOW-API-Key` header, so the public tunnel cannot be used to read your data
  or activate WOW. `/health` and the Plivo routes are exempt (Plivo
  authenticates itself, below).

Never commit real values - put them in real environment variables or the
git-ignored `backend/.env`. The REST calls in section 1/1b/6 below then need
`-H "X-WOW-API-Key: $API_ACCESS_KEY"`.

How the stream is protected: the (signed) Answer webhook returns a Stream URL
carrying a single-use token valid ~2 minutes and bound to that call's
`CallUUID`; the WebSocket is refused unless it presents it. This is why
`wss://.../telephony/plivo/stream` cannot be used by anyone who merely finds the
URL. Whether Plivo preserves the query string when it opens the WebSocket is
standard behaviour but **unconfirmed against a live call** - see "What to watch
for".

Local, tunnel-less experiments only: with `PUBLIC_BASE_URL` **unset**,
`PLIVO_ALLOW_UNSIGNED_WEBHOOKS=true` lets you POST to the Answer URL by hand
without a signature. It is ignored the moment `PUBLIC_BASE_URL` is set.

## 2. Start Cloudflare Tunnel first (you need its URL before starting the backend)

```
cloudflared tunnel --url http://localhost:8000
```

Copy the `https://<random-subdomain>.trycloudflare.com` URL it prints.

## 3. Start the backend with real providers

```
cd backend
set STT_PROVIDER=local_whisper
set TTS_PROVIDER=local_piper
set MODEL_PROVIDER=local_wow
set AGENT_RUNTIME=wow_agent
set PUBLIC_BASE_URL=https://<your-tunnel-subdomain>.trycloudflare.com
set PLIVO_AUTH_TOKEN=<your real Plivo Auth Token - see 1c>
set API_ACCESS_KEY=<your generated key - see 1c>
alembic upgrade head
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000
```

(`set` is Windows `cmd`; use `$env:NAME="value"` in PowerShell or
`export NAME=value` in bash - or put these in `backend/.env`, see
`.env.example`.)

Real STT/TTS/Brain v3 loading eagerly at boot means first-request latency
is already paid before your first real call - watch the startup logs for
each provider loading successfully before calling the number.

## 4. Point the Plivo number at this backend

In the Plivo console, set the rented number's (or an Application's)
**Answer URL** to:

```
https://<your-tunnel-subdomain>.trycloudflare.com/telephony/plivo/answer
```

Method: `POST`.

## 5. Call it

Dial the Plivo number from a real phone. Expected:

1. WOW answers, you hear a real synthesized "Hello." (Piper, female voice).
2. Speak naturally - e.g. "Hi, is Aniket available?"
3. After you stop speaking, real faster-whisper transcribes it, WOW Brain
   v3 + Agent Core decide a reply, and you hear it spoken back.
4. Keep talking - multiple turns work the same way.
5. Hang up (or stay silent - the call will still finalize whatever was
   captured, per `MediaPipeline.stream_call_audio`'s trailing-audio
   handling).

## 6. Verify it actually happened for real

```
GET /users/{demo_user_id}/calls
GET /calls/{call_id}          # real transcript + summary
GET /users/{demo_user_id}/calls/today-summary
```

The backend's own terminal also prints a `WOW CALL HANDLED` log line at
call end (caller number, duration, turn count, summary) -
`app/observability/notifications.py`'s real, minimal notification for
this first test; see that module's docstring for why it's a log line, not
a phone push notification, at this stage.

## What to watch for (genuinely unverified until this first real call)

- **Does Plivo keep the `?token=` query string when it opens the WebSocket?**
  If the stream is refused, the backend log shows `plivo stream: connection
  rejected (missing)`. That means Plivo dropped the query string; the documented
  fallback is `extraHeaders` (delivered in the `start` event) - needs a small
  change, not a redesign. Rejections `(invalid)`/`(expired)` mean the token was
  presented but unknown/late/replayed (Plivo retries a failed connection twice).
- **The exact JSON of Plivo's *inbound* `start`/`media` events.** Plivo's docs
  name the fields (`start`: streamId, callId, from, to, mediaFormat; `media`:
  base64 payload) but publish no verbatim sample. The parser accepts
  `start.callId` (+ common casings, flat fallback) and `media.payload` (flat
  `payload` fallback) and ignores `track: outbound`. Watch for
  `start event carried no recognizable call id` (call-id correlation skipped, the
  token still authenticated the stream) and `media event with no recognizable
  payload field` (audio would be silently dropped - a one-line fix in
  `_extract_media_payload`).
- Whether closing our WebSocket (`end_call`) actually hangs up the underlying
  PSTN call, or the caller has to hang up themselves - not independently
  confirmed; see `PlivoTelephonyProvider.end_call`'s docstring for the documented
  follow-up (Plivo's REST Call-hangup API) if it doesn't.
- Whether an unverified/trial Plivo account can really receive a call from an
  arbitrary outside number with zero extra step.
- The signature check runs over the URL rebuilt from `PUBLIC_BASE_URL`; if every
  call shows `signature validation failed`, compare that URL with what the Plivo
  console has configured for the Answer URL (scheme, host, path, no trailing
  differences).

## Known limitation carried over unchanged

`answer_call`/`end_call` in `PlivoTelephonyProvider` are real but
minimal - see the class docstring for exactly what each does and doesn't
do; nothing here executes `ANSWER_CALL`/`TRANSFER_CALL`/`END_CALL` as
agent-predicted actions (still deferred, unchanged - see
`docs/implementation-status.md` "Agent Core completion").
