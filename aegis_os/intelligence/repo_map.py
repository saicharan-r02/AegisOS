"""Multi-language symbol extraction and graph-centrality ranked repository map."""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aegis_os.kernel.providers import estimate_tokens


@dataclass
class Symbol:
    name: str
    kind: str  # "class", "function", "method", "interface", "type"
    line: int
    signature: str = ""
    docstring: str = ""


@dataclass
class FileSymbols:
    file_path: str
    mtime: float
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


class SymbolExtractor:
    """Extract definitions and import references across multiple languages."""

    @staticmethod
    def extract_python(content: str) -> tuple[list[Symbol], list[str]]:
        symbols: list[Symbol] = []
        imports: list[str] = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return symbols, imports

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in node.args.args]
                sig = f"def {node.name}({', '.join(args)})"
                doc = ast.get_docstring(node) or ""
                symbols.append(
                    Symbol(
                        name=node.name,
                        kind="function",
                        line=node.lineno,
                        signature=sig,
                        docstring=doc[:100],
                    )
                )
            elif isinstance(node, ast.ClassDef):
                bases = [ast.unparse(b) for b in node.bases] if hasattr(ast, "unparse") else []
                sig = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"
                doc = ast.get_docstring(node) or ""
                symbols.append(
                    Symbol(
                        name=node.name,
                        kind="class",
                        line=node.lineno,
                        signature=sig,
                        docstring=doc[:100],
                    )
                )
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = [arg.arg for arg in sub.args.args]
                        method_sig = f"  def {sub.name}({', '.join(args)})"
                        symbols.append(
                            Symbol(
                                name=f"{node.name}.{sub.name}",
                                kind="method",
                                line=sub.lineno,
                                signature=method_sig,
                            )
                        )
        return symbols, imports

    @staticmethod
    def extract_js_ts(content: str) -> tuple[list[Symbol], list[str]]:
        symbols: list[Symbol] = []
        imports: list[str] = []

        # Find imports
        for match in re.finditer(
            r"(?:import\s+.*?from\s+['\"](.*?)['\"]|require\(['\"](.*?)['\"]\))", content
        ):
            module = match.group(1) or match.group(2)
            if module:
                imports.append(module)

        # Classes & interfaces
        for match in re.finditer(
            r"^\s*(?:export\s+)?(?:default\s+)?(class|interface)\s+([A-Za-z0-9_]+)",
            content,
            re.MULTILINE,
        ):
            kind = match.group(1)
            name = match.group(2)
            line = content[: match.start()].count("\n") + 1
            symbols.append(Symbol(name=name, kind=kind, line=line, signature=f"{kind} {name}"))

        # Functions
        for match in re.finditer(
            r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\((.*?)\)",
            content,
            re.MULTILINE,
        ):
            name = match.group(1)
            params = match.group(2)
            line = content[: match.start()].count("\n") + 1
            symbols.append(
                Symbol(
                    name=name,
                    kind="function",
                    line=line,
                    signature=f"function {name}({params[:40]})",
                )
            )

        # Arrow functions assigned to const/let/var
        for match in re.finditer(
            r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\((.*?)\)\s*=>",
            content,
            re.MULTILINE,
        ):
            name = match.group(1)
            params = match.group(2)
            line = content[: match.start()].count("\n") + 1
            symbols.append(
                Symbol(
                    name=name,
                    kind="function",
                    line=line,
                    signature=f"const {name} = ({params[:30]}) =>",
                )
            )

        return symbols, imports

    @staticmethod
    def extract_go(content: str) -> tuple[list[Symbol], list[str]]:
        symbols: list[Symbol] = []
        imports: list[str] = []

        # Imports
        for match in re.finditer(r"import\s+(?:\((.*?)\)|\"([^\"]+)\")", content, re.DOTALL):
            block = match.group(1)
            single = match.group(2)
            if single:
                imports.append(single)
            elif block:
                for line in block.splitlines():
                    imp = line.strip().strip('"')
                    if imp:
                        imports.append(imp)

        # Functions and methods
        for match in re.finditer(
            r"func\s+(?:\((?:[A-Za-z0-9_*\s]+)\)\s+)?([A-Za-z0-9_]+)\s*\((.*?)\)", content
        ):
            name = match.group(1)
            line = content[: match.start()].count("\n") + 1
            symbols.append(
                Symbol(name=name, kind="function", line=line, signature=f"func {name}(...)")
            )

        # Structs and interfaces
        for match in re.finditer(r"type\s+([A-Za-z0-9_]+)\s+(struct|interface)", content):
            name = match.group(1)
            kind = match.group(2)
            line = content[: match.start()].count("\n") + 1
            symbols.append(Symbol(name=name, kind=kind, line=line, signature=f"type {name} {kind}"))

        return symbols, imports

    @staticmethod
    def extract_rust(content: str) -> tuple[list[Symbol], list[str]]:
        symbols: list[Symbol] = []
        imports: list[str] = []

        # use declarations
        for match in re.finditer(r"use\s+([A-Za-z0-9_:]+)", content):
            imports.append(match.group(1))

        # fn, struct, enum, trait
        for match in re.finditer(
            r"(?:pub(?:\(crate\))?\s+)?(fn|struct|enum|trait)\s+([A-Za-z0-9_]+)", content
        ):
            kind = match.group(1)
            name = match.group(2)
            line = content[: match.start()].count("\n") + 1
            symbols.append(Symbol(name=name, kind=kind, line=line, signature=f"{kind} {name}"))

        return symbols, imports

    @staticmethod
    def extract_java(content: str) -> tuple[list[Symbol], list[str]]:
        symbols: list[Symbol] = []
        imports: list[str] = []

        for match in re.finditer(r"import\s+([A-Za-z0-9_.*]+);", content):
            imports.append(match.group(1))

        for match in re.finditer(
            r"(?:public|protected|private)?\s*(?:static\s+)?(class|interface|enum)\s+([A-Za-z0-9_]+)",
            content,
        ):
            kind = match.group(1)
            name = match.group(2)
            line = content[: match.start()].count("\n") + 1
            symbols.append(Symbol(name=name, kind=kind, line=line, signature=f"{kind} {name}"))

        return symbols, imports

    @classmethod
    def extract_for_file(cls, path: Path, content: str) -> tuple[list[Symbol], list[str]]:
        suffix = path.suffix.lower()
        if suffix == ".py":
            return cls.extract_python(content)
        elif suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs"}:
            return cls.extract_js_ts(content)
        elif suffix == ".go":
            return cls.extract_go(content)
        elif suffix == ".rs":
            return cls.extract_rust(content)
        elif suffix in {".java", ".kt"}:
            return cls.extract_java(content)
        return [], []


def compute_pagerank(
    graph: dict[str, list[str]], iterations: int = 20, damping: float = 0.85
) -> dict[str, float]:
    """Compute PageRank centrality scores over an in-memory adjacency list."""
    nodes = list(graph.keys())
    if not nodes:
        return {}
    num_nodes = len(nodes)
    scores = {node: 1.0 / num_nodes for node in nodes}

    for _ in range(iterations):
        new_scores = {node: (1.0 - damping) / num_nodes for node in nodes}
        for src, targets in graph.items():
            if targets:
                share = (scores[src] * damping) / len(targets)
                for tgt in targets:
                    if tgt in new_scores:
                        new_scores[tgt] += share
            else:
                share = (scores[src] * damping) / num_nodes
                for n in nodes:
                    new_scores[n] += share
        scores = new_scores

    return scores


class RepoMap:
    """Compact repository map with PageRank importance and incremental caching."""

    _IGNORED_DIRS = {
        ".git",
        ".aegis",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
    }
    _ALLOWED_EXTENSIONS = {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".java",
    }

    def __init__(self, workspace_root: Path, cache_dir: Path | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.cache_path = (
            cache_dir or (self.workspace_root / ".aegis" / "index")
        ) / "repo_map.json"
        self.files_cache: dict[str, FileSymbols] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        if not self.cache_path.is_file():
            return
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            for rel_path, entry in data.get("files", {}).items():
                syms = [Symbol(**s) for s in entry.get("symbols", [])]
                self.files_cache[rel_path] = FileSymbols(
                    file_path=rel_path,
                    mtime=entry.get("mtime", 0.0),
                    symbols=syms,
                    imports=entry.get("imports", []),
                )
        except Exception:
            self.files_cache.clear()

    def _save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            data: dict[str, Any] = {
                "files": {
                    rel_path: {
                        "mtime": item.mtime,
                        "imports": item.imports,
                        "symbols": [s.__dict__ for s in item.symbols],
                    }
                    for rel_path, item in self.files_cache.items()
                }
            }
            self.cache_path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    def scan_files(self) -> None:
        """Scan workspace files incrementally and update symbols cache."""
        for root, dirs, files in os.walk(str(self.workspace_root)):
            root_path = Path(root)
            dirs[:] = [d for d in dirs if d not in self._IGNORED_DIRS and not d.startswith(".")]
            for fname in files:
                fpath = root_path / fname
                if fpath.suffix.lower() not in self._ALLOWED_EXTENSIONS:
                    continue
                try:
                    rel_path = fpath.relative_to(self.workspace_root).as_posix()
                    mtime = fpath.stat().st_mtime
                    if rel_path in self.files_cache and self.files_cache[rel_path].mtime == mtime:
                        continue
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                    symbols, imports = SymbolExtractor.extract_for_file(fpath, content)
                    self.files_cache[rel_path] = FileSymbols(
                        file_path=rel_path,
                        mtime=mtime,
                        symbols=symbols,
                        imports=imports,
                    )
                except Exception:
                    continue

        self._save_cache()

    def build_import_graph(self) -> dict[str, list[str]]:
        """Construct an adjacency graph of file -> imported files."""
        graph: dict[str, list[str]] = {f: [] for f in self.files_cache}
        file_keys = set(self.files_cache.keys())

        for rel_path, item in self.files_cache.items():
            for imp in item.imports:
                clean_imp = imp.replace(".", "/").replace("\\", "/")
                # Match against registered files
                for other_file in file_keys:
                    if other_file != rel_path and clean_imp in other_file:
                        graph[rel_path].append(other_file)
        return graph

    def render_map(self, max_tokens: int = 1500) -> str:
        """Render a compact repository outline ranked by centrality up to max_tokens."""
        self.scan_files()
        if not self.files_cache:
            return "No source files indexed."

        graph = self.build_import_graph()
        rankings = compute_pagerank(graph)

        # Sort files by centrality score descending
        sorted_files = sorted(
            self.files_cache.keys(),
            key=lambda f: rankings.get(f, 0.0),
            reverse=True,
        )

        lines: list[str] = [
            "### Repository Map (Ranked by Centrality):",
            "Below is a high-level index of key symbols, classes, and functions across the codebase.",
        ]

        current_tokens = estimate_tokens("\n".join(lines))

        for rel_path in sorted_files:
            file_entry = self.files_cache[rel_path]
            if not file_entry.symbols:
                continue

            file_header = f"\n📄 {rel_path} (rank: {rankings.get(rel_path, 0.0):.3f}):"
            symbol_lines: list[str] = []
            for s in file_entry.symbols:
                sym_line = f"  - L{s.line}: {s.signature}"
                if s.docstring:
                    sym_line += f"  # {s.docstring.splitlines()[0]}"
                symbol_lines.append(sym_line)

            block = file_header + "\n" + "\n".join(symbol_lines)
            block_tokens = estimate_tokens(block)

            if current_tokens + block_tokens > max_tokens:
                lines.append(
                    f"\n... (truncated {len(sorted_files) - len(lines)} additional files for token budget)"
                )
                break

            lines.append(block)
            current_tokens += block_tokens

        return "\n".join(lines)
