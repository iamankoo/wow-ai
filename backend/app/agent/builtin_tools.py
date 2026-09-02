"""The initial, safe internal-operation tools available to the WOW Agent
orchestrator (see docs "Tool system"). Each wraps an existing storage
abstraction - no tool here has a side effect beyond what
`MemoryStore`/`SummaryRepository` already expose, and every argument is
schema-validated by `Tool.validate` before `run` is ever called.
"""

from app.agent.summary_repository import SummaryRepository
from app.agent.tools import Tool, ToolContext
from app.interfaces.memory_store import MemoryStore


class SaveMemoryTool(Tool):
    name = "save_memory"
    description = "Persist a fact from this interaction to the caller's long-term memory store."
    schema = {"content": str}

    def __init__(self, memory_store: MemoryStore):
        self._store = memory_store

    async def run(self, ctx: ToolContext, arguments: dict) -> dict:
        memory_id = await self._store.add(
            user_id=ctx.user_id,
            content=arguments["content"],
            contact_id=ctx.contact_id,
            source_type="agent_tool",
        )
        return {"memory_id": memory_id}


class CreateSummaryTool(Tool):
    name = "create_summary"
    description = (
        "Persist a baseline summary of the conversation so far (concatenated "
        "transcript today - not yet abstractive; see docs/SELF_LEARNING.md "
        "for the planned upgrade path)."
    )
    schema = {"conversation_id": str, "summary_text": str}

    def __init__(self, summary_repository: SummaryRepository):
        self._repo = summary_repository

    async def run(self, ctx: ToolContext, arguments: dict) -> dict:
        summary_id = await self._repo.upsert(
            conversation_id=arguments["conversation_id"],
            summary_text=arguments["summary_text"],
        )
        return {"summary_id": summary_id}
