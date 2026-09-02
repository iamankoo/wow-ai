"""Controlled tool registry for the WOW Agent orchestrator (see docs
"Tool system").

Tools are the *only* way the orchestrator produces a side effect (writing
memory, persisting a summary, ...). Every invocation is schema-validated,
authorization-checked, timeout-bounded, and audited via an injectable sink -
there is no code path from a WOW Brain prediction to arbitrary code
execution. A tool bug or a downstream failure never crashes the call: any
exception from `Tool.run` is caught and turned into a failed `ToolResult`.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone


class ToolAuthorizationError(RuntimeError):
    """Raised when a caller is not authorized to invoke a tool."""


class ToolValidationError(RuntimeError):
    """Raised when tool arguments fail schema validation."""


@dataclass
class ToolContext:
    """Who/what is invoking a tool - the identity a tool's authorization
    check and any persisted rows are scoped to."""

    user_id: str
    conversation_id: str | None = None
    contact_id: str | None = None


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    output: dict = field(default_factory=dict)
    error: str | None = None
    duration_ms: float | None = None


class Tool(ABC):
    """Base class for one controlled agent tool.

    Subclasses set `name`, `description`, and `schema` (argument name ->
    expected Python type) as class attributes, and implement `run`.
    Override `authorize` for anything stricter than "a user_id is present".
    """

    name: str = ""
    description: str = ""
    schema: dict[str, type] = {}
    timeout_seconds: float = 5.0

    def authorize(self, ctx: ToolContext, arguments: dict) -> bool:
        return bool(ctx.user_id)

    def validate(self, arguments: dict) -> None:
        for key, expected_type in self.schema.items():
            if key not in arguments:
                raise ToolValidationError(
                    f"{self.name}: missing required argument '{key}'"
                )
            if not isinstance(arguments[key], expected_type):
                raise ToolValidationError(
                    f"{self.name}: argument '{key}' must be {expected_type.__name__}"
                )

    @abstractmethod
    async def run(self, ctx: ToolContext, arguments: dict) -> dict:
        """Execute the tool and return a JSON-serializable result payload."""


AuditSink = Callable[[dict], Awaitable[None]]


class ToolRegistry:
    """Holds the authorized set of tools and mediates every invocation."""

    def __init__(self, tools: list[Tool] | None = None, *, audit_sink: AuditSink | None = None):
        self._tools: dict[str, Tool] = {t.name: t for t in (tools or [])}
        self._audit_sink = audit_sink

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    async def invoke(self, name: str, ctx: ToolContext, arguments: dict) -> ToolResult:
        started = time.monotonic()
        tool = self._tools.get(name)
        if tool is None:
            result = ToolResult(tool_name=name, success=False, error="unknown_tool")
            await self._audit(ctx, arguments, result)
            return result

        try:
            if not tool.authorize(ctx, arguments):
                raise ToolAuthorizationError(f"{name}: not authorized for this caller")
            tool.validate(arguments)
            output = await asyncio.wait_for(
                tool.run(ctx, arguments), timeout=tool.timeout_seconds
            )
            result = ToolResult(tool_name=name, success=True, output=output)
        except asyncio.TimeoutError:
            # asyncio.TimeoutError, not builtin TimeoutError: on Python <3.11
            # they are distinct classes (unified starting 3.11) and this repo
            # targets 3.10 - asyncio.wait_for always raises the asyncio one.
            result = ToolResult(tool_name=name, success=False, error="timeout")
        except (ToolAuthorizationError, ToolValidationError) as e:
            result = ToolResult(tool_name=name, success=False, error=str(e))
        except Exception as e:  # noqa: BLE001 - a tool bug must not crash the call
            result = ToolResult(tool_name=name, success=False, error=f"tool_error: {e}")

        result.duration_ms = (time.monotonic() - started) * 1000
        await self._audit(ctx, arguments, result)
        return result

    async def _audit(self, ctx: ToolContext, arguments: dict, result: ToolResult) -> None:
        if self._audit_sink is None:
            return
        await self._audit_sink(
            {
                "tool_name": result.tool_name,
                "user_id": ctx.user_id,
                "conversation_id": ctx.conversation_id,
                "arguments": arguments,
                "success": result.success,
                "error": result.error,
                "duration_ms": result.duration_ms,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
