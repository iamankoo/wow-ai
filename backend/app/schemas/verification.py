from pydantic import BaseModel


class VerificationRequestResponse(BaseModel):
    sent: bool
    # Only populated while no real SMS/email vendor is wired in - see
    # app/config.py's otp_expose_dev_code / app/providers/otp/
    # logging_provider.py.
    dev_code: str | None = None


class VerificationConfirmRequest(BaseModel):
    code: str


class VerificationConfirmResponse(BaseModel):
    verified: bool
