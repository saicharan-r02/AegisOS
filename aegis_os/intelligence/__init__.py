"""Codebase intelligence package for AegisOS."""

from __future__ import annotations

from aegis_os.intelligence.bm25 import BM25Index, tokenize_code
from aegis_os.intelligence.explorer import AegisExplorer, ExploreCodebaseTool
from aegis_os.intelligence.profiler import ProjectProfile, ProjectProfiler
from aegis_os.intelligence.repo_map import FileSymbols, RepoMap, Symbol, compute_pagerank
from aegis_os.intelligence.search import (
    CodeSearchEngine,
    FindDefinitionTool,
    GetRepoMapTool,
    HybridFindReferencesTool,
    SearchCodeTool,
)

__all__ = [
    "AegisExplorer",
    "BM25Index",
    "CodeSearchEngine",
    "ExploreCodebaseTool",
    "FileSymbols",
    "FindDefinitionTool",
    "GetRepoMapTool",
    "HybridFindReferencesTool",
    "ProjectProfile",
    "ProjectProfiler",
    "RepoMap",
    "SearchCodeTool",
    "Symbol",
    "compute_pagerank",
    "tokenize_code",
]
