import ast
import os
from pathlib import Path

from pydantic import BaseModel, Field

from aegis_os.sandbox.path_guard import PathTraversalError, validate_path
from aegis_os.tools.base import BaseAegisTool, ToolResult


class ASTGrepArgs(BaseModel):
    symbol_name: str = Field(description="Name of the function, class, or method to search for.")
    search_path: str = Field(
        description="Directory or file to search. Searches recursively for directories."
    )
    symbol_type: str | None = Field(
        default=None,
        description="Type of symbol: 'function','class',or None for both.",
    )


class _ASTMatch:
    def __init__(self, file: str, line: int, kind: str, name: str, qualified: str):
        self.file = file
        self.line = line
        self.kind = kind
        self.name = name
        self.qualified = qualified  # e.g., ClassName.method_name

    def __str__(self) -> str:
        return f"{self.file}:{self.line} [{self.kind}] {self.qualified}"


def _grep_file(filepath: str, symbol_name: str, symbol_type: str | None) -> list[_ASTMatch]:
    matches: list[_ASTMatch] = []
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, OSError):
        return matches

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if symbol_type and symbol_type != "function":
                continue
            if node.name.lower() == symbol_name.lower() or symbol_name.lower() in node.name.lower():
                parent = _find_parent_class(tree, node)
                qualified = f"{parent}.{node.name}" if parent else node.name
                matches.append(_ASTMatch(filepath, node.lineno, "function", node.name, qualified))
        elif isinstance(node, ast.ClassDef):
            if symbol_type and symbol_type != "class":
                continue
            if node.name.lower() == symbol_name.lower() or symbol_name.lower() in node.name.lower():
                matches.append(_ASTMatch(filepath, node.lineno, "class", node.name, node.name))
    return matches


def _find_parent_class(tree: ast.AST, target_node: ast.AST) -> str | None:
    """Walk the tree and find the immediate parent ClassDef of the target node."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in ast.walk(node):
                if child is target_node:
                    return node.name
    return None


class ASTGrepTool(BaseAegisTool):
    """
    Search Python source files for function/class definitions by name using AST parsing.
    Returns file path, line number, and qualified symbol name. Does not read file
    contents into context — safe for large codebases.
    """

    name = "ast_grep"
    parallel_safe = True
    _ignored_dirs = frozenset(
        {
            ".git",
            ".venv",
            "venv",
            "env",
            "node_modules",
            "__pycache__",
            ".aegis",
            "site-packages",
            "dist",
            "build",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
        }
    )
    description = (
        "Search Python source files for function or class definitions by name using "
        "AST parsing. Returns file path and line number without reading file contents. "
        "Use symbol_type='function' or 'class' to narrow results."
    )
    args_schema = ASTGrepArgs

    def __init__(self, workspace_root: Path | str | None = None) -> None:
        self.workspace_root = Path(workspace_root) if workspace_root is not None else None

    def _execute(self, args: ASTGrepArgs) -> ToolResult:
        search_path = args.search_path
        all_matches: list[_ASTMatch] = []

        if self.workspace_root is not None:
            try:
                search_path = str(validate_path(args.search_path, self.workspace_root))
            except PathTraversalError as exc:
                return ToolResult.fail(error=str(exc))

        if os.path.isfile(search_path):
            python_files = [search_path]
        elif os.path.isdir(search_path):
            python_files = []
            for root, dirs, files in os.walk(search_path):
                dirs[:] = [d for d in dirs if d not in self._ignored_dirs]
                for fname in files:
                    if fname.endswith(".py"):
                        python_files.append(os.path.join(root, fname))
        else:
            return ToolResult.fail(error=f"Path does not exist: {args.search_path}")

        for fpath in python_files:
            all_matches.extend(_grep_file(fpath, args.symbol_name, args.symbol_type))

        if not all_matches:
            return ToolResult(
                success=True,
                output=f"No symbols matching '{args.symbol_name}' found in {args.search_path}.",
                error=None,
                metadata={"match_count": 0},
            )

        lines = [self._display(m) for m in all_matches]
        return ToolResult(
            success=True,
            output="\n".join(lines),
            error=None,
            metadata={"match_count": len(all_matches)},
        )

    def _display(self, match: "_ASTMatch") -> str:
        """Show paths relative to the project so the model never sees server-internal folders."""
        text = str(match)
        if self.workspace_root is not None:
            root = str(self.workspace_root.resolve())
            text = text.replace(root + os.sep, "", 1)
        return text
