"""Patch-based source editing with workspace checks and syntax diagnostics."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from aegis_os.sandbox.path_guard import PathTraversalError, validate_path
from aegis_os.tools.base import BaseAegisTool, ToolResult
from aegis_os.tools.syntax import syntax_diagnostics

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def apply_unified_diff(original: str, patch: str) -> str:
    """Apply a single-file unified diff to text, rejecting any context mismatch."""
    source = original.splitlines(keepends=True)
    patch_lines = patch.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in original else "\n"
    output: list[str] = []
    source_index = 0
    index = 0
    hunk_count = 0

    while index < len(patch_lines):
        header = _HUNK_HEADER.match(patch_lines[index].rstrip("\r\n"))
        if header is None:
            index += 1
            continue
        hunk_count += 1
        target_index = max(0, int(header.group(1)) - 1)
        if target_index < source_index or target_index > len(source):
            raise ValueError("Patch hunk has an invalid source line number.")
        output.extend(source[source_index:target_index])
        source_index = target_index
        index += 1

        while (
            index < len(patch_lines)
            and _HUNK_HEADER.match(patch_lines[index].rstrip("\r\n")) is None
        ):
            line = patch_lines[index]
            index += 1
            if line.startswith("\\ No newline at end of file"):
                continue
            if not line:
                raise ValueError("Malformed empty line in unified diff.")
            marker = line[0]
            value = line[1:]
            if marker in (" ", "-"):
                if source_index >= len(source):
                    raise ValueError("Patch context extends beyond the end of the file.")
                current = source[source_index]
                if current.rstrip("\r\n") != value.rstrip("\r\n"):
                    raise ValueError(f"Patch context did not match source line {source_index + 1}.")
                if marker == " ":
                    output.append(current)
                source_index += 1
            elif marker == "+":
                if value.endswith("\n") and newline == "\r\n" and not value.endswith("\r\n"):
                    value = value[:-1] + "\r\n"
                output.append(value)
            else:
                raise ValueError(f"Unsupported unified diff line marker: {marker!r}.")

    if hunk_count == 0:
        raise ValueError("No unified diff hunks were provided.")
    output.extend(source[source_index:])
    return "".join(output)


class ApplyPatchArgs(BaseModel):
    file_path: str = Field(description="Relative workspace file to patch.")
    patch: str = Field(description="Unified diff containing one or more hunks for file_path.")


class ApplyPatchTool(BaseAegisTool):
    """Apply a context-checked unified diff to one workspace file."""

    name = "apply_patch"
    description = (
        "Apply a unified diff to one workspace file; every context line must match exactly."
    )
    args_schema = ApplyPatchArgs

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def _execute(self, args: ApplyPatchArgs) -> ToolResult:
        try:
            safe_path = validate_path(args.file_path, self.workspace_root)
        except PathTraversalError as exc:
            return ToolResult.fail(str(exc))
        if not safe_path.is_file():
            return ToolResult.fail(f"File not found: '{args.file_path}'")
        try:
            original = safe_path.read_text(encoding="utf-8")
            updated = apply_unified_diff(original, args.patch)
        except (OSError, UnicodeError, ValueError) as exc:
            return ToolResult.fail(f"Unable to apply patch: {exc}")

        temp_path = safe_path.with_suffix(safe_path.suffix + ".aegis_tmp")
        try:
            temp_path.write_text(updated, encoding="utf-8", newline="")
            temp_path.replace(safe_path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            return ToolResult.fail(f"Failed to save patched file: {exc}")

        diagnostics = syntax_diagnostics(safe_path, updated)
        if diagnostics:
            return ToolResult(
                success=False,
                output=f"Patch applied to '{args.file_path}'. Syntax diagnostics:\n"
                + "\n".join(diagnostics),
                error="Syntax validation failed after applying the patch: "
                + "; ".join(diagnostics),
                metadata={"file_path": str(safe_path), "syntax_diagnostics": diagnostics},
            )
        return ToolResult.ok(
            output=f"Patch applied to '{args.file_path}' and syntax validation passed.",
            metadata={"file_path": str(safe_path), "syntax_diagnostics": []},
        )
