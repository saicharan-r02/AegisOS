"""Baseline-first test verification ensuring regressions are never introduced."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from aegis_os.tools.test_tools import PytestRunnerTool


class TestBaseline(BaseModel):
    """Snapshot of test suite execution before any code modifications."""

    __test__ = False

    passed_tests: list[str] = Field(
        default_factory=list, description="IDs of tests that passed in baseline"
    )
    failed_tests: list[str] = Field(
        default_factory=list, description="IDs of tests that failed in baseline"
    )
    total_count: int = Field(default=0, description="Total number of tests executed")

    @property
    def passed_set(self) -> set[str]:
        return set(self.passed_tests)

    @property
    def failed_set(self) -> set[str]:
        return set(self.failed_tests)


class BaselineVerifier:
    """Captures initial test baseline and verifies that code changes make forward progress without regressions."""

    def __init__(self, workspace_root: Path, runner: PytestRunnerTool | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.runner = runner or PytestRunnerTool(self.workspace_root)

    def capture_baseline(self, test_path: str = "tests/") -> TestBaseline:
        """Run pytest prior to task changes and record baseline pass/fail sets."""
        result = self.runner.run({"test_path": test_path})
        meta = result.metadata or {}
        output = result.output

        passed: list[str] = []
        failed: list[str] = []

        # Parse test IDs from pytest verbose output (e.g. tests/test_calc.py::test_add PASSED)
        for line in output.splitlines():
            if " PASSED" in line:
                m = re.match(r"^(\S+::\S+)\s+PASSED", line.strip())
                if m:
                    passed.append(m.group(1))
            elif " FAILED" in line or " ERROR" in line:
                m = re.match(r"^(\S+::\S+)\s+(?:FAILED|ERROR)", line.strip())
                if m:
                    failed.append(m.group(1))

        passed_count = meta.get("passed", len(passed))
        failed_count = meta.get("failed", len(failed)) + meta.get("errors", 0)
        total = passed_count + failed_count

        return TestBaseline(
            passed_tests=passed,
            failed_tests=failed,
            total_count=total,
        )

    @staticmethod
    def verify_progress(
        baseline: TestBaseline,
        current_report: Any,
    ) -> tuple[bool, list[str]]:
        """Verify that all previously passing tests still pass and no new regressions occurred."""
        violations: list[str] = []

        curr_passed = getattr(current_report, "passed", 0)
        curr_failed = getattr(current_report, "failed", 0)
        curr_errors = getattr(current_report, "errors", 0)

        # 1. Total passing count should not drop below baseline
        baseline_passed_count = len(baseline.passed_tests) or (
            baseline.total_count - len(baseline.failed_tests)
        )
        if curr_passed < baseline_passed_count:
            violations.append(
                f"Regression detected: Passing test count dropped from {baseline_passed_count} to {curr_passed}."
            )

        # 2. Check if new failures were introduced
        if curr_failed > len(baseline.failed_tests) or curr_errors > 0:
            violations.append(
                f"New failures introduced: {curr_failed} failed, {curr_errors} errors (baseline had {len(baseline.failed_tests)} failures)."
            )

        # 3. Check specific test regressions if test names available
        curr_findings = getattr(current_report, "findings", [])
        curr_failed_names = {f.test_name for f in curr_findings if hasattr(f, "test_name")}
        for test_id in baseline.passed_set:
            test_short = test_id.split("::")[-1]
            if test_id in curr_failed_names or test_short in curr_failed_names:
                violations.append(f"Regressed test: '{test_id}' passed in baseline but now fails.")

        is_valid = len(violations) == 0
        return is_valid, violations
