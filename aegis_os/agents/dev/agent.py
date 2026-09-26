from pathlib import Path
from typing import Optional
from aegis_os.agents.base_agent import BaseAgent
from aegis_os.agents.dev.prompts import SYSTEM_PROMPT
from aegis_os.kernel.llm import get_llm
from aegis_os.kernel.state import AgentRole
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.ast_tools import ASTGrepTool
from aegis_os.tools.filesystem_tools import ListDirTool,ReadFileTool,WriteFileTool
from aegis_os.tools.git_tools import GitCommitTool,GitDiffTool,GitStatusTool
from aegis_os.tools.registry import ToolRegistry
from aegis_os.tools.terminal_tools import ExecuteCommandTool

class AegisDev(BaseAgent):
    """
    Developer agent responsible for source-code implementation and refactoring.
    Responsibilities:
    - Reads, writes, and refactors source code.
    - Commits completed changes with structured commit messages.
    - Searches for symbols using AST-based grep.
    RBAC: Has write access to code. Cannot run tests or deploy.
    Requires workspace_root to scope filesystem operations safely.
    """

    def __init__(self,workspace_root: Path,llm_provider: str = "openai",llm_model: Optional[str] = None,max_steps: int = 20,state_machine: Optional[StateMachine] = None):
        registry=ToolRegistry()
        registry.register(ReadFileTool(workspace_root))
        registry.register(WriteFileTool(workspace_root))
        registry.register(ListDirTool(workspace_root))
        registry.register(ASTGrepTool())
        registry.register(GitStatusTool())
        registry.register(GitDiffTool())
        registry.register(GitCommitTool())
        registry.register(ExecuteCommandTool(workspace_root))

        llm=get_llm(provider=llm_provider,model_name=llm_model or "gpt-4o")

        super().__init__(
            name="AegisDev",
            role=AgentRole.DEV,
            llm=llm,
            tools=registry,
            system_prompt=SYSTEM_PROMPT,
            max_steps=max_steps,
            state_machine=state_machine,
        )
        self.workspace_root=workspace_root
