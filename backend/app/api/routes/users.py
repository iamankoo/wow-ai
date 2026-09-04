import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.user import User
from app.schemas.brain import UserCreate, UserProfileUpdate, UserRead

router = APIRouter(prefix="/users", tags=["users"])

_ACTIVATION_DURATIONS: dict[str, timedelta | None] = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "5h": timedelta(hours=5),
    "until_stop": None,
}


class ActivationRequest(BaseModel):
    duration: Literal["15m", "1h", "5h", "until_stop", "off"]


async def _apply_activation_expiry(user: User, session: AsyncSession) -> None:
    """Real, lazy expiry (Phase 6 Part G) - this project has no background
    scheduler, so "WOW automatically becomes inactive" is enforced the
    moment anything next reads this user's state, not on a timer. Flips
    and persists call_assistant_enabled the instant active_until has
    passed, so a client never sees a stale "still on" reading."""
    if user.call_assistant_enabled and user.active_until is not None:
        if datetime.now(timezone.utc) >= user.active_until:
            user.call_assistant_enabled = False
            user.active_until = None
            await session.commit()
            await session.refresh(user)


@router.post("", response_model=UserRead, status_code=201)
async def create_user(
    payload: UserCreate, session: AsyncSession = Depends(get_db)
) -> User:
    user = User(**payload.model_dump())
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: uuid.UUID, session: AsyncSession = Depends(get_db)) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await _apply_activation_expiry(user, session)
    return user


@router.post("/{user_id}/activation", response_model=UserRead)
async def set_activation(
    user_id: uuid.UUID, payload: ActivationRequest, session: AsyncSession = Depends(get_db)
) -> User:
    """Phase 6 Part G - the real endpoint the main screen's ON/OFF power
    button and duration chips call directly. Deterministic by design: the
    duration options are fixed UI buttons, not free text, so this bypasses
    the agent/NLU layer entirely rather than routing a button tap through
    a probabilistic classifier - EnableCallAssistantTool/
    DisableCallAssistantTool (natural-language "turn on WOW") remain the
    path for voice/text commands and write the exact same two columns."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.duration == "off":
        user.call_assistant_enabled = False
        user.active_until = None
    else:
        delta = _ACTIVATION_DURATIONS[payload.duration]
        user.call_assistant_enabled = True
        user.active_until = (datetime.now(timezone.utc) + delta) if delta else None

    await session.commit()
    await session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user_profile(
    user_id: uuid.UUID, payload: UserProfileUpdate, session: AsyncSession = Depends(get_db)
) -> User:
    """Phase 6 Part C/N - the real profile-edit path the onboarding and
    profile screens save through. Enforces the 18+ requirement server-side
    (never just a client-side checkbox) and resets mobile_verified/
    email_verified when the corresponding destination actually changes -
    a previously verified code only ever proved control over the old
    phone_number/email, not the new one."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updates = payload.model_dump(exclude_unset=True)

    if "date_of_birth" in updates and updates["date_of_birth"] is not None:
        dob = updates["date_of_birth"]
        today = date.today()
        years = today.year - dob.year
        if (today.month, today.day) < (dob.month, dob.day):
            years -= 1
        if years < 18:
            raise HTTPException(
                status_code=400, detail="WOW requires you to be 18 or older to continue"
            )

    if "phone_number" in updates and updates["phone_number"] != user.phone_number:
        user.mobile_verified = False
    if "email" in updates and updates["email"] != user.email:
        user.email_verified = False

    for field, value in updates.items():
        setattr(user, field, value)

    await session.commit()
    await session.refresh(user)
    return user
