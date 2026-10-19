import fnmatch
import os
from pathlib import Path
import re
from typing import List, Optional
from pydantic import BaseModel, Field
from aegis_os.sandbox.path_guard import PathTraversalError, validate_path
from aegis_os.tools.base import BaseAegisTool, ToolResult

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


# ── Surgical Replacement Tool ──────────────────────────────────────────────

class ReplaceInFileArgs(BaseModel):
    path: str = Field(description="Relative path to the file within the workspace.")
    target_content: str = Field(description="Exact string or block of lines to find and replace.")
    replacement_content: str = Field(description="Exact new content to insert in place of target_content.")
    replace_all: bool = Field(
        default=False,
        description="If True, replace all occurrences. If False, requires target_content to be unique.",
    )


class ReplaceInFileTool(BaseAegisTool):
    """
    Surgically replace targeted code snippets without rewriting entire files.
    Ensures exact matches and atomic writing.
    """
    name = "replace_in_file"
    description = (
        "Surgically replace exact matching content in a file without rewriting the whole file. "
        "target_content must match exactly, including indentation. "
        "By default, errors if target_content is not unique (to prevent unintended replacements)."
    )
    args_schema = ReplaceInFileArgs

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def _execute(self, args: ReplaceInFileArgs) -> ToolResult:  # type: ignore[override]
        try:
            safe_path = validate_path(args.path, self.workspace_root)
        except PathTraversalError as exc:
            return ToolResult.fail(error=str(exc))

        if not safe_path.exists():
            return ToolResult.fail(error=f"File not found: '{args.path}'")
        if not safe_path.is_file():
            return ToolResult.fail(error=f"Path is not a file: '{args.path}'")

        try:
            content = safe_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult.fail(error=f"Failed to read file: {exc}")

        if args.target_content not in content:
            return ToolResult.fail(
                error=(
                    f"Target content was not found in '{args.path}'. "
                    f"Ensure exact match including whitespace and indentation."
                )
            )

        count = content.count(args.target_content)
        if not args.replace_all and count > 1:
            return ToolResult.fail(
                error=(
                    f"Target content appears {count} times in '{args.path}'. "
                    f"Provide more surrounding context lines to uniquely identify the location, "
                    f"or set replace_all=True."
                )
            )

        if args.replace_all:
            new_content = content.replace(args.target_content, args.replacement_content)
        else:
            new_content = content.replace(args.target_content, args.replacement_content, 1)

        temp_path = safe_path.with_suffix(safe_path.suffix + ".aegis_tmp")
        try:
            temp_path.write_text(new_content, encoding="utf-8")
            temp_path.replace(safe_path)
        except OSError as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return ToolResult.fail(error=f"Failed to save modified file: {exc}")

        return ToolResult.ok(
            output=f"Successfully replaced {count if args.replace_all else 1} occurrence(s) in '{args.path}'.",
            metadata={
                "file_path": str(safe_path),
                "replacements_made": count if args.replace_all else 1,
            },
        )


# ── Codebase Reconnaissance & Search Tools ────────────────────────────────

_IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", ".aegis", "dist", "build"}


class GrepSearchArgs(BaseModel):
    query: str = Field(description="Search string or regular expression.")
    path: str = Field(default=".", description="Relative directory or file to search within.")
    is_regex: bool = Field(default=False, description="Whether to treat query as a regex.")
    case_sensitive: bool = Field(default=False, description="Case-sensitive search.")
    max_results: int = Field(default=50, ge=1, le=200, description="Maximum number of matches.")


class GrepSearchTool(BaseAegisTool):
    """
    Search across workspace files for exact text or regex pattern matches.
    """
    name = "grep_search"
    description = (
        "Search across workspace files for text or regex patterns. "
        "Returns matching file paths, line numbers, and content snippets."
    )
    args_schema = GrepSearchArgs

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def _execute(self, args: GrepSearchArgs) -> ToolResult:  # type: ignore[override]
        try:
            safe_path = validate_path(args.path, self.workspace_root)
        except PathTraversalError as exc:
            return ToolResult.fail(error=str(exc))

        if not safe_path.exists():
            return ToolResult.fail(error=f"Path not found: '{args.path}'")

        flags = 0 if args.case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(args.query if args.is_regex else re.escape(args.query), flags)
        except re.error as exc:
            return ToolResult.fail(error=f"Invalid regex pattern: {exc}")

        matches: List[str] = []
        files_to_search: List[Path] = []

        if safe_path.is_file():
            files_to_search = [safe_path]
        else:
            for root, dirs, files in os.walk(safe_path):
                dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS and not d.startswith(".")]
                for fname in files:
                    if fname.startswith("."):
                        continue
                    files_to_search.append(Path(root) / fname)

        for fpath in files_to_search:
            if len(matches) >= args.max_results:
                break
            try:
                rel_path = fpath.relative_to(self.workspace_root)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line_idx, line in enumerate(f, start=1):
                        if pattern.search(line):
                            matches.append(f"{rel_path}:{line_idx}: {line.strip()[:150]}")
                            if len(matches) >= args.max_results:
                                break
            except (OSError, UnicodeDecodeError):
                continue

        if not matches:
            return ToolResult.ok(
                output=f"No matches found for '{args.query}' in '{args.path}'.",
                metadata={"matches_count": 0},
            )

        header = f"Found {len(matches)} match(es) for '{args.query}':\n"
        return ToolResult.ok(
            output=header + "\n".join(matches),
            metadata={"matches_count": len(matches)},
        )


class FindFilesArgs(BaseModel):
    pattern: str = Field(description="Glob pattern to search for e.g. '*.py', '**/*.json', 'test_*.py'.")
    path: str = Field(default=".", description="Relative directory to search within.")
    max_results: int = Field(default=50, ge=1, le=200, description="Maximum files to return.")


class FindFilesTool(BaseAegisTool):
    """
    Find files by glob pattern within the workspace.
    """
    name = "find_files"
    description = (
        "Find files matching a glob pattern (e.g. '*.py', '**/*.json', 'tests/**/test_*.py') "
        "within the workspace."
    )
    args_schema = FindFilesArgs

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def _execute(self, args: FindFilesArgs) -> ToolResult:  # type: ignore[override]
        try:
            safe_path = validate_path(args.path, self.workspace_root)
        except PathTraversalError as exc:
            return ToolResult.fail(error=str(exc))

        if not safe_path.exists() or not safe_path.is_dir():
            return ToolResult.fail(error=f"Directory not found: '{args.path}'")

        found: List[str] = []
        for root, dirs, files in os.walk(safe_path):
            dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS and not d.startswith(".")]
            for fname in files:
                rel_file = str((Path(root) / fname).relative_to(self.workspace_root)).replace("\\", "/")
                if fnmatch.fnmatch(fname, args.pattern) or fnmatch.fnmatch(rel_file, args.pattern):
                    found.append(rel_file)
                    if len(found) >= args.max_results:
                        break
            if len(found) >= args.max_results:
                break

        if not found:
            return ToolResult.ok(
                output=f"No files matching pattern '{args.pattern}' found in '{args.path}'.",
                metadata={"found_count": 0},
            )

        header = f"Found {len(found)} file(s) matching '{args.pattern}':\n"
        return ToolResult.ok(
            output=header + "\n".join(found),
            metadata={"found_count": len(found)},
        )

