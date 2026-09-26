import json
import re
from pathlib import Path
from typing import Any,Dict,List,Optional
from pydantic import BaseModel,Field
from aegis_os.agents.base_agent import BaseAgent
from aegis_os.agents.qa.prompts import SYSTEM_PROMPT
from aegis_os.kernel.llm import get_llm
from aegis_os.kernel.state import AgentRole
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.ast_tools import ASTGrepTool
from aegis_os.tools.filesystem_tools import ListDirTool, ReadFileTool, WriteFileTool
from aegis_os.tools.registry import ToolRegistry
from aegis_os.tools.test_tools import PytestRunnerTool

class TestFinding(BaseModel):
    """A single test failure or diagnostic finding."""
    __test__=False
    test_name:str
    error_message:str
    root_cause_hypothesis:str

class TestReport(BaseModel):
    """Structured test report produced by AegisQA."""
    __test__=False
    passed:int = Field(default=0)
    failed:int = Field(default=0)
    errors:int = Field(default=0)
    findings:List[TestFinding] = Field(default_factory=list)
    recommended_action:Optional[str] = None
    raw_output:Optional[str] = None

class AegisQA(BaseAgent):
    """
    Quality Assurance Agent.
    Responsibilities:
    - Runs pytest and interprets structured results.
    - Diagnoses failures with root-cause analysis.
    - Can write new test files to tests/ directory.
    RBAC: ReadFileTool is workspace-scoped. WriteFileTool is restricted
    to the tests/ subdirectory via the workspace_root mechanism — passing
    `workspace_root/tests` as the root confines writes to test files only.
    """
    def __init__(self,workspace_root: Path,llm_provider: str = "openai",llm_model: Optional[str] = None,max_steps: int = 20,state_machine: Optional[StateMachine] = None,):
        tests_root = workspace_root / "tests"
        registry = ToolRegistry()
        
        registry.register(ReadFileTool(workspace_root))
        registry.register(ListDirTool(workspace_root))
        registry.register(ASTGrepTool())
        
        registry.register(PytestRunnerTool())
        
        registry.register(WriteFileTool(tests_root))
        llm = get_llm(provider=llm_provider, model_name=llm_model or "gpt-4o")
        super().__init__(name="AegisQA",role=AgentRole.QA,llm=llm,tools=registry,system_prompt=SYSTEM_PROMPT,max_steps=max_steps,state_machine=state_machine,)
        self.workspace_root = workspace_root

    def run_and_report(self, target: str = "tests/") -> TestReport:
        """
        Execute tests and produce a structured TestReport.
        Args:
            target: pytest target (directory or specific test file/node).
        Returns:
            A validated TestReport Pydantic model.
        """
        prompt=(
            f"Please run the pytest test suite targeting '{target}', "
            f"diagnose any failures, and produce a structured test report."
        )
        raw_output=self.run(prompt)
        return self._parse_report(raw_output)

    def _parse_report(self,raw: str) -> TestReport:
        """Extract TestReport data from agent output, with safe fallback."""
        block_match=re.search(r"```json\s*(.*?)\s*```",raw,re.DOTALL)
        if block_match:
            try:
                data: Dict[str, Any]=json.loads(block_match.group(1))
                return TestReport.model_validate(data)
            except (json.JSONDecodeError, Exception):
                pass

        passed=int(re.search(r"(\d+) passed",raw).group(1)) if re.search(r"(\d+) passed",raw) else 0
        failed=int(re.search(r"(\d+) failed",raw).group(1)) if re.search(r"(\d+) failed",raw) else 0
        errors=int(re.search(r"(\d+) error",raw).group(1)) if re.search(r"(\d+) error",raw) else 0
        return TestReport(passed=passed,failed=failed,errors=errors,raw_output=raw)