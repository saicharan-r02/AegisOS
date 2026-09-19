from typing import Any, Iterator, Optional
from aegis_os.tools.base import BaseAegisTool

class ToolRegistry:
    """
    Central catalog of tools available to agents.
    Provides schema export for LLM function calling and prompt formatting.
    """
    def __init__(self, tools: Optional[Any] = None) -> None:
        self._tools: dict[str, BaseAegisTool] = {}
        if isinstance(tools, ToolRegistry):
            self._tools = dict(tools._tools)
        elif isinstance(tools, dict):
            for tool in tools.values():
                self.register(tool)
        elif tools:
            for tool in tools:
                self.register(tool)

    def register(self,tool: BaseAegisTool,overwrite: bool=False) -> None:
        """
        Register a tool in the catalog.
        Raises:
            ValueError: If tool with same name is already registered and overwrite is False.
        """
        if tool.name in self._tools and not overwrite:
            raise ValueError(
                f"Tool with name '{tool.name}' is already registered in ToolRegistry."
            )
        self._tools[tool.name]=tool

    def get(self, name: str) -> Optional[BaseAegisTool]:
        """Look up a tool by its unique name."""
        return self._tools.get(name)

    def require(self,name: str) -> BaseAegisTool:
        """Look up a tool by name or raise KeyError if missing."""
        if name not in self._tools:
            raise KeyError(
                f"Tool '{name}' is not registered. Available tools: {list(self._tools.keys())}"
            )
        return self._tools[name]

    def list_tools(self) -> list[BaseAegisTool]:
        """Return all registered tool instances."""
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        """Return list of registered tool names."""
        return list(self._tools.keys())

    def all_tools(self) -> dict[str, BaseAegisTool]:
        """Return dictionary of all registered tools by name."""
        return dict(self._tools)

    def to_json_schemas(self) -> list[dict[str, Any]]:
        """
        Export tool schemas in OpenAI/Groq function calling format.
        """
        schemas=[]
        for tool in self._tools.values():
            schema={
                "type":"function",
                "function":{
                    "name":tool.name,
                    "description": tool.description,
                    "parameters": tool.args_schema.model_json_schema(),
                },
            }
            schemas.append(schema)
        return schemas

    def format_tool_descriptions(self) -> str:
        """
        Format tool signatures and descriptions into a markdown block
        for direct prompt injection in ReAct reasoning loops.
        """
        if not self._tools:
            return "No tools available."

        lines = ["### Available Tools:"]
        for tool in self._tools.values():
            param_schema=tool.args_schema.model_json_schema()
            properties=param_schema.get("properties",{})
            required=param_schema.get("required",[])

            param_lines=[]
            for prop_name,prop_data in properties.items():
                req_marker=" (required)" if prop_name in required else " (optional)"
                prop_type=prop_data.get("type", "any")
                prop_desc=prop_data.get("description", "")
                param_lines.append(f"    - `{prop_name}` ({prop_type}){req_marker}: {prop_desc}")

            params_text="\n".join(param_lines) if param_lines else "    - No parameters required."

            lines.append(
                f"\n- **`{tool.name}`**: {tool.description}\n"
                f"  Parameters:\n{params_text}"
            )
        return "\n".join(lines)

    def __iter__(self) -> Iterator[BaseAegisTool]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools