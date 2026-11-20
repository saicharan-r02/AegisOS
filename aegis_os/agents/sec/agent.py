import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from aegis_os.agents.base_agent import BaseAgent, _first_json
from aegis_os.agents.sec.prompts import SYSTEM_PROMPT
from aegis_os.kernel.llm import get_llm
from aegis_os.kernel.state import AgentRole
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.security.scanners import SecurityScannerRunner
from aegis_os.tools.ast_tools import ASTGrepTool
from aegis_os.tools.filesystem_tools import ListDirTool, ReadFileTool
from aegis_os.tools.registry import ToolRegistry


class SecurityFinding(BaseModel):
    id: str = Field(description="Finding ID e.g. SEC-001")
    severity: str = Field(description="CRITICAL | HIGH | MEDIUM | LOW | INFO")
    category: str = Field(description="OWASP category")
    file: str
    line: int | None = None
    description: str
    remediation: str


class SecuritySummary(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class SecurityReport(BaseModel):
    audit_target: str
    findings: list[SecurityFinding] = Field(default_factory=list)
    summary: SecuritySummary = Field(default_factory=SecuritySummary)
    report_error: str | None = None
    scanner_runs: list[dict[str, Any]] = Field(default_factory=list)


class AegisSec(BaseAgent):
    """
    Security Auditor Agent.
    Responsibilities:
    - Reads source files and applies OWASP vulnerability checklist.
    - Uses AST grep to find dangerous patterns (eval, exec, shell=True).
    - Produces a structured SecurityReport with severity and remediation.
    RBAC: Strictly read-only. No write, no shell execution, no commits.
    """

    def __init__(
        self,
        workspace_root: Path,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        max_steps: int = 20,
        state_machine: StateMachine | None = None,
        allow_network_scanners: bool | None = None,
    ):
        registry = ToolRegistry()
        registry.register(ReadFileTool(workspace_root))
        registry.register(ListDirTool(workspace_root))
        registry.register(ASTGrepTool(workspace_root))

        llm = get_llm(
            provider=llm_provider,
            model_name=llm_model,
            role=AgentRole.SEC,
            workspace_root=workspace_root,
        )
        super().__init__(
            name="AegisSec",
            role=AgentRole.SEC,
            llm=llm,
            tools=registry,
            system_prompt=SYSTEM_PROMPT,
            max_steps=max_steps,
            state_machine=state_machine,
        )
        self.workspace_root = workspace_root
        self.scanner_runner = SecurityScannerRunner(
            workspace_root, allow_network_scanners=allow_network_scanners
        )

    def audit(self, target: str = ".") -> SecurityReport:
        """
        Audit the specified path and return a structured SecurityReport.
        Args:
            target: Directory or file to audit (relative to workspace).
        Returns:
            A validated SecurityReport Pydantic model.
        """
        prompt = (
            f"Please perform a full security audit on '{target}' following OWASP "
            f"guidelines and produce a structured SecurityReport JSON as described "
            f"in your system prompt."
        )
        scanner_report = self.scanner_runner.run(target)
        scanner_evidence = scanner_report.model_dump_json(indent=2)
        prompt += (
            "\n\n## Deterministic Scanner Evidence\n"
            "Treat these results as authoritative evidence. You may explain and prioritize them, "
            "but do not remove or downgrade a scanner finding.\n"
            f"{scanner_evidence}"
        )
        raw_output = self.run(prompt, max_iterations=5)
        report = self._parse_report(raw_output, target)
        report.scanner_runs = [run.model_dump() for run in scanner_report.runs]

        existing_ids = {finding.id for finding in report.findings}
        for finding in scanner_report.findings:
            finding_id = f"SCAN-{finding.scanner}-{finding.rule_id}"
            if finding_id in existing_ids:
                continue
            report.findings.append(SecurityFinding(
                id=finding_id,
                severity=finding.severity,
                category=finding.scanner,
                file=finding.file,
                line=finding.line,
                description=finding.description,
                remediation=finding.remediation,
            ))

        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for sec_finding in report.findings:
            severity = sec_finding.severity.casefold()
            if severity in counts:
                counts[severity] += 1
        report.summary = SecuritySummary(**counts)

        completed = {run.scanner for run in scanner_report.runs if run.status == "completed"}
        missing = {"bandit", "detect-secrets"} - completed
        if missing and not report.report_error:
            report.report_error = (
                "Required security scanners did not complete: " + ", ".join(sorted(missing))
            )
        return report

    def _parse_report(self, raw: str, target: str) -> SecurityReport:
        block_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        if block_match:
            try:
                data: dict[str, Any] = json.loads(block_match.group(1))
                return SecurityReport.model_validate(data)
            except (json.JSONDecodeError, Exception):
                pass

        try:
            data = _first_json(raw)
            if "findings" in data or "summary" in data:
                return SecurityReport.model_validate({"audit_target": target, **data})
        except (json.JSONDecodeError, ValueError):
            pass

        return SecurityReport(
            audit_target=target,
            findings=[],
            summary=SecuritySummary(),
            report_error="Security agent did not return a verifiable audit report.",
        )
