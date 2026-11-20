import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from aegis_os.agents.base_agent import BaseAgent, _first_json
from aegis_os.agents.qa.prompts import SYSTEM_PROMPT
from aegis_os.kernel.llm import get_llm
from aegis_os.kernel.state import AgentRole
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.ast_tools import ASTGrepTool
from aegis_os.tools.filesystem_tools import ListDirTool, ReadFileTool, WriteFileTool
from aegis_os.tools.registry import ToolRegistry
from aegis_os.tools.test_tools import PytestRunnerTool


class TestFinding(BaseModel):
    __test__ = False
    test_name: str
    error_message: str
    root_cause_hypothesis: str

class TestReport(BaseModel):
    """Structured test report produced by AegisQA."""
    __test__ = False
    passed: int = Field(default=0)
    failed: int = Field(default=0)
    errors: int = Field(default=0)
    no_tests_collected: bool = False
    acceptance_tests_generated: bool = False
    findings: list[TestFinding] = Field(default_factory=list)
    recommended_action: str | None = None
    raw_output: str | None = None


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

    def __init__(
        self,
        workspace_root: Path,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        max_steps: int = 20,
        state_machine: StateMachine | None = None,
        unsafe_local: bool = False,
    ):
        tests_root = workspace_root / "tests"
        registry = ToolRegistry()

        registry.register(ReadFileTool(workspace_root))
        registry.register(ListDirTool(workspace_root))
        registry.register(ASTGrepTool(workspace_root))
        registry.register(PytestRunnerTool(workspace_root, unsafe_local=unsafe_local))
        registry.register(WriteFileTool(tests_root))

        llm = get_llm(
            provider=llm_provider,
            model_name=llm_model,
            role=AgentRole.QA,
            workspace_root=workspace_root,
        )
        super().__init__(
            name="AegisQA",
            role=AgentRole.QA,
            llm=llm,
            tools=registry,
            system_prompt=SYSTEM_PROMPT,
            max_steps=max_steps,
            state_machine=state_machine,
        )
        self.workspace_root = workspace_root
        self.requires_tool_before_finish = True

    def run_and_report(self, target: str = "tests/") -> TestReport:
        """
        Execute tests and produce a structured TestReport.
        Args:
            target: pytest target (directory or specific test file/node).
        Returns:
            A validated TestReport Pydantic model.
        """
        prompt = (
            f"Run pytest ONCE for target '{target}'. Do not repeat an identical command. "
            "If pytest collects zero tests, report NO_TESTS_COLLECTED immediately; do not "
            "invent a passing result or rewrite production code. For ordinary failures, "
            "report the shortest useful traceback and likely cause. Return JSON with "
            "passed, failed, errors, no_tests_collected, findings, recommended_action."
        )
        raw_output = self.run(prompt, max_iterations=5)
        return self._parse_report(raw_output)

    def create_acceptance_tests(self, objective: str) -> str:
        """Create focused tests under tests/ once when the repository has no tests."""
        prompt = (
            "The repository's test command collected zero tests. Create a small, meaningful "
            "pytest acceptance test for the actual requested change. Objective: "
            f"{objective}\n"
            "Inspect only the most relevant changed file(s), then write test(s) under tests/ "
            "using the registered write_file tool. Test observable behavior and edge cases; "
            "do not use assert True, mocks that merely restate the implementation, or modify "
            "production files. Prefer Python standard-library checks unless the repository "
            "already has a test dependency for the target technology. Do not run pytest here. "
            "Create at most two focused test files, then report exactly what was created."
        )
        records = self.run_task(prompt, max_iterations=4)
        created = any(
            record.tool_name == "write_file" and record.status.value == "SUCCESS"
            for record in records
        )
        last_output = records[-1].tool_result.output if records and records[-1].tool_result else ""
        marker = "ACCEPTANCE_TESTS_CREATED" if created else "ACCEPTANCE_TESTS_NOT_CREATED"
        return f"{marker}\n{last_output}"[:1200]

    def _parse_report(self, raw: str) -> TestReport:
        """Extract TestReport data; never interpret a no-test run as success."""
        if re.search(r"NO_TESTS_COLLECTED|no tests (?:were )?collected|no tests ran", raw, re.IGNORECASE):
            return TestReport(
                no_tests_collected=True,
                recommended_action="Create focused acceptance tests once, then rerun pytest once.",
                raw_output=raw,
            )
        block_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        if block_match:
            try:
                data: dict[str, Any] = json.loads(block_match.group(1))
                return TestReport.model_validate(data)
            except (json.JSONDecodeError, Exception):
                pass

        try:
            data = _first_json(raw)
            if any(key in data for key in ("passed", "failed", "errors", "findings")):
                return TestReport.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            pass

        passed_match = re.search(r"(\d+) passed", raw)
        failed_match = re.search(r"(\d+) failed", raw)
        errors_match = re.search(r"(\d+) error", raw)
        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        errors = int(errors_match.group(1)) if errors_match else 0

        if not any((passed_match, failed_match, errors_match)) or passed + failed + errors == 0:
            return TestReport(
                errors=1,
                findings=[TestFinding(
                    test_name="qa_report",
                    error_message="QA did not return a verifiable test result.",
                    root_cause_hypothesis="The model output was empty, malformed, or omitted test counts.",
                )],
                recommended_action="Rerun the verification command and return a structured result.",
                raw_output=raw,
            )
        return TestReport(passed=passed, failed=failed, errors=errors, raw_output=raw)
