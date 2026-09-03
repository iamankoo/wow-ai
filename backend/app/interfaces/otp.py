"""One-time-code delivery abstraction (Phase 6 Part C - mobile/email
verification).

Mirrors TelephonyProvider's shape: this interface is delivery-only. Code
generation, hashing, expiry and attempt-limiting are real production logic
that lives in app/services/verification_service.py and never changes
between providers - only how a generated code reaches the user's phone/
email is provider-specific.
"""

from abc import ABC, abstractmethod


class OtpDeliveryError(Exception):
    """Raised when a provider cannot confirm the code was handed off for
    delivery. Never swallowed - a failed send must not be reported to the
    caller as success."""


class OtpDeliveryProvider(ABC):
    @abstractmethod
    async def deliver(self, *, channel: str, destination: str, code: str) -> None:
        """Send `code` to `destination` over `channel` ('mobile' or
        'email'). Raises OtpDeliveryError if delivery cannot be confirmed."""
