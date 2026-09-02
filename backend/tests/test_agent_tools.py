"""ToolRegistry: authorization, validation, timeout, audit, and failure
isolation - see app/agent/tools.py."""

import asyncio

import pytest

from app.agent.tools import (
    Tool,
    ToolContext,
    ToolRegistry,
)


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
