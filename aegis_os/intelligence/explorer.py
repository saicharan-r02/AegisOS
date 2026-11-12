"""Read-only Explorer sub-agent with fresh context for targeted codebase investigation."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from aegis_os.agents.base_agent import BaseAgent
from aegis_os.intelligence.search import (
    CodeSearchEngine,
    FindDefinitionTool,
    GetRepoMapTool,
    HybridFindReferencesTool,
    SearchCodeTool,
)
from aegis_os.kernel.state import AgentRole, AgentState, MissionStatus
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.base import BaseAegisTool, ToolResult
from aegis_os.tools.filesystem_tools import (
    FindFilesTool,
    GrepSearchTool,
    ListDirTool,
    ReadFileTool,
)
from aegis_os.tools.git_tools import GitDiffTool, GitLogTool, GitStatusTool
from aegis_os.tools.registry import ToolRegistry

EXPLORER_SYSTEM_PROMPT = """You are AegisExplorer, a read-only autonomous code investigator and architectural analyst.
Your objective is to investigate codebases, diagnose bugs, locate symbols, and explain architectures with high accuracy and low token overhead.

CRITICAL RULES:
1. You are strictly READ-ONLY. You cannot write, edit, delete files, or execute state-modifying commands.
2. ALWAYS provide exact file:line citations (e.g. `path/to/file.py:42`) for every symbol, definition, or finding.
3. Keep investigation efficient:
   - First use `get_repo_map` or `find_definition` to locate relevant modules.
   - Use `search_code` (BM25) or `find_references` to track usage.
   - Use `read_file` with `start_line` and `end_line` to inspect specific sections.
4. When you have enough information, conclude with a final answer summarizing:
   - Direct answer or bug root cause
   - Key files and symbols with file:line citations
   - Recommended next steps or architectural insights
"""


class AegisExplorer(BaseAgent):
    """Read-only autonomous codebase investigator operating in an isolated context."""

    def __init__(
        self,
        workspace_root: Path,
        llm: Any,
        engine: CodeSearchEngine | None = None,
        max_steps: int = 12,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.engine = engine or CodeSearchEngine(self.workspace_root)

        registry = ToolRegistry()
        # Search & intelligence tools
        registry.register(SearchCodeTool(self.workspace_root, engine=self.engine))
        registry.register(FindDefinitionTool(self.workspace_root, engine=self.engine))
        registry.register(HybridFindReferencesTool(self.workspace_root, engine=self.engine))
        registry.register(GetRepoMapTool(self.workspace_root, engine=self.engine))

        # Filesystem read-only tools
        registry.register(ReadFileTool(self.workspace_root))
        registry.register(ListDirTool(self.workspace_root))
        registry.register(FindFilesTool(self.workspace_root))
        registry.register(GrepSearchTool(self.workspace_root))

        # Git read-only tools
        registry.register(GitStatusTool(self.workspace_root))
        registry.register(GitDiffTool(self.workspace_root))
        registry.register(GitLogTool(self.workspace_root))

        # Fresh isolated state machine for sub-agent
        sub_state = AgentState(
            session_id=f"explorer-{uuid.uuid4().hex[:8]}",
            mission_goal="Codebase Investigation",
            status=MissionStatus.RUNNING,
            active_role=AgentRole.EXPLORER,
            max_steps=max_steps,
        )
        sm = StateMachine(state=sub_state)

        super().__init__(
            name="AegisExplorer",
            role=AgentRole.EXPLORER,
            system_prompt=EXPLORER_SYSTEM_PROMPT,
            llm=llm,
            state_machine=sm,
            tools=registry,
            max_steps=max_steps,
        )

    def investigate(self, query: str, max_steps: int = 10) -> str:
        """Run read-only ReAct investigation loop and return cited findings."""
        task_prompt = (
            f"Investigate the following inquiry across the codebase:\n"
            f"'{query}'\n\n"
            f"Use your tools to find definitions, references, and inspect code slices. "
            f"Return a structured summary with exact file:line citations."
        )
        return self.run(task_prompt, max_iterations=max_steps)


# ─────────────────────────────────────────────────────────────────────────────
# Sub-agent Delegation Tool (for Main Agent use)
# ─────────────────────────────────────────────────────────────────────────────


class ExploreCodebaseArgs(BaseModel):
    query: str = Field(
        min_length=1, description="Question, bug inquiry, or architecture query to explore."
    )
    max_steps: int = Field(
        default=8, ge=1, le=20, description="Max exploration steps for the sub-agent."
    )


class ExploreCodebaseTool(BaseAegisTool):
    """Delegate exploration to a read-only Explorer sub-agent with fresh context."""

    name = "explore_codebase"
    description = (
        "Spawn a read-only Explorer sub-agent with fresh context to investigate a question, "
        "trace a bug, or analyze architecture. Returns a concise summary with exact file:line citations."
    )
    args_schema = ExploreCodebaseArgs
    parallel_safe = True

    def __init__(
        self, workspace_root: Path, llm: Any, engine: CodeSearchEngine | None = None
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.llm = llm
        self.engine = engine or CodeSearchEngine(self.workspace_root)

    def _execute(self, args: ExploreCodebaseArgs) -> ToolResult:
        try:
            explorer = AegisExplorer(
                workspace_root=self.workspace_root,
                llm=self.llm,
                engine=self.engine,
                max_steps=args.max_steps,
            )
            result = explorer.investigate(args.query, max_steps=args.max_steps)
            return ToolResult.ok(output=result)
        except Exception as exc:
            return ToolResult.fail(f"Explorer sub-agent failed: {exc}")
