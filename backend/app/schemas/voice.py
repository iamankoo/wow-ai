from pydantic import BaseModel


class VoiceCommandResponse(BaseModel):
    """Phase 6 Part E/J - the real audio-in/audio-out round trip's result.

    `reply_audio_base64` is genuinely empty (not padded/faked) whenever
    there was nothing real to say back - either the caller's recording had
    no detectable speech at all (`transcript` is also empty then), or the
    agent's action carried no reply text.
    """

    transcript: str
    reply_text: str
    reply_audio_base64: str
    reply_sample_rate: int
    action_type: str
    # Real per-turn detected language ("en"/"hi"/"hi-Latn" - see
    # app.agent.language_detection), None only when there was no real
    # speech to detect a language from (empty transcript). Lets a client
    # (e.g. the mobile app's physical-device voice test) directly observe
    # what WOW actually detected, not just infer it from the reply text.
    language: str | None = None
