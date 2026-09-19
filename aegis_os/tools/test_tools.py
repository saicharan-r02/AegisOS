import re
import sys
from typing import Optional
from pydantic import BaseModel,Field
from aegis_os.sandbox.quotas import ExecutionQuota
from aegis_os.sandbox.subprocess_sandbox import SubprocessSandbox
from aegis_os.tools.base import BaseAegisTool, ToolResult

_sandbox=SubprocessSandbox()

class PytestRunnerArgs(BaseModel):
    target: str=Field(
        default="tests/",
        description="Test path to run: a directory, a file, or a specific test e.g. tests/unit/test_state.py::TestAgentState::test_initial_state",
    )
    timeout_seconds: float=Field(
        default=60.0,
        gt=0,
        description="Maximum seconds before the test run is killed.",
    )
    extra_args: Optional[str]=Field(
        default=None,
        description="Additional pytest arguments e.g. '-x --tb=short'.",
    )
    cwd: Optional[str]=Field(
        default=None,
        description="Working directory for the test run.",
    )

class PytestRunnerTool(BaseAegisTool):
    """
    Execute pytest programmatically and return structured pass/fail diagnostics.
    Parses the test summary to extract pass count, failure count, error details,
    and the names of failing tests for structured root-cause feedback to the agent.
    """
    name="run_pytest"
    description=(
        "Run the pytest test suite and return structured results including "
        "pass count, failure count, failing test names, and error messages. "
        "Specify a target path to run a subset of tests."
    )
    args_schema=PytestRunnerArgs

    def _execute(self,args: PytestRunnerArgs) -> ToolResult:  # type: ignore[override]
        from pathlib import Path

        python_exe=sys.executable
        cmd_parts=[f'"{python_exe}"',"-m","pytest",args.target,"--tb=short","-q"]
        if args.extra_args:
            cmd_parts.append(args.extra_args)
        command=" ".join(cmd_parts)

        cwd=Path(args.cwd) if args.cwd else None
        quota=ExecutionQuota(timeout_seconds=args.timeout_seconds)
        result=_sandbox.execute_command(command,cwd=cwd,quota=quota)

        if result.timed_out:
            return ToolResult.fail(
                error=f"pytest timed out after {args.timeout_seconds} seconds. "
                      f"Try narrowing the target path or increasing timeout_seconds.",
                metadata={"timed_out": True},
            )

        combined=(result.stdout+"\n"+result.stderr).strip()

        # Parse summary line: e.g. "5 passed, 2 failed, 1 error in 3.21s"
        summary_match=re.search(
            r"([\d]+ passed)?[,\s]*([\d]+ failed)?[,\s]*([\d]+ error)?",
            combined,
        )
        passed=0
        failed=0
        errors=0
        if summary_match:
            passed=int(re.search(r"(\d+) passed",combined).group(1)) if re.search(r"(\d+) passed",combined) else 0
            failed=int(re.search(r"(\d+) failed",combined).group(1)) if re.search(r"(\d+) failed",combined) else 0
            errors=int(re.search(r"(\d+) error",combined).group(1)) if re.search(r"(\d+) error",combined) else 0
        # Extract failing test names
        failing_tests=re.findall(r"FAILED\s+([\w/\\:.\-]+)",combined)
        all_passed=result.exit_code == 0 and failed == 0 and errors == 0
        summary=f"Tests: {passed} passed, {failed} failed, {errors} errors."
        if failing_tests:
            summary += f"\nFailing tests:\n" + "\n".join(f"  - {t}" for t in failing_tests)
        return ToolResult(
            success=all_passed,
            output=combined,
            error=None if all_passed else summary,
            metadata={
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "failing_tests": failing_tests,
                "exit_code": result.exit_code,
            },
        )