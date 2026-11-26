"""Unit tests for Phase 3 Codebase Intelligence: Profiler, RepoMap, BM25, and Explorer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from aegis_os.intelligence.bm25 import BM25Index, tokenize_code
from aegis_os.intelligence.explorer import AegisExplorer, ExploreCodebaseTool
from aegis_os.intelligence.profiler import ProjectProfile, ProjectProfiler
from aegis_os.intelligence.repo_map import (
    RepoMap,
    SymbolExtractor,
    compute_pagerank,
)
from aegis_os.intelligence.search import (
    CodeSearchEngine,
    FindDefinitionTool,
    GetRepoMapTool,
    HybridFindReferencesTool,
    SearchCodeTool,
)
from aegis_os.kernel.providers import estimate_tokens
from aegis_os.kernel.state import AgentRole


class TestProjectProfiler:
    def test_python_project_detection(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[tool.poetry]
name = "my-project"
dependencies = { fastapi = "^0.100" }
""",
            encoding="utf-8",
        )
        rules_file = tmp_path / "AEGIS.md"
        rules_file.write_text("Rule: Never use eval().", encoding="utf-8")

        profiler = ProjectProfiler(tmp_path)
        profile = profiler.profile(use_cache=False)

        assert profile.primary_language == "python"
        assert profile.package_manager == "poetry"
        assert profile.test_command == "poetry run pytest"
        assert "fastapi" in profile.frameworks
        assert "AEGIS.md" in profile.rules
        assert "Never use eval()" in profile.rules["AEGIS.md"]

        # Verify caching
        cached_file = tmp_path / ".aegis" / "project.json"
        assert cached_file.is_file()
        cached_data = json.loads(cached_file.read_text(encoding="utf-8"))
        assert cached_data["package_manager"] == "poetry"

    def test_node_ts_project_detection(self, tmp_path: Path) -> None:
        pkg_json = tmp_path / "package.json"
        pkg_json.write_text(
            json.dumps({
                "dependencies": {"react": "^18.0", "next": "^14.0"},
                "devDependencies": {"typescript": "^5.0"},
                "scripts": {"test": "jest", "lint": "eslint ."},
            }),
            encoding="utf-8",
        )

        profiler = ProjectProfiler(tmp_path)
        profile = profiler.profile(use_cache=False)

        assert "typescript" in profile.languages
        assert "react" in profile.frameworks
        assert profile.test_command == "npm test"

    def test_context_prompt_formatting(self) -> None:
        profile = ProjectProfile(
            primary_language="python",
            languages=["python", "typescript"],
            package_manager="poetry",
            test_command="poetry run pytest",
            lint_command="ruff check .",
            rules={"AEGIS.md": "Keep functions small."},
        )
        prompt = profile.to_context_prompt()
        assert "Primary Language: python" in prompt
        assert "Keep functions small" in prompt


class TestSymbolExtractionAndRepoMap:
    def test_multi_language_extraction(self) -> None:
        py_code = """
import os
from math import sqrt

class Calculator:
    def add(self, a, b):
        \"\"\"Add two numbers.\"\"\"
        return a + b
"""
        py_syms, py_imps = SymbolExtractor.extract_python(py_code)
        assert len(py_syms) == 2
        assert py_syms[0].name == "Calculator"
        assert py_syms[1].name == "Calculator.add"
        assert "os" in py_imps
        assert "math" in py_imps

        ts_code = """
import { useState } from 'react';
export class UserService {
    async fetchUser(id: string) {}
}
export function helper() {}
"""
        ts_syms, ts_imps = SymbolExtractor.extract_js_ts(ts_code)
        assert any(s.name == "UserService" for s in ts_syms)
        assert any(s.name == "helper" for s in ts_syms)
        assert "react" in ts_imps

        go_code = """
package main
import "fmt"
type Server struct {}
func RunServer() {}
"""
        go_syms, go_imps = SymbolExtractor.extract_go(go_code)
        assert any(s.name == "Server" for s in go_syms)
        assert any(s.name == "RunServer" for s in go_syms)
        assert "fmt" in go_imps

    def test_pagerank_computation(self) -> None:
        graph = {
            "a.py": ["b.py", "c.py"],
            "b.py": ["c.py"],
            "c.py": ["a.py"],
        }
        scores = compute_pagerank(graph)
        assert len(scores) == 3
        # In this graph, c.py is imported by both a.py and b.py, so it should have highest rank
        assert scores["c.py"] > scores["b.py"]

    def test_repo_map_budget_clipping(self, tmp_path: Path) -> None:
        # Create multiple files with classes
        for i in range(15):
            f = tmp_path / f"module_{i}.py"
            f.write_text(f"class Class{i}:\n    def method_{i}(self):\n        pass\n", encoding="utf-8")

        repo_map = RepoMap(tmp_path)
        rendered = repo_map.render_map(max_tokens=200)

        assert "Repository Map" in rendered
        # Verify token budget enforcement
        token_count = estimate_tokens(rendered)
        assert token_count <= 250  # Close to the 200 token budget


class TestBM25AndSearchEngine:
    def test_subword_tokenization(self) -> None:
        tokens = tokenize_code("getUserProfileByID_v2")
        assert "getuserprofilebyid" in tokens
        assert "user" in tokens
        assert "profile" in tokens

    def test_bm25_index_and_cache(self, tmp_path: Path) -> None:
        docs = {
            "auth.py": "def authenticate_user(username, password): pass",
            "db.py": "def connect_database(host, port): pass",
            "models.py": "class UserProfile: pass",
        }
        index = BM25Index()
        index.add_documents(docs)

        results = index.query("authenticate user", top_k=2)
        assert len(results) > 0
        assert results[0][0] == "auth.py"

        # Cache check
        cache_path = tmp_path / "bm25.json"
        index.save_cache(cache_path)
        loaded = BM25Index.load_cache(cache_path)
        assert loaded is not None
        loaded_results = loaded.query("authenticate", top_k=1)
        assert loaded_results[0][0] == "auth.py"

    def test_search_tools(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        file_a = src / "payment.py"
        file_a.write_text(
            """
class PaymentProcessor:
    def process_transaction(self, amount: float) -> bool:
        return amount > 0
""",
            encoding="utf-8",
        )

        engine = CodeSearchEngine(tmp_path)

        # 1. SearchCodeTool
        search_tool = SearchCodeTool(tmp_path, engine=engine)
        res = search_tool.run({"query": "process transaction"})
        assert res.success
        assert "payment.py" in res.output
        assert "PaymentProcessor" in res.output

        # 2. FindDefinitionTool
        def_tool = FindDefinitionTool(tmp_path, engine=engine)
        def_res = def_tool.run({"symbol": "PaymentProcessor"})
        assert def_res.success
        assert "payment.py:2" in def_res.output

        # 3. HybridFindReferencesTool
        ref_tool = HybridFindReferencesTool(tmp_path, engine=engine)
        ref_res = ref_tool.run({"symbol": "amount"})
        assert ref_res.success
        assert "payment.py" in ref_res.output

        # 4. GetRepoMapTool
        map_tool = GetRepoMapTool(tmp_path, engine=engine)
        map_res = map_tool.run({"max_tokens": 500})
        assert map_res.success
        assert "PaymentProcessor" in map_res.output


class TestAegisExplorer:
    def test_explorer_initialization_and_read_only(self, tmp_path: Path) -> None:
        mock_llm = MagicMock()
        mock_llm.context_tokens = 8000
        mock_llm.max_tool_output_tokens = 1000

        explorer = AegisExplorer(tmp_path, llm=mock_llm)

        assert explorer.role == AgentRole.EXPLORER
        # Check tools are strictly read-only
        tool_names = set(explorer.tools.list_names())
        assert "read_file" in tool_names
        assert "search_code" in tool_names
        assert "find_definition" in tool_names
        assert "git_status" in tool_names

        # Crucial: NO write/destructive tools allowed in Explorer
        assert "write_file" not in tool_names
        assert "apply_patch" not in tool_names
        assert "replace_in_file" not in tool_names
        assert "git_commit" not in tool_names

    def test_explore_codebase_tool_delegation(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("def main(): return 42\n", encoding="utf-8")
        mock_llm = MagicMock()
        mock_llm.context_tokens = 8000
        mock_llm.max_tool_output_tokens = 1000
        mock_llm.max_completion_tokens = 0
        mock_llm.bind_tools.return_value = mock_llm

        # Mock LLM returning final answer
        mock_response = MagicMock()
        mock_response.content = "Investigation complete: main() is defined at app.py:1."
        mock_response.tool_calls = []
        mock_llm.invoke.return_value = mock_response

        tool = ExploreCodebaseTool(tmp_path, llm=mock_llm)
        res = tool.run({"query": "Where is main() defined?"})

        assert res.success
        assert "app.py:1" in res.output


class TestPhase3BenchmarkSynthetic500Files:
    """Benchmark Phase 3 against a 500+ file synthetic repository.

    Verifies RepoMap fits in token budget, BM25 finds symbols across files,
    and token consumption drops by >70% compared to brute-force file reading.
    """

    def test_synthetic_repo_benchmark(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "synthetic_repo"
        repo_dir.mkdir()

        total_files = 520
        total_tokens_all_files = 0

        # Generate 520 files across 10 packages
        for i in range(total_files):
            pkg_dir = repo_dir / f"pkg_{i % 10}"
            pkg_dir.mkdir(exist_ok=True)
            file_path = pkg_dir / f"module_{i}.py"

            content = f'''"""Module {i} description and utilities."""

import os
from pkg_{(i + 1) % 10}.module_{(i + 1) % total_files} import helper_{(i + 1) % total_files}

class Service{i}:
    """Service class {i} handling business operations."""
    def handle_request_{i}(self, payload: dict) -> bool:
        return True

def helper_{i}() -> str:
    return "result_{i}"
'''
            if i == 342:
                # Target secret symbol to search
                content += """
def target_secret_token_validator(token: str) -> bool:
    \"\"\"Validate unique authentication security token.\"\"\"
    return token == "AEGIS_V2_SECRET"
"""
            file_path.write_text(content, encoding="utf-8")
            total_tokens_all_files += estimate_tokens(content)

        # 1. Test RepoMap fits within 2000 token budget
        engine = CodeSearchEngine(repo_dir)
        repo_map_str = engine.get_repo_map(max_tokens=2000)
        repo_map_tokens = estimate_tokens(repo_map_str)

        assert repo_map_tokens <= 2200
        assert "Repository Map" in repo_map_str

        # 2. Test BM25 finds target symbol accurately across 500+ files
        search_tool = SearchCodeTool(repo_dir, engine=engine)
        search_result = search_tool.run({"query": "target_secret_token_validator", "top_k": 3})

        assert search_result.success
        assert "module_342.py" in search_result.output
        assert "AEGIS_V2_SECRET" in search_result.output

        # 3. Test find_definition locates target function
        def_tool = FindDefinitionTool(repo_dir, engine=engine)
        def_result = def_tool.run({"symbol": "target_secret_token_validator"})

        assert def_result.success
        assert "module_342.py" in def_result.output
        assert "def target_secret_token_validator(token)" in def_result.output

        # 4. Measure token efficiency: RepoMap + targeted retrieval vs brute force reading all files
        # Brute force = reading all 520 files
        targeted_tokens = repo_map_tokens + estimate_tokens(search_result.output) + estimate_tokens(def_result.output)
        token_savings_percent = (1.0 - (targeted_tokens / total_tokens_all_files)) * 100.0

        # Requirement: "token consumption drops by >70% compared to brute-force file reading"
        assert token_savings_percent > 70.0, (
            f"Expected >70% token savings, got {token_savings_percent:.1f}% "
            f"(targeted={targeted_tokens}, brute_force={total_tokens_all_files})"
        )
