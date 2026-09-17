from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from aegis_os.sandbox.quotas import ExecutionQuota

class CommandResult(BaseModel):
    """
    The structured, immutable result of a sandbox command execution.
    All tool code MUST use this model, never raw strings from subprocess calls
    """
    exit_code: int =Field(description="OS exit code. 0 is success, non-zero is failure.")
    stdout: str =Field(description="Captured standard output, potentially truncated.")
    stderr: str =Field(description="Captured standard error, potentially truncated.")
    timed_out: bool =Field(default=False,description="True if the process was forcefully killed due to timeout.",)
    output_truncated: bool =Field(default=False,description="True if combined stdout+stderr exceeded max_output_bytes.",)

    @property
    def success(self) -> bool:
        """Convenience: exit_code == 0 and not timed out."""
        return self.exit_code == 0 and not self.timed_out

    @property
    def combined_output(self) -> str:
        """Merge stdout and stderr for display."""
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout)
        if self.stderr.strip():
            parts.append(f"[STDERR]\n{self.stderr}")
        return "\n".join(parts) if parts else "(no output)"


class SandboxExecutor(ABC):
    """
    Abstract base class for all AegisOS sandbox execution backends.

    Subclasses implement `execute_command` to provide isolation guarantees
    appropriate to their environment (subprocess quotas, Docker containers, etc.).
    """

    @abstractmethod
    def execute_command(
        self,
        command: str,
        cwd: Optional[Path] = None,
        quota: Optional[ExecutionQuota] = None,
    ) -> CommandResult:
        """
        Execute a shell command and return a structured result.

        Args:
            command:  The shell command string to execute.
            cwd:      Working directory for the command. Defaults to None (inherited).
            quota:    Execution limits. Uses default quotas if None.

        Returns:
            A fully populated CommandResult. This method MUST NOT raise exceptions
            from subprocess failures — failures are encoded in the return value.
        """
        ...
