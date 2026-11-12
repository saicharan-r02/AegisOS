import logging
from pathlib import Path

from pydantic import BaseModel, Field

from aegis_os.kernel.context import redact_sensitive_text
from aegis_os.sandbox.base import SandboxExecutor
from aegis_os.sandbox.docker_sandbox import DockerSandbox
from aegis_os.sandbox.path_guard import PathTraversalError, validate_path
from aegis_os.sandbox.policy import CommandPolicy, CommandTier
from aegis_os.sandbox.quotas import ExecutionQuota
from aegis_os.sandbox.subprocess_sandbox import SubprocessSandbox
from aegis_os.tools.base import BaseAegisTool, ToolResult

logger = logging.getLogger(__name__)


class ExecuteCommandArgs(BaseModel):
    command: str = Field(description="The shell command to execute inside the sandbox.")
    cwd: str | None = Field(
        default=None,
        description=(
            "Working directory for the command, relative to workspace root. "
            "Defaults to workspace root if not provided."
        ),
    )
    timeout_seconds: float | None = Field(
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
        sandbox: SandboxExecutor | None = None,
        default_quota: ExecutionQuota | None = None,
        unsafe_local: bool = False,
        policy: CommandPolicy | None = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.unsafe_local = unsafe_local
        self.sandbox: SandboxExecutor = sandbox or (
            SubprocessSandbox() if unsafe_local else DockerSandbox(self.workspace_root)
        )
        self.default_quota = default_quota or ExecutionQuota()
        self.policy = policy or CommandPolicy()

    def _execute(self, args: ExecuteCommandArgs) -> ToolResult:
        try:
            cwd = validate_path(args.cwd or ".", self.workspace_root)
        except (PathTraversalError, ValueError) as exc:
            return ToolResult.fail(error=str(exc))
        if not cwd.is_dir():
            return ToolResult.fail(error=f"Working directory does not exist: '{args.cwd}'")

        decision = self.policy.evaluate(args.command, self.workspace_root)
        decision_metadata = {
            "policy_tier": decision.tier.value,
            "policy_reason": decision.reason,
            "command": redact_sensitive_text(args.command),
        }
        if decision.tier == CommandTier.DENY:
            return ToolResult.fail(
                error=f"Command denied by policy: {decision.reason}",
                metadata=decision_metadata,
            )
        if decision.tier == CommandTier.REQUIRE_APPROVAL:
            return ToolResult.fail(
                error=f"Human approval required: {decision.reason}",
                metadata={**decision_metadata, "approval_required": True},
            )
        if self.unsafe_local:
            logger.warning("UNSAFE LOCAL MODE: executing an auto-allowed command on the host.")

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
                **decision_metadata,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "output_truncated": result.output_truncated,
            },
        )
