from pathlib import Path

from aegis_os.agents.base_agent import BaseAgent
from aegis_os.agents.dev.prompts import SYSTEM_PROMPT
from aegis_os.kernel.llm import get_llm
from aegis_os.kernel.state import AgentRole
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.ast_tools import ASTGrepTool
from aegis_os.tools.codebase_tools import FileOutlineTool, FindReferencesTool
from aegis_os.tools.editing_tools import ApplyPatchTool
from aegis_os.tools.filesystem_tools import (
    FindFilesTool,
    GrepSearchTool,
    ListDirTool,
    ReadFileTool,
    ReplaceInFileTool,
    WriteFileTool,
)
from aegis_os.tools.git_tools import GitCommitTool, GitDiffTool, GitStatusTool
from aegis_os.tools.registry import ToolRegistry
from aegis_os.tools.terminal_tools import ExecuteCommandTool


class AegisDev(BaseAgent):
    """
    Developer agent responsible for source-code implementation and refactoring.
    Responsibilities:
    - Reads, writes, and refactors source code.
    - Commits completed changes with structured commit messages.
    - Searches for symbols using AST-based grep and regex grep.
    RBAC: Has write access to code. Cannot run tests or deploy.
    Requires workspace_root to scope filesystem operations safely.
    """

    def __init__(
        self,
        workspace_root: Path,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        max_steps: int = 20,
        state_machine: StateMachine | None = None,
        unsafe_local: bool = False
    ):
        registry = ToolRegistry()
        registry.register(ReadFileTool(workspace_root))
        registry.register(WriteFileTool(workspace_root))
        registry.register(ApplyPatchTool(workspace_root))
        registry.register(ReplaceInFileTool(workspace_root))
        registry.register(ListDirTool(workspace_root))
        registry.register(GrepSearchTool(workspace_root))
        registry.register(FindFilesTool(workspace_root))
        registry.register(ASTGrepTool())
        registry.register(FileOutlineTool(workspace_root))
        registry.register(FindReferencesTool(workspace_root))
        registry.register(GitStatusTool(workspace_root))
        registry.register(GitDiffTool(workspace_root))
        registry.register(GitCommitTool(workspace_root))
        registry.register(ExecuteCommandTool(workspace_root, unsafe_local=unsafe_local))

        llm=get_llm(provider=llm_provider,model_name=llm_model,role=AgentRole.DEV,workspace_root=workspace_root)
        super().__init__(
            name="AegisDev",
            role=AgentRole.DEV,
            llm=llm,
            tools=registry,
            system_prompt=SYSTEM_PROMPT,
            max_steps=max_steps,
            state_machine=state_machine
        )
        self.workspace_root=workspace_root
