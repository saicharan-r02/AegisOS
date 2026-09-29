from pathlib import Path
from typing import Optional
from aegis_os.agents.base_agent import BaseAgent
from aegis_os.agents.ops.prompts import SYSTEM_PROMPT
from aegis_os.kernel.llm import get_llm
from aegis_os.kernel.state import AgentRole
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.filesystem_tools import ListDirTool,ReadFileTool
from aegis_os.tools.git_tools import GitDiffTool,GitStatusTool
from aegis_os.tools.registry import ToolRegistry
from aegis_os.tools.terminal_tools import ExecuteCommandTool

class AegisOps(BaseAgent):
    """
    Site Reliability Engineering Agent.
    Responsibilities:
    - Health checks: build, imports, smoke tests.
    - Dependency audits: pip conflicts, missing packages.
    - Git hygiene: untracked files, diverged branches.
    - Telemetry: builds logs, test run summaries.
    RBAC:
    - Has shell execution (ExecuteCommandTool) for pip, python, git.
    - Can read any config or log file.
    - CANNOT write source files or commit.
    """

    def __init__(self,workspace_root: Path,llm_provider: str = "openai",llm_model: Optional[str] = None,max_steps: int = 20,state_machine: Optional[StateMachine] = None):
        registry = ToolRegistry()
        registry.register(ReadFileTool(workspace_root))
        registry.register(ListDirTool(workspace_root))
        registry.register(GitStatusTool())
        registry.register(GitDiffTool())
        registry.register(ExecuteCommandTool(workspace_root))

        llm = get_llm(provider=llm_provider, model_name=llm_model or "gpt-4o")

        super().__init__(name="AegisOps",role=AgentRole.OPS,llm=llm,tools=registry,system_prompt=SYSTEM_PROMPT,max_steps=max_steps,state_machine=state_machine)
        self.workspace_root=workspace_root

    def health_check(self) -> str:
        """
        Run a full operational health check and return the report as text.
        Covers: build status, dependency audit, git hygiene.
        """
        prompt=(
            "Please run a full operational health check on this project. "
            "Check: (1) that the package imports successfully, "
            "(2) dependencies are correctly installed per requirements.txt, "
            "(3) git status is clean with no stray untracked changes. "
            "Produce a structured Operational Health Report."
        )
        return self.run(prompt)