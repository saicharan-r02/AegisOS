from pathlib import Path
import pytest
from pydantic import BaseModel,Field
from aegis_os.tools.base import BaseAegisTool, ToolResult
from aegis_os.tools.filesystem_tools import ReadFileTool,WriteFileTool
from aegis_os.tools.registry import ToolRegistry

class _EchoArgs(BaseModel):
    message: str=Field(description="Message to echo back.")
    count: int=Field(default=1,description="Number of times to echo.")

class _EchoTool(BaseAegisTool):
    name="echo"
    description="Echoes a message back to the caller."
    args_schema=_EchoArgs

    def _execute(self, args: _EchoArgs) -> ToolResult:
        return ToolResult.ok(output=args.message*args.count)

class TestToolRegistry:
    """ToolRegistry registration and schema generation tests."""

    def test_register_and_retrieve_tool(self,tmp_workspace: Path) -> None:
        registry=ToolRegistry()
        tool=ReadFileTool(workspace_root=tmp_workspace)
        registry.register(tool)

        assert registry.get("read_file")==tool
        assert registry.require("read_file")==tool
        assert "read_file" in registry
        assert len(registry)==1

    def test_duplicate_registration_raises_error(self,tmp_workspace: Path) -> None:
        registry=ToolRegistry()
        tool1=ReadFileTool(workspace_root=tmp_workspace)
        tool2=ReadFileTool(workspace_root=tmp_workspace)

        registry.register(tool1)
        with pytest.raises(ValueError) as exc_info:
            registry.register(tool2)
        assert "already registered" in str(exc_info.value)

    def test_duplicate_registration_allowed_with_overwrite(self,tmp_workspace: Path) -> None:
        registry=ToolRegistry()
        tool1=ReadFileTool(workspace_root=tmp_workspace)
        tool2=ReadFileTool(workspace_root=tmp_workspace)

        registry.register(tool1)
        registry.register(tool2,overwrite=True)
        assert registry.get("read_file")==tool2

    def test_require_missing_tool_raises_key_error(self) -> None:
        registry=ToolRegistry()
        with pytest.raises(KeyError):
            registry.require("nonexistent_tool")

    def test_to_json_schemas(self) -> None:
        registry=ToolRegistry()
        registry.register(_EchoTool())

        schemas=registry.to_json_schemas()
        assert len(schemas)==1
        fn=schemas[0]["function"]
        assert fn["name"]=="echo"
        assert fn["description"]=="Echoes a message back to the caller."
        params=fn["parameters"]
        assert params["type"]=="object"
        assert "message" in params["properties"]
        assert "message" in params["required"]

    def test_format_tool_descriptions(self,tmp_workspace: Path) -> None:
        registry=ToolRegistry()
        registry.register(_EchoTool())
        registry.register(WriteFileTool(workspace_root=tmp_workspace))

        doc=registry.format_tool_descriptions()
        assert "### Available Tools:" in doc
        assert "**`echo`**" in doc
        assert "`message` (string) (required)" in doc
        assert "**`write_file`**" in doc
        assert "`path` (string) (required)" in doc