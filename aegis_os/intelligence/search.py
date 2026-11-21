"""Hybrid code search combining BM25 keyword retrieval and symbol index."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from aegis_os.intelligence.bm25 import BM25Index
from aegis_os.intelligence.repo_map import RepoMap
from aegis_os.tools.base import BaseAegisTool, ToolResult


class CodeSearchEngine:
    """Unified hybrid codebase search engine combining BM25 and symbol indexing."""

    _INDEXABLE_EXTENSIONS = {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".md",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
    }
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

    def __init__(self, workspace_root: Path, cache_dir: Path | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.cache_dir = cache_dir or (self.workspace_root / ".aegis" / "index")
        self.repo_map = RepoMap(self.workspace_root, cache_dir=self.cache_dir)
        self.bm25 = BM25Index()
        self.chunks_meta: dict[str, dict[str, Any]] = {}
        self.files_mtime: dict[str, float] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        bm25_cache = self.cache_dir / "bm25.json"
        meta_cache = self.cache_dir / "bm25_meta.json"
        loaded_bm25 = BM25Index.load_cache(bm25_cache)
        if loaded_bm25 is not None and meta_cache.is_file():
            try:
                meta = json.loads(meta_cache.read_text(encoding="utf-8"))
                self.bm25 = loaded_bm25
                self.chunks_meta = meta.get("chunks", {})
                self.files_mtime = meta.get("files_mtime", {})
            except Exception:
                self.chunks_meta.clear()
                self.files_mtime.clear()

    def _save_cache(self) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.bm25.save_cache(self.cache_dir / "bm25.json")
            meta_cache = self.cache_dir / "bm25_meta.json"
            meta_cache.write_text(
                json.dumps(
                    {
                        "chunks": self.chunks_meta,
                        "files_mtime": self.files_mtime,
                    }
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def build_or_update(self, force: bool = False) -> None:
        """Scan workspace, chunk files, and update BM25 and symbol indices."""
        self.repo_map.scan_files()

        documents: dict[str, str] = {}
        new_chunks_meta: dict[str, dict[str, Any]] = {}
        new_files_mtime: dict[str, float] = {}
        changed = False

        for root, dirs, files in os.walk(str(self.workspace_root)):
            root_path = Path(root)
            dirs[:] = [d for d in dirs if d not in self._IGNORED_DIRS and not d.startswith(".")]
            for fname in files:
                fpath = root_path / fname
                if fpath.suffix.lower() not in self._INDEXABLE_EXTENSIONS:
                    continue

                try:
                    rel_path = fpath.relative_to(self.workspace_root).as_posix()
                    mtime = fpath.stat().st_mtime
                    new_files_mtime[rel_path] = mtime

                    if (
                        not force
                        and rel_path in self.files_mtime
                        and self.files_mtime[rel_path] == mtime
                    ):
                        # Re-use existing chunks for this file
                        for chunk_id, meta in self.chunks_meta.items():
                            if meta.get("file") == rel_path:
                                documents[chunk_id] = meta.get("text", "")
                                new_chunks_meta[chunk_id] = meta
                        continue

                    changed = True
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                    lines = content.splitlines()
                    chunk_size = 30
                    overlap = 5
                    step = chunk_size - overlap

                    if not lines:
                        continue

                    for start_idx in range(0, len(lines), step):
                        end_idx = min(start_idx + chunk_size, len(lines))
                        chunk_text = "\n".join(lines[start_idx:end_idx])
                        start_line = start_idx + 1
                        end_line = end_idx
                        chunk_id = f"{rel_path}:{start_line}"
                        documents[chunk_id] = chunk_text
                        new_chunks_meta[chunk_id] = {
                            "file": rel_path,
                            "start_line": start_line,
                            "end_line": end_line,
                            "text": chunk_text,
                        }
                        if end_idx >= len(lines):
                            break
                except Exception:
                    continue

        if changed or force or not self.bm25.doc_count:
            self.bm25.add_documents(documents)
            self.chunks_meta = new_chunks_meta
            self.files_mtime = new_files_mtime
            self._save_cache()

    def search_code(
        self,
        query: str,
        path_filter: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Search codebase for code snippets matching query using BM25 index."""
        self.build_or_update()
        raw_results = self.bm25.query(query, top_k=top_k * 3)

        results: list[dict[str, Any]] = []
        clean_filter = path_filter.replace("\\", "/").lower() if path_filter else None

        for chunk_id, score in raw_results:
            meta = self.chunks_meta.get(chunk_id)
            if not meta:
                continue
            file_path = meta["file"]
            if clean_filter and clean_filter not in file_path.lower():
                continue

            results.append(
                {
                    "file": file_path,
                    "line": meta["start_line"],
                    "end_line": meta["end_line"],
                    "score": round(score, 3),
                    "snippet": meta["text"],
                }
            )
            if len(results) >= top_k:
                break

        return results
    def search(self, *args, **kwargs):
        return self.search_code(*args, **kwargs)

    def find_definition(self, symbol: str) -> list[dict[str, Any]]:
        """Locate definition of a symbol (class, function, method, struct) across the repo."""
        self.repo_map.scan_files()
        results: list[dict[str, Any]] = []

        query_name = symbol.strip()
        query_lower = query_name.lower()

        for rel_path, file_entry in self.repo_map.files_cache.items():
            for sym in file_entry.symbols:
                # Exact match or suffix match (e.g. MyClass.my_method)
                if (
                    sym.name == query_name
                    or sym.name.endswith(f".{query_name}")
                    or sym.name.lower() == query_lower
                ):
                    results.append(
                        {
                            "file": rel_path,
                            "line": sym.line,
                            "name": sym.name,
                            "kind": sym.kind,
                            "signature": sym.signature,
                            "docstring": sym.docstring,
                        }
                    )

        # Sort exact matches first
        results.sort(key=lambda r: (r["name"] != query_name, r["file"], r["line"]))
        return results

    def find_references(
        self,
        symbol: str,
        path_filter: str | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Find line references where symbol is used in source files."""
        pattern = re.compile(rf"\b{re.escape(symbol.strip())}\b")
        results: list[dict[str, Any]] = []
        clean_filter = path_filter.replace("\\", "/").lower() if path_filter else None

        for root, dirs, files in os.walk(str(self.workspace_root)):
            root_path = Path(root)
            dirs[:] = [d for d in dirs if d not in self._IGNORED_DIRS and not d.startswith(".")]
            for fname in files:
                fpath = root_path / fname
                if fpath.suffix.lower() not in self._INDEXABLE_EXTENSIONS:
                    continue
                try:
                    rel_path = fpath.relative_to(self.workspace_root).as_posix()
                    if clean_filter and clean_filter not in rel_path.lower():
                        continue

                    lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
                    for idx, line in enumerate(lines, start=1):
                        if pattern.search(line):
                            results.append(
                                {
                                    "file": rel_path,
                                    "line": idx,
                                    "text": line.strip(),
                                }
                            )
                            if len(results) >= max_results:
                                return results
                except Exception:
                    continue

        return results

    def get_repo_map(self, focus_path: str | None = None, max_tokens: int = 1500) -> str:
        """Render PageRank-ranked repository map within token budget."""
        rendered = self.repo_map.render_map(max_tokens=max_tokens)
        if not focus_path:
            return rendered

        clean_focus = focus_path.replace("\\", "/").lower()
        # Filter lines to prioritize or highlight focus path
        lines = rendered.splitlines()
        focused_lines: list[str] = [lines[0], lines[1]] if len(lines) >= 2 else []
        for line in lines[2:]:
            if clean_focus in line.lower() or line.startswith("  -"):
                focused_lines.append(line)
        return "\n".join(focused_lines) if len(focused_lines) > 2 else rendered


# ─────────────────────────────────────────────────────────────────────────────
# Aegis Tool Definitions
# ─────────────────────────────────────────────────────────────────────────────


class SearchCodeArgs(BaseModel):
    query: str = Field(
        min_length=1, description="Keywords, identifiers, or phrase to search across codebase."
    )
    path_filter: str | None = Field(
        default=None, description="Optional path substring to restrict search."
    )
    top_k: int = Field(
        default=10, ge=1, le=50, description="Maximum number of code snippets to return."
    )


class SearchCodeTool(BaseAegisTool):
    """BM25 code search across identifiers, comments, and strings."""

    name = "search_code"
    description = (
        "Search codebase using BM25 semantic/keyword index over code identifiers, "
        "comments, and docstrings. Returns matching file:line snippets."
    )
    args_schema = SearchCodeArgs
    parallel_safe = True

    def __init__(self, workspace_root: Path, engine: CodeSearchEngine | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.engine = engine or CodeSearchEngine(self.workspace_root)

    def _execute(self, args: SearchCodeArgs) -> ToolResult:
        try:
            results = self.engine.search_code(
                query=args.query,
                path_filter=args.path_filter,
                top_k=args.top_k,
            )
            if not results:
                return ToolResult.ok(
                    output=f"No matches found for query '{args.query}'.",
                    metadata={"match_count": 0},
                )

            formatted: list[str] = []
            for r in results:
                formatted.append(
                    f"📄 {r['file']}:{r['line']} (score: {r['score']}):\n{r['snippet']}\n"
                )

            return ToolResult.ok(
                output="\n---\n".join(formatted),
                metadata={"match_count": len(results), "top_score": results[0]["score"]},
            )
        except Exception as exc:
            return ToolResult.fail(f"Search failed: {exc}")


class FindDefinitionArgs(BaseModel):
    symbol: str = Field(
        min_length=1, description="Symbol name (function, class, struct, type) to locate."
    )


class FindDefinitionTool(BaseAegisTool):
    """Locate definitions of functions, classes, and types across the codebase."""

    name = "find_definition"
    description = "Find class, function, struct, or type definitions across the codebase with exact file and line numbers."
    args_schema = FindDefinitionArgs
    parallel_safe = True

    def __init__(self, workspace_root: Path, engine: CodeSearchEngine | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.engine = engine or CodeSearchEngine(self.workspace_root)

    def _execute(self, args: FindDefinitionArgs) -> ToolResult:
        try:
            definitions = self.engine.find_definition(args.symbol)
            if not definitions:
                return ToolResult.ok(
                    output=f"No definition found for symbol '{args.symbol}'.",
                    metadata={"count": 0},
                )

            lines: list[str] = [f"Found {len(definitions)} definition(s) for '{args.symbol}':"]
            for d in definitions:
                entry = f"- {d['file']}:{d['line']} -> {d['signature']}"
                if d.get("docstring"):
                    entry += f"  # {d['docstring'].splitlines()[0]}"
                lines.append(entry)

            return ToolResult.ok(
                output="\n".join(lines),
                metadata={"count": len(definitions), "definitions": definitions},
            )
        except Exception as exc:
            return ToolResult.fail(f"Find definition failed: {exc}")


class FindReferencesArgs(BaseModel):
    symbol: str = Field(min_length=1, description="Symbol or identifier to find references for.")
    path_filter: str | None = Field(default=None, description="Optional path substring filter.")
    max_results: int = Field(default=50, ge=1, le=200, description="Maximum number of references.")


class HybridFindReferencesTool(BaseAegisTool):
    """Find references to a symbol across the codebase."""

    name = "find_references"
    description = (
        "Find all references to a symbol across the codebase with exact file and line numbers."
    )
    args_schema = FindReferencesArgs
    parallel_safe = True

    def __init__(self, workspace_root: Path, engine: CodeSearchEngine | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.engine = engine or CodeSearchEngine(self.workspace_root)

    def _execute(self, args: FindReferencesArgs) -> ToolResult:
        try:
            refs = self.engine.find_references(
                symbol=args.symbol,
                path_filter=args.path_filter,
                max_results=args.max_results,
            )
            if not refs:
                return ToolResult.ok(
                    output=f"No references found for '{args.symbol}'.",
                    metadata={"count": 0},
                )

            lines = [f"Found {len(refs)} reference(s) for '{args.symbol}':"]
            for r in refs:
                lines.append(f"{r['file']}:{r['line']}: {r['text']}")

            return ToolResult.ok(
                output="\n".join(lines),
                metadata={"count": len(refs)},
            )
        except Exception as exc:
            return ToolResult.fail(f"Find references failed: {exc}")


class GetRepoMapArgs(BaseModel):
    focus_path: str | None = Field(
        default=None, description="Optional path to focus or prioritize."
    )
    max_tokens: int = Field(
        default=1500, ge=100, le=8000, description="Max token budget for the repo map."
    )


class GetRepoMapTool(BaseAegisTool):
    """Get a high-level PageRank-ranked symbol map of the codebase, fitted to a token budget."""

    name = "get_repo_map"
    description = (
        "Get a high-level PageRank-ranked symbol map of the codebase, fitted to a token budget."
    )
    args_schema = GetRepoMapArgs
    parallel_safe = True

    def __init__(self, workspace_root: Path, engine: CodeSearchEngine | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.engine = engine or CodeSearchEngine(self.workspace_root)

    def _execute(self, args: GetRepoMapArgs) -> ToolResult:
        try:
            repo_map_str = self.engine.get_repo_map(
                focus_path=args.focus_path,
                max_tokens=args.max_tokens,
            )
            return ToolResult.ok(output=repo_map_str)
        except Exception as exc:
            return ToolResult.fail(f"Get repo map failed: {exc}")
