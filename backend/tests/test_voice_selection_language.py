"""app.media.voice_selection.resolve_voice_for_language - real per-turn,
per-detected-language voice resolution, preserving the user's real
voice_gender. Real SQLite-backed User row, not mocked."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.media.voice_selection import resolve_voice_for_language
from app.models.user import PreferredLanguage, User, VoiceGender


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
async def female_user(session) -> str:
    user = User(
        display_name="Aniket",
        phone_number="+910000000123",
        preferred_language=PreferredLanguage.ENGLISH,  # static profile default
        voice_gender=VoiceGender.FEMALE,
    )
    session.add(user)
    await session.commit()
    return str(user.id)


async def test_detected_english_resolves_the_real_female_english_voice(session, female_user):
    voice = await resolve_voice_for_language(session, female_user, "en")
    assert voice == "en_US-hfc_female-medium"


async def test_detected_hindi_resolves_the_real_female_hindi_voice(session, female_user):
    voice = await resolve_voice_for_language(session, female_user, "hi")
    assert voice == "hi_IN-priyamvada-medium"


async def test_detected_hinglish_resolves_the_same_real_female_hindi_voice(session, female_user):
    """Piper has no distinct Hinglish voice model - reuses the real Hindi
    voice, same as the existing PreferredLanguage.HINGLISH mapping."""
    voice = await resolve_voice_for_language(session, female_user, "hi-Latn")
    assert voice == "hi_IN-priyamvada-medium"


async def test_voice_gender_is_preserved_across_a_language_switch(session):
    male_user = User(
        display_name="Bob",
        phone_number="+910000000124",
        preferred_language=PreferredLanguage.ENGLISH,
        voice_gender=VoiceGender.MALE,
    )
    session.add(male_user)
    await session.commit()
    user_id = str(male_user.id)

    en_voice = await resolve_voice_for_language(session, user_id, "en")
    hi_voice = await resolve_voice_for_language(session, user_id, "hi")

    assert en_voice == "en_US-hfc_male-medium"
    assert hi_voice == "hi_IN-pratham-medium"


async def test_unknown_language_code_falls_back_to_the_user_s_own_preference(session, female_user):
    voice = await resolve_voice_for_language(session, female_user, "fr")
    assert voice == "en_US-hfc_female-medium"  # the seeded user's own preferred_language=ENGLISH


async def test_nonexistent_user_returns_none_not_a_made_up_voice(session):
    voice = await resolve_voice_for_language(session, str(uuid.uuid4()), "hi")
    assert voice is None
