"""Real mobile/email one-time-code verification (Phase 6 Part C).

Code generation, hashing, expiry and attempt-limiting are real production
logic - see app/interfaces/otp.py's docstring for why only the delivery
transport is currently a dev stand-in (app/providers/otp/logging_provider.py).
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.otp import OtpDeliveryProvider
from app.models.user import User
from app.models.verification_code import VerificationChannel, VerificationCode


def _hash_code(code: str) -> str:
    # A 6-digit numeric space is far too small for a salted-hash + timing-
    # safe-compare to meaningfully resist brute force on its own -
    # attempt-limiting (see confirm_code below) is the real defense here.
    # The hash exists so a compromised database row doesn't hand out a
    # plaintext code for a still-valid, unconsumed verification.
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class VerificationError(Exception):
    """Base for all caller-facing verification failures - routes map these
    to real HTTP error responses, never a silent success."""


class UserNotFoundError(VerificationError):
    pass


class NoDestinationError(VerificationError):
    """The user has no phone_number/email on file for this channel yet."""


class CodeExpiredOrMissingError(VerificationError):
    pass


class TooManyAttemptsError(VerificationError):
    pass


class IncorrectCodeError(VerificationError):
    pass


class VerificationService:
    def __init__(
        self,
        session: AsyncSession,
        delivery_provider: OtpDeliveryProvider,
        *,
        code_ttl_seconds: int,
        max_attempts: int,
        expose_dev_code: bool,
    ):
        self._session = session
        self._delivery = delivery_provider
        self._ttl = timedelta(seconds=code_ttl_seconds)
        self._max_attempts = max_attempts
        self._expose_dev_code = expose_dev_code

    async def request_code(
        self, *, user_id: str, channel: VerificationChannel
    ) -> str | None:
        """Generates and delivers a real code. Returns the plaintext code
        only when otp_expose_dev_code is on (no real SMS/email vendor
        wired in yet - see module docstring), so callers can still finish
        the real verify flow end to end during development."""
        user = await self._session.get(User, uuid.UUID(str(user_id)))
        if user is None:
            raise UserNotFoundError(user_id)

        destination = user.phone_number if channel == VerificationChannel.MOBILE else user.email
        if not destination:
            raise NoDestinationError(channel.value)

        code = f"{secrets.randbelow(1_000_000):06d}"
        row = VerificationCode(
            user_id=user.id,
            channel=channel,
            destination=destination,
            code_hash=_hash_code(code),
            expires_at=datetime.now(timezone.utc) + self._ttl,
        )
        self._session.add(row)
        await self._session.flush()

        await self._delivery.deliver(channel=channel.value, destination=destination, code=code)

        return code if self._expose_dev_code else None

    async def confirm_code(
        self, *, user_id: str, channel: VerificationChannel, code: str
    ) -> None:
        """Raises on any failure - never returns a falsy "not verified"
        value a caller could accidentally ignore. On success, marks the
        matching User.mobile_verified/email_verified flag True."""
        user = await self._session.get(User, uuid.UUID(str(user_id)))
        if user is None:
            raise UserNotFoundError(user_id)

        stmt = (
            select(VerificationCode)
            .where(
                VerificationCode.user_id == user.id,
                VerificationCode.channel == channel,
                VerificationCode.consumed.is_(False),
            )
            .order_by(VerificationCode.created_at.desc())
        )
        row = (await self._session.execute(stmt)).scalars().first()

        if row is None or row.expires_at < datetime.now(timezone.utc):
            raise CodeExpiredOrMissingError(channel.value)
        if row.attempts >= self._max_attempts:
            raise TooManyAttemptsError(channel.value)

        if _hash_code(code) != row.code_hash:
            row.attempts += 1
            await self._session.flush()
            raise IncorrectCodeError(channel.value)

        row.consumed = True
        if channel == VerificationChannel.MOBILE:
            user.mobile_verified = True
        else:
            user.email_verified = True
        await self._session.flush()
