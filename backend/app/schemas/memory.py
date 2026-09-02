from pydantic import BaseModel

from app.models.memory import MemoryStatus, MemoryType


class MemoryCreateRequest(BaseModel):
    user_id: str
    content: str
    contact_id: str | None = None
    memory_type: MemoryType = MemoryType.SEMANTIC
    # A caller creating a memory directly (not via the agent tool path) is
    # asserting it, not merely observing it in conversation - see docs
    # "Memory safety". Still defaults to the least-trusted tier; explicit
    # user confirmation should use MemoryStatus.USER_APPROVED.
    status: MemoryStatus = MemoryStatus.OBSERVED
    confidence: float | None = None


class MemoryRead(BaseModel):
    id: str
    content: str
    memory_type: MemoryType
    status: MemoryStatus
    confidence: float | None = None


class MemoryApproveRequest(BaseModel):
    user_id: str
    status: MemoryStatus = MemoryStatus.USER_APPROVED
