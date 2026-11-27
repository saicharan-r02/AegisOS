"""Model Context Protocol (MCP) client and plugin extension system."""

from __future__ import annotations

import importlib.metadata
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from aegis_os.sandbox.policy import CommandPolicy, CommandTier
from aegis_os.tools.base import BaseAegisTool, ToolResult
from aegis_os.tools.registry import ToolRegistry


class MCPToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = {}


class GenericMCPArgs(BaseModel):
    model_config = ConfigDict(extra="allow")


class MCPToolWrapper(BaseAegisTool):
    """Wraps an external MCP server tool into AegisOS BaseAegisTool with policy enforcement."""

    args_schema: type[BaseModel] = GenericMCPArgs

    def __init__(
        self,
        name: str,
        description: str,
        caller: Callable[[str, dict[str, Any]], ToolResult],
        policy: CommandPolicy | None = None,
        workspace_root: Path | str | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self._caller = caller
        self.policy = policy or CommandPolicy()
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd()

    def _execute(self, args: BaseModel) -> ToolResult:
        kwargs = args.model_dump()
        # Check command policy before dispatching to external MCP server
        command_candidate = f"{self.name} {json.dumps(kwargs)}"
        eval_result = self.policy.evaluate(command_candidate, self.workspace_root)
        if eval_result.tier == CommandTier.DENY:
            return ToolResult.fail(
                f"MCP tool '{self.name}' execution blocked by security policy: {eval_result.reason}"
            )
        return self._caller(self.name, kwargs)


class MCPClient:
    """Connects to external MCP tool servers and registers their tools with ToolRegistry."""

    def __init__(
        self,
        server_name: str,
        policy: CommandPolicy | None = None,
        workspace_root: Path | str | None = None,
    ) -> None:
        self.server_name = server_name
        self.policy = policy or CommandPolicy()
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd()
        self._tools: dict[str, MCPToolDefinition] = {}

    def register_remote_tool(
        self,
        tool_def: MCPToolDefinition,
        remote_call_fn: Callable[[str, dict[str, Any]], ToolResult],
        registry: ToolRegistry,
    ) -> None:
        """Register a remote MCP tool into AegisOS ToolRegistry."""
        self._tools[tool_def.name] = tool_def
        wrapper = MCPToolWrapper(
            name=tool_def.name,
            description=tool_def.description,
            caller=remote_call_fn,
            policy=self.policy,
            workspace_root=self.workspace_root,
        )
        registry.register(wrapper, overwrite=True)

    def list_tools(self) -> list[MCPToolDefinition]:
        return list(self._tools.values())


class PluginManager:
    """Discovers external plugins via Python entry points."""

    ENTRY_POINT_TOOLS = "aegis_os.tools"
    ENTRY_POINT_AGENTS = "aegis_os.agents"

    @classmethod
    def load_tool_plugins(cls, registry: ToolRegistry) -> int:
        """Load third-party tools registered under entry points."""
        loaded = 0
        try:
            tool_eps = importlib.metadata.entry_points(group=cls.ENTRY_POINT_TOOLS)
            for ep in tool_eps:
                tool_cls = ep.load()
                if isinstance(tool_cls, type) and issubclass(tool_cls, BaseAegisTool):
                    registry.register(tool_cls())
                    loaded += 1
        except Exception:
            pass
        return loaded
