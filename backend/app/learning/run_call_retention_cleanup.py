"""Manual/cron entrypoint for call retention cleanup (see call_retention.py).

Run it:

    python -m app.learning.run_call_retention_cleanup

No scheduler is wired up in Phase 1 (no Celery/APScheduler dependency has
been introduced - see docs "Do not overengineer prematurely"). This script
is meant to be invoked by an external scheduler (cron, Windows Task
Scheduler, a Docker Compose one-shot service) exactly the same way
`docs/KAGGLE_TRAINING.md`'s training commands are human/externally
triggered rather than autonomously scheduled from inside the app.
"""

import asyncio
import logging

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.learning.call_retention import CallRetentionPolicy, cleanup_expired_calls

logger = logging.getLogger("wow_ai.retention")


async def main() -> int:
    settings = get_settings()
    policy = CallRetentionPolicy(max_age_days=settings.call_retention_days)
    async with AsyncSessionLocal() as session:
        deleted = await cleanup_expired_calls(session, policy)
        await session.commit()
    logger.info("call_retention_cleanup", extra={"calls_deleted": deleted})
    return deleted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
