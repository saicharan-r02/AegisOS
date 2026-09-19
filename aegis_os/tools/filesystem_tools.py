from pathlib import Path
from typing import Optional
from pydantic import BaseModel,Field
from aegis_os.sandbox.path_guard import PathTraversalError,validate_path
from aegis_os.tools.base import BaseAegisTool,ToolResult

class ReadFileArgs(BaseModel):
    path: str=Field(description="Relative path to the file within the workspace.")
    start_line: Optional[int]=Field(
        default=None,
        ge=1,
        description="First line to read (1-indexed, inclusive). Reads from start if None.",
    )
    end_line: Optional[int]=Field(
        default=None,
        ge=1,
        description="Last line to read (1-indexed, inclusive). Reads to end if None.",
    )

class ReadFileTool(BaseAegisTool):
    """
    Read file contents with 1-indexed line numbers prefixed to each line.
    Supports partial reads via start_line/end_line for large files.
    Enforces path containment within the workspace root.
    """
    name="read_file"
    description=(
        "Read the contents of a file within the workspace. "
        "Returns lines prefixed with 1-indexed line numbers. "
        "Use start_line and end_line to read a specific slice of the file."
    )
    args_schema=ReadFileArgs

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def _execute(self, args: ReadFileArgs) -> ToolResult:  # type: ignore[override]
        try:
            safe_path = validate_path(args.path, self.workspace_root)
        except PathTraversalError as exc:
            return ToolResult.fail(error=str(exc))

        if not safe_path.exists():
            return ToolResult.fail(
                error=f"File not found: '{args.path}'"
            )
        if not safe_path.is_file():
            return ToolResult.fail(
                error=f"Path is not a file: '{args.path}'"
            )

        try:
            content = safe_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult.fail(error=f"Failed to read file: {exc}")

        all_lines=content.splitlines()
        total_lines=len(all_lines)

        # Apply line range (converting 1-indexed to 0-indexed slicing)
        start_idx=(args.start_line-1)if args.start_line else 0
        end_idx=args.end_line if args.end_line else total_lines

        # Clamp to actual file bounds
        start_idx=max(0,min(start_idx,total_lines))
        end_idx=max(start_idx,min(end_idx,total_lines))

        selected_lines=all_lines[start_idx:end_idx]

        # Prefix each line with its 1-indexed line number
        numbered_lines=[
            f"{start_idx + i + 1:>4}: {line}"
            for i, line in enumerate(selected_lines)
        ]

        output="\n".join(numbered_lines)

        return ToolResult.ok(
            output=output,
            metadata={
                "file_path": str(safe_path),
                "total_lines": total_lines,
                "lines_returned": len(selected_lines),
                "start_line": start_idx+1,
                "end_line": start_idx+len(selected_lines),
            },
        )

class WriteFileArgs(BaseModel):
    path: str = Field(description="Relative path to the file within the workspace.")
    content: str = Field(description="The complete new content to write to the file.")
    create_dirs: bool = Field(
        default=True,
        description="If True, create parent directories if they do not exist.",
    )

class WriteFileTool(BaseAegisTool):
    """
    Write content to a file atomically.

    Uses a write-to-temp-then-rename strategy to prevent partial writes
    from leaving the file in a corrupt state if the process is interrupted.
    Enforces path containment within the workspace root.
    """
    name="write_file"
    description=(
        "Write or overwrite a file within the workspace with the provided content. "
        "The write is atomic — either the full content is written, or nothing changes. "
        "Parent directories are created automatically unless create_dirs=False."
    )
    args_schema=WriteFileArgs

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root=workspace_root

    def _execute(self, args: WriteFileArgs) -> ToolResult:  # type: ignore[override]
        try:
            safe_path = validate_path(args.path, self.workspace_root)
        except PathTraversalError as exc:
            return ToolResult.fail(error=str(exc))

        if args.create_dirs:
            try:
                safe_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return ToolResult.fail(
                    error=f"Failed to create parent directories: {exc}"
                )
        elif not safe_path.parent.exists():
            return ToolResult.fail(
                error=(
                    f"Parent directory '{safe_path.parent}' does not exist. "
                    f"Set create_dirs=True to create it automatically."
                )
            )

        # Atomic write: write to a temp file, then rename
        temp_path = safe_path.with_suffix(safe_path.suffix + ".aegis_tmp")
        try:
            temp_path.write_text(args.content, encoding="utf-8")
            temp_path.replace(safe_path)  # Atomic on same filesystem
        except OSError as exc:
            # Attempt cleanup of temp file
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return ToolResult.fail(error=f"Failed to write file: {exc}")

        line_count = args.content.count("\n") + 1
        return ToolResult.ok(
            output=f"Successfully wrote {line_count} lines to '{args.path}'.",
            metadata={
                "file_path": str(safe_path),
                "bytes_written": len(args.content.encode("utf-8")),
                "line_count": line_count,
            },
        )

class ListDirArgs(BaseModel):
    path: str=Field(
        default=".",
        description="Relative path to the directory within the workspace. Defaults to workspace root.",
    )
    show_hidden: bool=Field(
        default=False,
        description="If True, include hidden files and directories (names starting with '.').",
    )


class ListDirTool(BaseAegisTool):
    """
    List directory contents with file sizes and type indicators.
    Enforces path containment within the workspace root.
    """
    name="list_dir"
    description=(
        "List the contents of a directory within the workspace. "
        "Returns files with sizes and directories marked with trailing '/'. "
        "Use show_hidden=True to include hidden entries."
    )
    args_schema=ListDirArgs

    def __init__(self,workspace_root: Path) -> None:
        self.workspace_root=workspace_root

    def _execute(self,args: ListDirArgs) -> ToolResult:  # type: ignore[override]
        try:
            safe_path=validate_path(args.path,self.workspace_root)
        except PathTraversalError as exc:
            return ToolResult.fail(error=str(exc))

        if not safe_path.exists():
            return ToolResult.fail(error=f"Directory not found: '{args.path}'")
        if not safe_path.is_dir():
            return ToolResult.fail(error=f"Path is not a directory: '{args.path}'")

        try:
            entries=sorted(safe_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError as exc:
            return ToolResult.fail(error=f"Failed to list directory: {exc}")

        lines=[]
        file_count=0
        dir_count=0

        for entry in entries:
            if not args.show_hidden and entry.name.startswith("."):
                continue
            if entry.is_dir():
                lines.append(f"  📁  {entry.name}/")
                dir_count+=1
            elif entry.is_file():
                try:
                    size=entry.stat().st_size
                    size_str=_format_size(size)
                except OSError:
                    size_str="?"
                lines.append(f"  📄  {entry.name:<40}{size_str:>10}")
                file_count+=1

        header=f"Directory: {safe_path}\n{'─' * 60}"
        body="\n".join(lines) if lines else "  (empty)"
        footer=f"{'─' * 60}\n{dir_count} director{'y' if dir_count == 1 else 'ies'}, {file_count} file{'s' if file_count != 1 else ''}"

        return ToolResult.ok(
            output=f"{header}\n{body}\n{footer}",
            metadata={
                "directory": str(safe_path),
                "file_count": file_count,
                "dir_count": dir_count,
            },
        )

def _format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    for unit in ("B","KB","MB","GB"):
        if size_bytes<1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes//=1024
    return f"{size_bytes:.0f} TB"
