import enum
from datetime import date

from sqlalchemy import Boolean, Date, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class PreferredLanguage(str, enum.Enum):
    """WOW's initially-supported conversation languages (Phase 6 Part F)."""

    HINDI = "hindi"
    HINGLISH = "hinglish"
    ENGLISH = "english"


class VoiceGender(str, enum.Enum):
    """Which LocalPiperTTSProvider voice family to synthesize replies with.
    Female is the WOW default (Phase 6 Part F); male is the alternative -
    both are real local Piper voices, never a cloud voice provider."""

    FEMALE = "female"
    MALE = "male"


class User(UUIDPKMixin, TimestampMixin, Base):
    """The person WOW AI works on behalf of (the phone owner)."""

    __tablename__ = "users"

    display_name: Mapped[str] = mapped_column(String(120))
    phone_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Set only by VerificationService.confirm_code() after a real code
    # match - never set directly by a profile edit. Editing phone_number/
    # email resets the corresponding flag (see routes/verification.py),
    # since a verified code was only ever proof of control over the old
    # destination.
    mobile_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Phase 6 Part E - set once the initial "talk to WOW" personalization
    # call (real STT/Agent/TTS, not a questionnaire) has happened. Distinct
    # from profile completeness: this is a one-time event, not derivable
    # from other fields.
    personalization_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    preferred_language: Mapped[PreferredLanguage] = mapped_column(
        Enum(PreferredLanguage, name="preferred_language"),
        default=PreferredLanguage.ENGLISH,
    )
    voice_gender: Mapped[VoiceGender] = mapped_column(
        Enum(VoiceGender, name="voice_gender"), default=VoiceGender.FEMALE
    )

    # Default consent for new feedback events submitted without an explicit
    # per-submission override - conservative by design (opt-in, not
    # opt-out). See docs/SELF_LEARNING.md "Privacy and consent".
    training_data_consent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Whether WOW is currently authorized to answer/handle incoming calls on
    # this user's behalf - written by the enable_call_assistant/
    # disable_call_assistant agent tools (app/agent/builtin_tools.py), off
    # by default so automation is always opt-in.
    call_assistant_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def age(self) -> int | None:
        if self.date_of_birth is None:
            return None
        today = date.today()
        years = today.year - self.date_of_birth.year
        # Subtract one if this year's birthday hasn't happened yet.
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            years -= 1
        return years

    @property
    def is_adult(self) -> bool:
        age = self.age
        return age is not None and age >= 18

    @property
    def profile_complete(self) -> bool:
        """WOW's real activation gate (Phase 6 Part C) - not a separate
        flag that could drift from the fields it depends on."""
        return bool(
            self.display_name
            and self.phone_number
            and self.is_adult
            and self.mobile_verified
            and self.email_verified
        )
