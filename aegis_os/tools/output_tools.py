"""Mission-scoped tools for retrieving stored large tool outputs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from aegis_os.kernel.context import LargeOutputStore
from aegis_os.tools.base import BaseAegisTool, ToolResult


class ReadOutputArgs(BaseModel):
    artifact_id: str = Field(pattern=r"^[a-f0-9]{32}$", description="Opaque ID from a shortened tool output.")
    start_line: int = Field(default=1, ge=1, description="First line to read, 1-indexed.")
    end_line: int | None = Field(default=None, ge=1, description="Last line to read, inclusive; at most 500 lines.")


class ReadOutputTool(BaseAegisTool):
    """Read a bounded range from a mission output artifact by opaque ID."""

    name = "read_output"
    description = "Read a line range from a large tool output saved by AegisOS."
    args_schema = ReadOutputArgs
    parallel_safe = True

    def __init__(self, store: LargeOutputStore) -> None:
        self.store=store

    def _execute(self, args: ReadOutputArgs) -> ToolResult:
        if args.end_line is not None and args.end_line - args.start_line >= 500:
            return ToolResult.fail("Read at most 500 lines per output request.")
        try:
            output=self.store.read(args.artifact_id,args.start_line,args.end_line)
        except (OSError,ValueError) as exc:
            return ToolResult.fail(f"Unable to read output artifact: {exc}")
        return ToolResult.ok(output=output)
