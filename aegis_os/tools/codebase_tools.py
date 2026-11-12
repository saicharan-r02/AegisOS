"""Fast code outline and textual reference tools."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from pydantic import BaseModel, Field

from aegis_os.sandbox.path_guard import PathTraversalError, validate_path
from aegis_os.tools.base import BaseAegisTool, ToolResult


class FileOutlineArgs(BaseModel):
    path: str = Field(description="Relative source file path within the workspace.")


class FileOutlineTool(BaseAegisTool):
    """List top-level class and function symbols without reading whole files."""

    name = "file_outline"
    description = "Show classes, functions, and line numbers in a source file."
    args_schema = FileOutlineArgs
    parallel_safe = True

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def _execute(self, args: FileOutlineArgs) -> ToolResult:
        try:
            path = validate_path(args.path, self.workspace_root)
            source = path.read_text(encoding="utf-8", errors="replace")
        except (PathTraversalError, OSError) as exc:
            return ToolResult.fail(str(exc))
        if not path.is_file():
            return ToolResult.fail(f"Not a source file: '{args.path}'")

        symbols: list[str] = []
        if path.suffix.lower() == ".py":
            try:
                tree = ast.parse(source, filename=str(path))
            except SyntaxError as exc:
                return ToolResult.fail(
                    f"Cannot outline invalid Python syntax at line {exc.lineno}: {exc.msg}"
                )
            nodes = sorted(ast.walk(tree), key=lambda node: getattr(node, "lineno", 0))
            for node in nodes:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.append(f"{node.lineno}: {type(node).__name__} {node.name}")
        else:
            pattern = re.compile(
                r"^\s*(?:export\s+)?(?:declare\s+)?(?:async\s+)?"
                r"(function|class|interface|type|const|let|var)\s+([\w$]+)",
                re.MULTILINE,
            )
            symbols = [
                f"{source.count(chr(10), 0, match.start()) + 1}: {match.group(1)} {match.group(2)}"
                for match in pattern.finditer(source)
            ]
        return ToolResult.ok(
            output="\n".join(symbols) if symbols else "No symbols found.",
            metadata={"symbol_count": len(symbols)},
        )


class FindReferencesArgs(BaseModel):
    symbol: str = Field(min_length=1, description="Identifier or exact text to find.")
    path: str = Field(default=".", description="Workspace directory or file to search.")
    max_results: int = Field(default=100, ge=1, le=500)
    case_sensitive: bool = Field(default=True)


class FindReferencesTool(BaseAegisTool):
    """Search source files for word-boundary references to a symbol."""

    name = "find_references"
    description = "Find source lines that reference a symbol, with file and line numbers."
    args_schema = FindReferencesArgs
    parallel_safe = True
    _ignored = {".git", ".venv", "venv", "node_modules", "__pycache__", ".aegis", "dist", "build"}
    _extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java"}

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def _execute(self, args: FindReferencesArgs) -> ToolResult:
        try:
            root = validate_path(args.path, self.workspace_root)
        except PathTraversalError as exc:
            return ToolResult.fail(str(exc))
        if not root.exists():
            return ToolResult.fail(f"Path not found: '{args.path}'")
        pattern = re.compile(
            rf"\b{re.escape(args.symbol)}\b", 0 if args.case_sensitive else re.IGNORECASE
        )
        files = (
            [root]
            if root.is_file()
            else [
                p
                for p in root.rglob("*")
                if p.is_file()
                and p.suffix.lower() in self._extensions
                and not self._is_ignored(p, root)
            ]
        )
        matches: list[str] = []
        for path in files:
            if path.suffix.lower() not in self._extensions:
                continue
            try:
                for line_no, line in enumerate(
                    path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                ):
                    if pattern.search(line):
                        matches.append(
                            f"{path.relative_to(self.workspace_root)}:{line_no}: {line.strip()}"
                        )
                        if len(matches) >= args.max_results:
                            break
            except OSError:
                continue
            if len(matches) >= args.max_results:
                break
        return ToolResult.ok(
            output="\n".join(matches) if matches else f"No references found for '{args.symbol}'.",
            metadata={"match_count": len(matches), "truncated": len(matches) >= args.max_results},
        )

    def _is_ignored(self, path: Path, root: Path) -> bool:
        return any(part in self._ignored for part in path.relative_to(root).parts)
