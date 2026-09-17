"""
Subprocess Sandbox: Tier-1 Isolated Command Execution
=======================================================
Provides safe, resource-bounded subprocess execution for local development.

Engineering Decisions:
    1. Why `communicate()` and not `stdout.read()`?
       Reading stdout/stderr directly in a loop deadlocks when the OS pipe buffer
       fills up (typically ~64KB on Linux). `communicate()` uses threads internally
       to drain both pipes concurrently, preventing deadlock entirely.

    2. Why process tree termination instead of just `process.kill()`?
       A shell command like `bash -c "sleep 1000"` spawns bash AND sleep as a
       child. Killing only the parent bash process leaves the sleep zombie running.
       We kill the ENTIRE process group/tree to ensure full cleanup on timeout.

    3. Output truncation strategy:
       Rather than crashing when an agent generates 500MB of log output, we
       capture up to `max_output_bytes` and append a truncation notice. This keeps
       the calling agent loop healthy while signaling the overflow.

    4. Cross-platform compatibility:
       - Windows: uses `taskkill /F /T /PID <pid>` to terminate tree.
       - POSIX:   uses `os.killpg(os.getpgid(pid), signal.SIGKILL)` for group kill.
"""

import os
import platform
import signal
import subprocess
from pathlib import Path
from typing import Optional

from aegis_os.sandbox.base import CommandResult, SandboxExecutor
from aegis_os.sandbox.quotas import ExecutionQuota

_DEFAULT_QUOTA = ExecutionQuota()
_IS_WINDOWS = platform.system() == "Windows"

_TRUNCATION_NOTICE = (
    "\n\n[AEGIS WARNING] Output exceeded maximum byte limit and was truncated. "
    "Re-run with a narrower scope or increase max_output_bytes quota."
)


def _kill_process_tree(pid: int) -> None:
    """
    Terminate the entire process tree rooted at `pid`.

    On Windows, `taskkill /F /T` sends a SIGKILL-equivalent to the entire
    child process tree. On POSIX, we kill the entire process group.
    """
    try:
        if _IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                check=False,
            )
        else:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        # Process already exited — not an error condition
        pass


def _truncate_output(data: bytes, max_bytes: int) -> tuple[str, bool]:
    """
    Decode bytes and truncate to max_bytes if needed.

    Returns:
        (decoded_string, was_truncated)
    """
    if len(data) > max_bytes:
        truncated = data[:max_bytes].decode("utf-8", errors="replace")
        return truncated + _TRUNCATION_NOTICE, True
    return data.decode("utf-8", errors="replace"), False


class SubprocessSandbox(SandboxExecutor):
    """
    Tier-1 sandbox using Python subprocess with enforced quotas.

    Suitable for local development where Docker is not required.
    Provides: timeout-based process tree kill, output size limiting,
    and structured result encoding (never raises on subprocess failure).
    """

    def execute_command(
        self,
        command: str,
        cwd: Optional[Path] = None,
        quota: Optional[ExecutionQuota] = None,
    ) -> CommandResult:
        """
        Execute a shell command with full resource quota enforcement.

        Args:
            command: Shell command string (passed to shell=True on Windows,
                     or split and run directly on POSIX).
            cwd:     Working directory. If None, inherits from parent process.
            quota:   Resource limits. Uses _DEFAULT_QUOTA if None.

        Returns:
            CommandResult — always returns, never raises from subprocess errors.
        """
        active_quota = quota or _DEFAULT_QUOTA
        cwd_path = str(cwd) if cwd else None

        # Platform-specific process creation flags
        # On POSIX: create new process group so we can kill the entire tree.
        # On Windows: CREATE_NEW_PROCESS_GROUP for taskkill to work correctly.
        kwargs: dict = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "cwd": cwd_path,
            "shell": _IS_WINDOWS,  # shell=True needed on Windows for command strings
        }
        if _IS_WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True  # Creates new process group on POSIX

        # Prepare command
        cmd = command if _IS_WINDOWS else command.split() if isinstance(command, str) else command

        timed_out = False
        try:
            process = subprocess.Popen(cmd, **kwargs)  # noqa: S603
            try:
                raw_stdout, raw_stderr = process.communicate(
                    timeout=active_quota.timeout_seconds
                )
            except subprocess.TimeoutExpired:
                _kill_process_tree(process.pid)
                # Drain pipes after kill to avoid resource leaks
                raw_stdout, raw_stderr = process.communicate()
                timed_out = True

        except FileNotFoundError:
            # The command binary was not found (e.g., "pytest" not in PATH)
            return CommandResult(
                exit_code=127,
                stdout="",
                stderr=f"Command not found: '{command}'. Is it installed and on PATH?",
                timed_out=False,
                output_truncated=False,
            )
        except Exception as exc:  # noqa: BLE001
            # All other unexpected errors are encoded as a result, never re-raised
            return CommandResult(
                exit_code=1,
                stdout="",
                stderr=f"[SandboxError] Unexpected error during execution: {exc}",
                timed_out=False,
                output_truncated=False,
            )

        # Enforce output byte limits across combined stdout + stderr
        half_limit = active_quota.max_output_bytes // 2
        stdout_str, out_truncated = _truncate_output(raw_stdout, half_limit)
        stderr_str, err_truncated = _truncate_output(raw_stderr, half_limit)
        output_truncated = out_truncated or err_truncated

        exit_code = process.returncode if not timed_out else -1

        return CommandResult(
            exit_code=exit_code,
            stdout=stdout_str,
            stderr=stderr_str,
            timed_out=timed_out,
            output_truncated=output_truncated,
        )
