from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.user import User
from app.schemas.brain import UserCreate, UserProfileUpdate, UserRead

router = APIRouter(prefix="/users", tags=["users"])


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
async def get_user(user_id: str, session: AsyncSession = Depends(get_db)) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user_profile(
    user_id: str, payload: UserProfileUpdate, session: AsyncSession = Depends(get_db)
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
