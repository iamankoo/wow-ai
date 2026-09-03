"""Dev-mode OtpDeliveryProvider - not a real SMS/email vendor integration
(same "do not fake functionality" principle as
app/providers/telephony/simulated.py). No SMS gateway or transactional-
email account exists in this environment or repository, so real delivery
of a phone/email code requires a real external dependency (e.g. Twilio for
SMS, SendGrid/SES for email) that this project does not have credentials
for. Real gap, documented rather than faked.

This provider "delivers" a code by logging it server-side - the
verification STATE MACHINE around it (app/services/verification_service.py:
generation, hashing, expiry, attempt-limiting, marking verified) is 100%
real and identical regardless of which OtpDeliveryProvider is wired in;
only the transport is a stand-in. Swapping in a real SMS/email provider
later is a drop-in replacement - zero change to the service or routes.
"""

import logging

from app.interfaces.otp import OtpDeliveryProvider

logger = logging.getLogger("wow.otp.logging_provider")


class LoggingOtpDeliveryProvider(OtpDeliveryProvider):
    async def deliver(self, *, channel: str, destination: str, code: str) -> None:
        logger.warning(
            "OTP DEV DELIVERY (no real %s vendor configured) -> %s: %s",
            channel,
            destination,
            code,
        )
