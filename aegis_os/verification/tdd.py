"""Test-Driven Development (TDD) cycle coordinator: Red -> Green -> Refactor."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from aegis_os.tools.test_tools import PytestRunnerTool


class TDDPhase(str, Enum):
    RED = "RED"
    GREEN = "GREEN"
    REFACTOR = "REFACTOR"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TDDResult(BaseModel):
    """Structured report of a TDD cycle execution."""

    phase: TDDPhase = Field(description="Final reached phase of TDD cycle")
    success: bool = Field(description="True if full Red -> Green cycle succeeded")
    test_path: str = Field(description="Path to the test file written during RED phase")
    red_verified: bool = Field(default=False, description="True if initial test failed as expected")
    green_verified: bool = Field(default=False, description="True if implementation made test pass")
    summary: str = Field(description="Human-readable description of TDD execution")


class TDDCoordinator:
    """Enforces strict Test-Driven Development workflow for developer tasks."""

    def __init__(
        self,
        workspace_root: Path,
        dev_agent: Any,
        runner: PytestRunnerTool | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.dev = dev_agent
        self.runner = runner or PytestRunnerTool(self.workspace_root)

    def execute_tdd_cycle(
        self,
        task_description: str,
        test_file: str = "tests/test_feature.py",
    ) -> TDDResult:
        """Run strict RED -> GREEN -> REFACTOR development cycle."""
        # Step 1: RED Phase - Force Dev to write a failing test first
        red_prompt = (
            f"### TDD Step 1: RED Phase (Write Failing Test First)\n"
            f"Task: {task_description}\n\n"
            f"You MUST write a comprehensive unit test in '{test_file}' that reproduces or defines "
            f"the required behavior. Do NOT implement the feature code yet. "
            f"Write ONLY the test file using write_file."
        )
        self.dev.run(red_prompt, max_iterations=5)

        red_run = self.runner.run({"test_path": test_file})
        has_failure = (
            not red_run.success
            or (red_run.metadata or {}).get("failed", 0) > 0
            or (red_run.metadata or {}).get("errors", 0) > 0
        )

        if not has_failure:
            return TDDResult(
                phase=TDDPhase.FAILED,
                success=False,
                test_path=test_file,
                red_verified=False,
                green_verified=False,
                summary="TDD Violation: Test in RED phase passed without code implementation.",
            )

        # Step 2: GREEN Phase - Implement feature to make test pass
        green_prompt = (
            f"### TDD Step 2: GREEN Phase (Implement Code to Pass Test)\n"
            f"The reproduction test in '{test_file}' correctly FAILED as expected:\n"
            f"```\n{red_run.output[:1000]}\n```\n\n"
            f"Now implement the necessary production code to make the test pass. "
            f"Do NOT weaken or delete the test."
        )
        self.dev.run(green_prompt, max_iterations=8)

        green_run = self.runner.run({"test_path": test_file})
        now_passing = (
            green_run.success
            and (green_run.metadata or {}).get("failed", 0) == 0
            and (green_run.metadata or {}).get("errors", 0) == 0
        )

        if not now_passing:
            return TDDResult(
                phase=TDDPhase.GREEN,
                success=False,
                test_path=test_file,
                red_verified=True,
                green_verified=False,
                summary=f"TDD Incomplete: Implementation failed to turn test green: {green_run.error or green_run.output[:200]}",
            )

        return TDDResult(
            phase=TDDPhase.COMPLETED,
            success=True,
            test_path=test_file,
            red_verified=True,
            green_verified=True,
            summary="TDD Cycle Succeeded: Verified RED (failed) -> GREEN (passed) progression.",
        )
