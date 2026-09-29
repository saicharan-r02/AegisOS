import json
import re
from pathlib import Path
from typing import Any,Dict,List,Optional
from pydantic import BaseModel,Field
from aegis_os.agents.base_agent import BaseAgent
from aegis_os.agents.sec.prompts import SYSTEM_PROMPT
from aegis_os.kernel.llm import get_llm
from aegis_os.kernel.state import AgentRole
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.ast_tools import ASTGrepTool
from aegis_os.tools.filesystem_tools import ListDirTool, ReadFileTool
from aegis_os.tools.registry import ToolRegistry

class SecurityFinding(BaseModel):
    id: str=Field(description="Finding ID e.g. SEC-001")
    severity: str=Field(description="CRITICAL | HIGH | MEDIUM | LOW | INFO")
    category: str=Field(description="OWASP category")
    file: str
    line: Optional[int]=None
    description: str
    remediation: str

class SecuritySummary(BaseModel):
    critical: int=0
    high: int=0
    medium: int=0
    low: int=0
    info: int=0

class SecurityReport(BaseModel):
    audit_target: str
    findings: List[SecurityFinding]=Field(default_factory=list)
    summary: SecuritySummary=Field(default_factory=SecuritySummary)

class AegisSec(BaseAgent):
    """
    Security Auditor Agent.
    Responsibilities:
    - Reads source files and applies OWASP vulnerability checklist.
    - Uses AST grep to find dangerous patterns (eval, exec, shell=True).
    - Produces a structured SecurityReport with severity and remediation.
    RBAC: Strictly read-only. No write, no shell execution, no commits.
    """
    def __init__(self,workspace_root: Path,llm_provider: str="openai",llm_model: Optional[str]=None,max_steps: int = 20,state_machine: Optional[StateMachine] = None,):
        registry=ToolRegistry()
        # READ-ONLY: no write, no git commit, no test runner
        registry.register(ReadFileTool(workspace_root))
        registry.register(ListDirTool(workspace_root))
        registry.register(ASTGrepTool())
        llm=get_llm(provider=llm_provider,model_name=llm_model or "gpt-4o")
        super().__init__(name="AegisSec",role=AgentRole.SEC,llm=llm,tools=registry,system_prompt=SYSTEM_PROMPT,max_steps=max_steps,state_machine=state_machine,)
        self.workspace_root=workspace_root
    def audit(self,target: str ="aegis_os/") -> SecurityReport:
        """
        Audit the specified path and return a structured SecurityReport.
        Args:
            target: Directory or file to audit (relative to workspace).
        Returns:
            A validated SecurityReport Pydantic model.
        """
        prompt=(
            f"Please perform a full security audit on '{target}' following OWASP "
            f"guidelines and produce a structured SecurityReport JSON as described "
            f"in your system prompt."
        )
        raw_output=self.run(prompt)
        return self._parse_report(raw_output,target)
    def _parse_report(self,raw: str,target: str) -> SecurityReport:
        block_match=re.search(r"```json\s*(.*?)\s*```",raw,re.DOTALL)
        if block_match:
            try:
                data: Dict[str, Any]=json.loads(block_match.group(1))
                return SecurityReport.model_validate(data)
            except (json.JSONDecodeError,Exception):
                pass
        return SecurityReport(audit_target=target,findings=[],summary=SecuritySummary())
