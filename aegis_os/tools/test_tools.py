import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from aegis_os.sandbox.base import SandboxExecutor
from aegis_os.sandbox.docker_sandbox import DockerSandbox
from aegis_os.sandbox.path_guard import PathTraversalError, validate_path
from aegis_os.sandbox.policy import CommandPolicy, CommandTier
from aegis_os.sandbox.quotas import ExecutionQuota
from aegis_os.sandbox.subprocess_sandbox import SubprocessSandbox
from aegis_os.tools.base import BaseAegisTool, ToolResult


class PytestRunnerArgs(BaseModel):
    target: str = Field(
        default="tests/",
        description="Test path to run: a directory, a file, or a specific test e.g. tests/unit/test_state.py::TestAgentState::test_initial_state",
    )
    timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        description="Maximum seconds before the test run is killed.",
    )
    extra_args: str | None = Field(
        default=None,
        description="Additional pytest arguments e.g. '-x --tb=short'.",
    )
    cwd: str | None = Field(
        default=None,
        description="Working directory for the test run.",
    )


class PytestRunnerTool(BaseAegisTool):
    """
    Execute pytest programmatically and return structured pass/fail diagnostics.
    Parses the test summary to extract pass count, failure count, error details,
    and the names of failing tests for structured root-cause feedback to the agent.
    """

    name = "run_pytest"
    description = (
        "Run the pytest test suite and return structured results including "
        "pass count, failure count, failing test names, and error messages. "
        "Specify a target path to run a subset of tests."
    )
    args_schema = PytestRunnerArgs

    def __init__(
        self,
        workspace_root: Path | None = None,
        sandbox: SandboxExecutor | None = None,
        unsafe_local: bool = False,
        policy: CommandPolicy | None = None,
    ) -> None:
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.sandbox = sandbox or (
            SubprocessSandbox() if unsafe_local else DockerSandbox(self.workspace_root)
        )
        self.policy = policy or CommandPolicy()

    def _relative_target(self, target: str, cwd: Path) -> str:
        """Turn an absolute path inside the workspace into a relative one (policy-safe, portable)."""
        try:
            candidate = Path(target)
            if candidate.is_absolute():
                return candidate.resolve().relative_to(cwd.resolve()).as_posix() or "."
        except (ValueError, OSError):
            pass
        return target

    def _execute(self, args: PytestRunnerArgs) -> ToolResult:  # type: ignore[override]
        try:
            cwd = validate_path(args.cwd or ".", self.workspace_root)
        except (PathTraversalError, ValueError) as exc:
            return ToolResult.fail(str(exc))
        python_exe = sys.executable if isinstance(self.sandbox, SubprocessSandbox) else "python"
        target = self._relative_target(args.target, cwd)
        cmd_parts = [python_exe, "-m", "pytest", target, "--tb=short", "-q"]
        if args.extra_args:
            try:
                cmd_parts.extend(shlex.split(args.extra_args, posix=True))
            except ValueError as exc:
                return ToolResult.fail(f"Invalid pytest arguments: {exc}")
        command = subprocess.list2cmdline(cmd_parts) if os.name == "nt" else shlex.join(cmd_parts)
        decision = self.policy.evaluate(command, self.workspace_root)
        if decision.tier != CommandTier.AUTO_ALLOW:
            return ToolResult.fail(
                f"Pytest command was blocked by command policy: {decision.reason}",
                metadata={
                    "policy_tier": decision.tier.value,
                    "approval_required": decision.tier == CommandTier.REQUIRE_APPROVAL,
                },
            )
        quota = ExecutionQuota(timeout_seconds=args.timeout_seconds)
        result = self.sandbox.execute_command(command, cwd=cwd, quota=quota)

        if result.timed_out:
            return ToolResult.fail(
                error=f"pytest timed out after {args.timeout_seconds} seconds. "
                f"Try narrowing the target path or increasing timeout_seconds.",
                metadata={"timed_out": True},
            )

        combined = (result.stdout + "\n" + result.stderr).strip()

        # Parse summary line: e.g. "5 passed, 2 failed, 1 error in 3.21s"
        summary_match = re.search(
            r"([\d]+ passed)?[,\s]*([\d]+ failed)?[,\s]*([\d]+ error)?",
            combined,
        )
        passed = 0
        failed = 0
        errors = 0
        if summary_match:
            passed_match = re.search(r"(\d+) passed", combined)
            failed_match = re.search(r"(\d+) failed", combined)
            errors_match = re.search(r"(\d+) error", combined)
            passed = int(passed_match.group(1)) if passed_match else 0
            failed = int(failed_match.group(1)) if failed_match else 0
            errors = int(errors_match.group(1)) if errors_match else 0
        failing_tests = re.findall(r"FAILED\s+([\w/\\:.\-]+)", combined)
        no_tests_collected = (
            not result.timed_out
            and (result.exit_code == 5 or "no tests ran" in combined.lower() or "no tests collected" in combined.lower())
        )
        # A zero-test run is not a successful verification, even if a wrapper
        # accidentally reports exit code 0.
        all_passed = result.exit_code == 0 and passed > 0 and failed == 0 and errors == 0
        summary = f"Tests: {passed} passed, {failed} failed, {errors} errors."
        if no_tests_collected:
            summary += (
                f"\nNO_TESTS_COLLECTED: No tests were collected from '{target}'. "
                "Do not rerun the identical command. Ask the supervisor for one focused "
                "acceptance-test bootstrap or use a verifier for this repository's language."
            )
        elif passed == 0 and failed == 0 and errors == 0 and not result.timed_out:
            summary += "\nUNVERIFIED_TEST_RESULT: pytest returned no parseable test counts."
        if failing_tests:
            summary += "\nFailing tests:\n" + "\n".join(f"  - {t}" for t in failing_tests)
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
                "no_tests_collected": no_tests_collected,
                "status": "NO_TESTS_COLLECTED" if no_tests_collected else ("PASSED" if all_passed else "FAILED"),
            },
        )
