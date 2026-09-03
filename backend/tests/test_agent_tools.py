"""ToolRegistry: authorization, validation, timeout, audit, and failure
isolation - see app/agent/tools.py. Also covers the builtin_tools.py Tool
subclasses that wrap a real storage abstraction (context profile, memory,
user settings)."""

import asyncio

import pytest

from app.agent.builtin_tools import (
    ClearContextTool,
    CollectMessageTool,
    DisableCallAssistantTool,
    EnableCallAssistantTool,
    MarkUrgentTool,
    SetContextTool,
)
from app.agent.context_profile_repository import InMemoryContextProfileRepository
from app.agent.tools import (
    Tool,
    ToolContext,
    ToolRegistry,
)
from app.agent.user_settings_repository import InMemoryUserSettingsRepository
from tests.agent_fakes import InMemoryMemoryStore


class EchoTool(Tool):
    name = "echo"
    description = "Echoes back its argument."
    schema = {"message": str}

    async def run(self, ctx: ToolContext, arguments: dict) -> dict:
        return {"echoed": arguments["message"]}


class DenyAllTool(Tool):
    name = "deny_all"
    description = "Always refuses authorization."

    def authorize(self, ctx: ToolContext, arguments: dict) -> bool:
        return False

    async def run(self, ctx: ToolContext, arguments: dict) -> dict:
        return {}


class BrokenTool(Tool):
    name = "broken"
    description = "Always raises."

    async def run(self, ctx: ToolContext, arguments: dict) -> dict:
        raise RuntimeError("boom")


class SlowTool(Tool):
    name = "slow"
    description = "Sleeps longer than its timeout."
    timeout_seconds = 0.01

    async def run(self, ctx: ToolContext, arguments: dict) -> dict:
        await asyncio.sleep(0.2)
        return {}


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(user_id="u1", conversation_id="c1")


async def test_successful_invocation(ctx):
    registry = ToolRegistry([EchoTool()])
    result = await registry.invoke("echo", ctx, {"message": "hi"})
    assert result.success is True
    assert result.output == {"echoed": "hi"}
    assert result.error is None


async def test_unknown_tool_fails_gracefully(ctx):
    registry = ToolRegistry([EchoTool()])
    result = await registry.invoke("does_not_exist", ctx, {})
    assert result.success is False
    assert result.error == "unknown_tool"


async def test_missing_argument_fails_validation(ctx):
    registry = ToolRegistry([EchoTool()])
    result = await registry.invoke("echo", ctx, {})
    assert result.success is False
    assert "message" in result.error


async def test_wrong_type_fails_validation(ctx):
    registry = ToolRegistry([EchoTool()])
    result = await registry.invoke("echo", ctx, {"message": 123})
    assert result.success is False
    assert "must be str" in result.error


async def test_denied_authorization(ctx):
    registry = ToolRegistry([DenyAllTool()])
    result = await registry.invoke("deny_all", ctx, {})
    assert result.success is False
    assert "not authorized" in result.error


async def test_tool_exception_does_not_propagate(ctx):
    registry = ToolRegistry([BrokenTool()])
    result = await registry.invoke("broken", ctx, {})
    assert result.success is False
    assert "boom" in result.error


async def test_tool_timeout(ctx):
    registry = ToolRegistry([SlowTool()])
    result = await registry.invoke("slow", ctx, {})
    assert result.success is False
    assert result.error == "timeout"


async def test_every_invocation_is_audited(ctx):
    events = []

    async def sink(event: dict) -> None:
        events.append(event)

    registry = ToolRegistry([EchoTool()], audit_sink=sink)
    await registry.invoke("echo", ctx, {"message": "hi"})
    await registry.invoke("does_not_exist", ctx, {})

    assert len(events) == 2
    assert events[0]["tool_name"] == "echo"
    assert events[0]["success"] is True
    assert events[1]["tool_name"] == "does_not_exist"
    assert events[1]["success"] is False


async def test_set_context_tool_activates_a_profile(ctx):
    repo = InMemoryContextProfileRepository()
    registry = ToolRegistry([SetContextTool(repo)])
    result = await registry.invoke("set_context", ctx, {"context_mode": "MEETING"})
    assert result.success is True
    assert result.output["context_mode"] == "MEETING"
    assert repo.active_name(user_id="u1") == "MEETING"


async def test_set_context_tool_switching_deactivates_the_previous_profile(ctx):
    repo = InMemoryContextProfileRepository()
    registry = ToolRegistry([SetContextTool(repo)])
    await registry.invoke("set_context", ctx, {"context_mode": "SLEEPING"})
    await registry.invoke("set_context", ctx, {"context_mode": "MEETING"})
    assert repo.active_name(user_id="u1") == "MEETING"


async def test_set_context_tool_rejects_out_of_taxonomy_context_mode(ctx):
    repo = InMemoryContextProfileRepository()
    registry = ToolRegistry([SetContextTool(repo)])
    result = await registry.invoke("set_context", ctx, {"context_mode": "ON_THE_MOON"})
    assert result.success is False
    assert "not a known context mode" in result.error
    assert repo.active_name(user_id="u1") is None


async def test_clear_context_tool_deactivates_the_active_profile(ctx):
    repo = InMemoryContextProfileRepository()
    registry = ToolRegistry([SetContextTool(repo), ClearContextTool(repo)])
    await registry.invoke("set_context", ctx, {"context_mode": "BUSY"})
    result = await registry.invoke("clear_context", ctx, {})
    assert result.success is True
    assert result.output == {"cleared": 1}
    assert repo.active_name(user_id="u1") is None


async def test_clear_context_tool_is_a_success_when_nothing_was_active(ctx):
    repo = InMemoryContextProfileRepository()
    registry = ToolRegistry([ClearContextTool(repo)])
    result = await registry.invoke("clear_context", ctx, {})
    assert result.success is True
    assert result.output == {"cleared": 0}


async def test_enable_call_assistant_tool_sets_the_flag(ctx):
    repo = InMemoryUserSettingsRepository()
    registry = ToolRegistry([EnableCallAssistantTool(repo)])
    result = await registry.invoke("enable_call_assistant", ctx, {})
    assert result.success is True
    assert result.output == {"call_assistant_enabled": True, "user_found": True}
    assert repo.is_enabled(user_id="u1") is True


async def test_disable_call_assistant_tool_clears_the_flag(ctx):
    repo = InMemoryUserSettingsRepository()
    registry = ToolRegistry([EnableCallAssistantTool(repo), DisableCallAssistantTool(repo)])
    await registry.invoke("enable_call_assistant", ctx, {})
    result = await registry.invoke("disable_call_assistant", ctx, {})
    assert result.success is True
    assert repo.is_enabled(user_id="u1") is False


async def test_collect_message_tool_persists_the_message_as_a_memory(ctx):
    memory_store = InMemoryMemoryStore()
    registry = ToolRegistry([CollectMessageTool(memory_store)])
    result = await registry.invoke("collect_message", ctx, {"content": "Call me back today"})
    assert result.success is True
    assert memory_store.records[0]["content"] == "Call me back today"
    assert memory_store.records[0]["source_type"] == "caller_message"


async def test_mark_urgent_tool_persists_a_flagged_short_term_memory(ctx):
    memory_store = InMemoryMemoryStore()
    registry = ToolRegistry([MarkUrgentTool(memory_store)])
    result = await registry.invoke("mark_urgent", ctx, {"content": "House is flooding"})
    assert result.success is True
    assert memory_store.records[0]["content"] == "URGENT: House is flooding"
    assert memory_store.records[0]["source_type"] == "mark_urgent"
