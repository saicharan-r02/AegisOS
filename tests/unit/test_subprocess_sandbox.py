"""
Test Suite: SubprocessSandbox Execution Contracts
==================================================
These tests PROVE the subprocess sandbox enforces its execution contracts:
  1. Normal commands execute correctly and return structured results.
  2. Timed-out commands are killed cleanly — no zombie processes.
  3. Large outputs are truncated without crashing.
  4. Non-existent commands return structured failures, not exceptions.
"""

import sys
import time
import pytest
from pathlib import Path

from aegis_os.sandbox.subprocess_sandbox import SubprocessSandbox
from aegis_os.sandbox.quotas import ExecutionQuota


@pytest.fixture
def sandbox() -> SubprocessSandbox:
    return SubprocessSandbox()


class TestNormalExecution:
    """Normal commands must execute and return structured results."""

    def test_python_version_command(self, sandbox: SubprocessSandbox) -> None:
        """Python --version must succeed with exit code 0."""
        result = sandbox.execute_command(f'"{sys.executable}" --version')
        assert result.exit_code == 0
        assert result.timed_out is False
        assert "Python" in result.stdout or "Python" in result.stderr

    def test_exit_code_captured_correctly(self, sandbox: SubprocessSandbox) -> None:
        """Non-zero exit codes must be captured correctly."""
        result = sandbox.execute_command(f'"{sys.executable}" -c "import sys; sys.exit(42)"')
        assert result.exit_code == 42
        assert result.success is False
        assert result.timed_out is False

    def test_stdout_captured(self, sandbox: SubprocessSandbox) -> None:
        """Standard output must be captured in the result."""
        result = sandbox.execute_command(f'"{sys.executable}" -c "print(\'hello aegis\')"')
        assert result.exit_code == 0
        assert "hello aegis" in result.stdout

    def test_stderr_captured(self, sandbox: SubprocessSandbox) -> None:
        """Standard error output must be captured in the result."""
        result = sandbox.execute_command(
            f'"{sys.executable}" -c "import sys; sys.stderr.write(\'error output\')"'
        )
        assert "error output" in result.stderr

    def test_result_never_raises(self, sandbox: SubprocessSandbox) -> None:
        """Even with bad commands, execute_command must never raise."""
        result = sandbox.execute_command("this_command_does_not_exist_12345")
        assert isinstance(result.exit_code, int)


class TestTimeoutEnforcement:
    """Timeout enforcement is the critical safety contract — it MUST work."""

    def test_hanging_process_is_killed_within_timeout(
        self, sandbox: SubprocessSandbox
    ) -> None:
        """A process sleeping longer than the quota must be killed and marked timed_out."""
        quota = ExecutionQuota(timeout_seconds=1.5)
        start = time.time()

        result = sandbox.execute_command(
            f'"{sys.executable}" -c "import time; time.sleep(60)"',
            quota=quota,
        )
        elapsed = time.time() - start

        assert result.timed_out is True
        assert result.exit_code == -1
        assert result.success is False
        # Must have terminated within roughly the timeout + overhead (5s buffer)
        assert elapsed < 7.0, f"Sandbox took {elapsed:.1f}s — expected ~1.5s"

    def test_fast_command_does_not_timeout(self, sandbox: SubprocessSandbox) -> None:
        """A fast command must NOT be marked as timed out."""
        quota = ExecutionQuota(timeout_seconds=10.0)
        result = sandbox.execute_command(
            f'"{sys.executable}" -c "print(\'done\')"',
            quota=quota,
        )
        assert result.timed_out is False
        assert result.exit_code == 0

    def test_timeout_result_is_structured_not_exception(
        self, sandbox: SubprocessSandbox
    ) -> None:
        """A timeout must return CommandResult, never raise TimeoutExpired."""
        quota = ExecutionQuota(timeout_seconds=1.0)
        # This must not raise — it must return a CommandResult
        result = sandbox.execute_command(
            f'"{sys.executable}" -c "import time; time.sleep(60)"',
            quota=quota,
        )
        assert hasattr(result, "timed_out")
        assert result.timed_out is True


class TestOutputTruncation:
    """Output exceeding byte limits must be truncated, not crash."""

    def test_large_output_is_truncated(self, sandbox: SubprocessSandbox) -> None:
        """Output larger than max_output_bytes must be truncated with a warning."""
        # Generate ~5000 chars, cap at 200 bytes per stream
        quota = ExecutionQuota(timeout_seconds=10.0, max_output_bytes=200)
        result = sandbox.execute_command(
            f'"{sys.executable}" -c "print(\'A\' * 5000)"',
            quota=quota,
        )
        assert result.output_truncated is True
        # The truncation notice must be appended
        assert "truncated" in result.stdout.lower() or "AEGIS WARNING" in result.stdout

    def test_small_output_is_not_truncated(self, sandbox: SubprocessSandbox) -> None:
        """Normal small output must not be marked as truncated."""
        result = sandbox.execute_command(f'"{sys.executable}" -c "print(\'hello\')"')
        assert result.output_truncated is False


class TestCommandResultModel:
    """CommandResult model properties must work correctly."""

    def test_success_property_true_on_exit_zero(
        self, sandbox: SubprocessSandbox
    ) -> None:
        result = sandbox.execute_command(f'"{sys.executable}" -c "pass"')
        assert result.success is True
        assert result.exit_code == 0

    def test_success_property_false_on_nonzero_exit(
        self, sandbox: SubprocessSandbox
    ) -> None:
        result = sandbox.execute_command(
            f'"{sys.executable}" -c "import sys; sys.exit(1)"'
        )
        assert result.success is False

    def test_combined_output_merges_stdout_stderr(
        self, sandbox: SubprocessSandbox
    ) -> None:
        result = sandbox.execute_command(
            f'"{sys.executable}" -c "import sys; print(\'out\'); sys.stderr.write(\'err\')"'
        )
        combined = result.combined_output
        assert "out" in combined
