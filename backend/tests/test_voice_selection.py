"""Phase 6 Part F - the real, deterministic mapping from a user's
preferred_language/voice_gender to a real Piper voice id.

Every voice id resolve_piper_voice can return was live download+synthesize
verified against the real piper-tts package before being added to
app/media/voice_selection.py's table (en_US-lessac-medium and
hi_IN-pratham-medium were already verified in test_local_piper_tts.py;
en_US-hfc_female-medium, en_US-hfc_male-medium, and
hi_IN-priyamvada-medium were verified for this change). This test file
only checks the pure mapping logic - it does not re-download voices.
"""

import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.media.voice_selection import DEFAULT_VOICE, resolve_piper_voice, resolve_user_voice
from app.models.user import PreferredLanguage, User, VoiceGender


@pytest.mark.parametrize(
    "language,gender,expected",
    [
        (PreferredLanguage.ENGLISH, VoiceGender.FEMALE, "en_US-hfc_female-medium"),
        (PreferredLanguage.ENGLISH, VoiceGender.MALE, "en_US-hfc_male-medium"),
        (PreferredLanguage.HINDI, VoiceGender.FEMALE, "hi_IN-priyamvada-medium"),
        (PreferredLanguage.HINDI, VoiceGender.MALE, "hi_IN-pratham-medium"),
        # Piper has no real distinct "Hinglish" voice - Hinglish deliberately
        # reuses the real Hindi voice pair rather than inventing one.
        (PreferredLanguage.HINGLISH, VoiceGender.FEMALE, "hi_IN-priyamvada-medium"),
        (PreferredLanguage.HINGLISH, VoiceGender.MALE, "hi_IN-pratham-medium"),
    ],
)
def test_resolves_every_real_language_gender_combination(language, gender, expected):
    assert resolve_piper_voice(language, gender) == expected


def test_accepts_raw_string_values_as_the_api_layer_would_pass_them():
    # Pydantic/SQLAlchemy hand back the enum's .value (a plain str) at the
    # API boundary just as often as the enum member itself - both must work.
    assert resolve_piper_voice("english", "male") == "en_US-hfc_male-medium"


def test_missing_fields_fall_back_to_the_default_voice():
    assert resolve_piper_voice(None, VoiceGender.FEMALE) == DEFAULT_VOICE
    assert resolve_piper_voice(PreferredLanguage.ENGLISH, None) == DEFAULT_VOICE


def test_unrecognized_values_fall_back_to_the_default_voice():
    assert resolve_piper_voice("klingon", "male") == DEFAULT_VOICE


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark_db = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set; skipping DB integration"
)


@pytest.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytestmark_db
async def test_resolve_user_voice_reads_the_real_persisted_preferences(session):
    user = User(
        display_name="Priya",
        phone_number="+10000000030",
        preferred_language=PreferredLanguage.HINDI,
        voice_gender=VoiceGender.FEMALE,
    )
    session.add(user)
    await session.flush()

    voice = await resolve_user_voice(session, str(user.id))

    assert voice == "hi_IN-priyamvada-medium"


@pytestmark_db
async def test_resolve_user_voice_returns_none_for_an_unknown_user(session):
    voice = await resolve_user_voice(session, str(uuid.uuid4()))
    assert voice is None
