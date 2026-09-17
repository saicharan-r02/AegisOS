"""
Terminal Tool: Sandboxed Command Execution
==========================================
Wraps SubprocessSandbox as an AegisOS tool, allowing the agent
to run shell commands through the validated, quota-bounded execution pipeline.

Security Note:
    This tool executes arbitrary shell commands. It is a HIGH-RISK capability.
    In Milestone 6, ExecuteCommandTool will be wrapped by the Security Policy
    Gateway which enforces RBAC rules and command blocklists before this tool
    is ever invoked. For Milestone 1, we implement the tool with clean
    contracts and trust the test suite to verify sandbox quotas enforce correctly.
"""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from aegis_os.sandbox.base import SandboxExecutor
from aegis_os.sandbox.quotas import ExecutionQuota
from aegis_os.sandbox.subprocess_sandbox import SubprocessSandbox
from aegis_os.tools.base import BaseAegisTool, ToolResult


class ExecuteCommandArgs(BaseModel):
    command: str = Field(
        description="The shell command to execute inside the sandbox."
    )
    cwd: Optional[str] = Field(
        default=None,
        description=(
            "Working directory for the command, relative to workspace root. "
            "Defaults to workspace root if not provided."
        ),
    )
    timeout_seconds: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Override the default execution timeout. "
            "The process tree is killed if this limit is exceeded."
        ),
    )


class ExecuteCommandTool(BaseAegisTool):
    """
    Execute a shell command inside the AegisOS subprocess sandbox.

    Results include exit code, stdout, stderr, and timeout/truncation flags.
    The tool never raises — all execution failures are encoded in ToolResult.
    """

    name = "execute_command"
    description = (
        "Execute a shell command in the secure AegisOS sandbox. "
        "Returns the exit code, stdout, stderr, and whether the command timed out. "
        "Commands are killed if they exceed the execution timeout."
    )
    args_schema = ExecuteCommandArgs

    def __init__(
        self,
        workspace_root: Path,
        sandbox: Optional[SandboxExecutor] = None,
        default_quota: Optional[ExecutionQuota] = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.sandbox: SandboxExecutor = sandbox or SubprocessSandbox()
        self.default_quota = default_quota or ExecutionQuota()

    def _execute(self, args: ExecuteCommandArgs) -> ToolResult:  # type: ignore[override]
        # Resolve working directory
        if args.cwd:
            cwd = self.workspace_root / args.cwd
            if not cwd.is_dir():
                return ToolResult.fail(
                    error=f"Working directory does not exist: '{args.cwd}'"
                )
        else:
            cwd = self.workspace_root

        # Build quota (allow per-call timeout override)
        if args.timeout_seconds is not None:
            quota = ExecutionQuota(
                timeout_seconds=args.timeout_seconds,
                max_output_bytes=self.default_quota.max_output_bytes,
            )
        else:
            quota = self.default_quota

        result = self.sandbox.execute_command(
            command=args.command,
            cwd=cwd,
            quota=quota,
        )

        # Format output for agent readability
        output_parts = []
        if result.stdout.strip():
            output_parts.append(f"STDOUT:\n{result.stdout}")
        if result.stderr.strip():
            output_parts.append(f"STDERR:\n{result.stderr}")
        if result.timed_out:
            output_parts.append(
                f"[TIMEOUT] Command exceeded {quota.timeout_seconds}s limit and was killed."
            )
        if result.output_truncated:
            output_parts.append("[WARNING] Output was truncated due to size limit.")

        formatted_output = "\n\n".join(output_parts) or "(no output)"

        success = result.success
        error_msg = None
        if not success:
            if result.timed_out:
                error_msg = f"Command timed out after {quota.timeout_seconds} seconds."
            else:
                error_msg = f"Command exited with code {result.exit_code}."

        return ToolResult(
            success=success,
            output=formatted_output,
            error=error_msg,
            metadata={
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "output_truncated": result.output_truncated,
                "command": args.command,
            },
        )
