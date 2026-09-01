from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.contact import Contact
from app.schemas.brain import ContactCreate, ContactRead

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("", response_model=ContactRead, status_code=201)
async def create_contact(
    payload: ContactCreate, session: AsyncSession = Depends(get_db)
) -> Contact:
    contact = Contact(**payload.model_dump())
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


@router.get("", response_model=list[ContactRead])
async def list_contacts(
    user_id: str, session: AsyncSession = Depends(get_db)
) -> list[Contact]:
    result = await session.execute(
        select(Contact).where(Contact.user_id == user_id)
    )
    return list(result.scalars().all())
