from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_verification_service
from app.models.verification_code import VerificationChannel
from app.schemas.verification import (
    VerificationConfirmRequest,
    VerificationConfirmResponse,
    VerificationRequestResponse,
)
from app.services.verification_service import (
    CodeExpiredOrMissingError,
    IncorrectCodeError,
    NoDestinationError,
    TooManyAttemptsError,
    UserNotFoundError,
    VerificationService,
)

router = APIRouter(prefix="/users/{user_id}/verify", tags=["verification"])


@router.post("/{channel}/request", response_model=VerificationRequestResponse)
async def request_verification_code(
    user_id: str,
    channel: VerificationChannel,
    service: VerificationService = Depends(get_verification_service),
) -> VerificationRequestResponse:
    try:
        dev_code = await service.request_code(user_id=user_id, channel=channel)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except NoDestinationError:
        raise HTTPException(
            status_code=400,
            detail=f"No {channel.value} on file to send a verification code to",
        )
    return VerificationRequestResponse(sent=True, dev_code=dev_code)


@router.post("/{channel}/confirm", response_model=VerificationConfirmResponse)
async def confirm_verification_code(
    user_id: str,
    channel: VerificationChannel,
    payload: VerificationConfirmRequest,
    service: VerificationService = Depends(get_verification_service),
) -> VerificationConfirmResponse:
    try:
        await service.confirm_code(user_id=user_id, channel=channel, code=payload.code)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except CodeExpiredOrMissingError:
        raise HTTPException(
            status_code=400, detail="No valid verification code - request a new one"
        )
    except TooManyAttemptsError:
        raise HTTPException(
            status_code=429, detail="Too many incorrect attempts - request a new code"
        )
    except IncorrectCodeError:
        raise HTTPException(status_code=400, detail="Incorrect code")
    return VerificationConfirmResponse(verified=True)
