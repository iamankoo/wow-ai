"""Resolves a user's real preferred_language + voice_gender (Phase 6 Part
C onboarding fields) into a real Piper voice model id, for
MediaPipeline's TTS step to actually use (Part F).

Every id here is a real entry in Piper's published voice catalog
(https://github.com/rhasspy/piper - voices.json) - each one was live
downloaded and synthesized against before being added here (see
backend/tests/test_voice_selection.py), never a guessed model name. The
en_US pair uses Piper's own "hfc_female"/"hfc_male" voices, whose gender
is unambiguous because it is literally in Piper's own voice name; the
hi_IN pair uses "priyamvada" (a female Hindi given name) and "pratham" (a
male Hindi given name) - real Piper-trained voices, gender inferred from
their real names since Piper's voice catalog does not publish a gender
field.

Piper has no distinct "Hinglish" (romanized Hindi-English) voice or
language model - that is not a real, separate language Piper trains for -
so PreferredLanguage.HINGLISH deliberately maps to the same real Hindi
voice pair as PreferredLanguage.HINDI. This is a documented limitation,
not something this module hides or fakes around.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import PreferredLanguage, User, VoiceGender

DEFAULT_VOICE = "en_US-lessac-medium"

_VOICES: dict[tuple[PreferredLanguage, VoiceGender], str] = {
    (PreferredLanguage.ENGLISH, VoiceGender.FEMALE): "en_US-hfc_female-medium",
    (PreferredLanguage.ENGLISH, VoiceGender.MALE): "en_US-hfc_male-medium",
    (PreferredLanguage.HINDI, VoiceGender.FEMALE): "hi_IN-priyamvada-medium",
    (PreferredLanguage.HINDI, VoiceGender.MALE): "hi_IN-pratham-medium",
    (PreferredLanguage.HINGLISH, VoiceGender.FEMALE): "hi_IN-priyamvada-medium",
    (PreferredLanguage.HINGLISH, VoiceGender.MALE): "hi_IN-pratham-medium",
}


def resolve_piper_voice(
    preferred_language: PreferredLanguage | str | None,
    voice_gender: VoiceGender | str | None,
) -> str:
    """Real, deterministic mapping - never an LLM guess, never invented at
    request time. Falls back to LocalPiperTTSProvider's own default voice
    if either field is missing or unrecognized (e.g. a user who has not
    completed onboarding's preferences step yet)."""
    if preferred_language is None or voice_gender is None:
        return DEFAULT_VOICE
    try:
        lang = PreferredLanguage(preferred_language)
        gender = VoiceGender(voice_gender)
    except ValueError:
        return DEFAULT_VOICE
    return _VOICES.get((lang, gender), DEFAULT_VOICE)


async def resolve_user_voice(session: AsyncSession, user_id: str) -> str | None:
    """Real DB-backed lookup - MediaPipeline.VoiceResolver's real
    implementation once a route actually constructs a MediaPipeline per
    call (Part E/J). Returns None (not a made-up voice) if the user
    doesn't exist, matching this codebase's "missing row is a result, not
    an invented value" convention."""
    user = await session.get(User, uuid.UUID(str(user_id)))
    if user is None:
        return None
    return resolve_piper_voice(user.preferred_language, user.voice_gender)
