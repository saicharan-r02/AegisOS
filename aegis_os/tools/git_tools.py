"""Workspace-scoped Git inspection and approval-gated commit tools."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from aegis_os.kernel.context import redact_sensitive_text
from aegis_os.sandbox.path_guard import PathTraversalError, validate_path
from aegis_os.sandbox.policy import CommandPolicy, CommandTier
from aegis_os.tools.base import BaseAegisTool, ToolResult


class GitStatusArgs(BaseModel):
    cwd: str | None = Field(default=None, description="Workspace-relative repository directory.")


class GitStatusTool(BaseAegisTool):
    """Read the current Git status using a fixed, read-only argument vector."""

    name = "git_status"
    description = "Get Git status for the current workspace."
    args_schema = GitStatusArgs
    parallel_safe = True

    def __init__(
        self, workspace_root: Path | None = None, policy: CommandPolicy | None = None
    ) -> None:
        self.workspace_root = workspace_root.resolve() if workspace_root else None
        self.policy = policy or CommandPolicy()

    def _execute(self, args: GitStatusArgs) -> ToolResult:
        try:
            cwd = _resolve_cwd(self.workspace_root, args.cwd)
        except (PathTraversalError, ValueError) as exc:
            return ToolResult.fail(str(exc))
        decision = self.policy.evaluate("git status", self.workspace_root or cwd)
        if decision.tier != CommandTier.AUTO_ALLOW:
            return ToolResult.fail(f"git status denied by policy: {decision.reason}")
        result = _run_git(["status", "--short"], cwd)
        if result.returncode != 0:
            return ToolResult.fail(f"git status failed: {result.stderr.strip()}")
        return ToolResult.ok(redact_sensitive_text(result.stdout.strip()) or "Working tree clean.")


class GitDiffArgs(BaseModel):
    staged: bool = Field(default=False, description="Show staged changes when true.")
    file_path: str | None = Field(
        default=None, description="Workspace-relative file to limit the diff."
    )
    cwd: str | None = Field(default=None, description="Workspace-relative repository directory.")


class GitDiffTool(BaseAegisTool):
    """Read a Git diff with workspace-scoped path validation."""

    name = "git_diff"
    description = "Show a redacted unified diff of current workspace changes."
    args_schema = GitDiffArgs
    parallel_safe = True

    def __init__(
        self, workspace_root: Path | None = None, policy: CommandPolicy | None = None
    ) -> None:
        self.workspace_root = workspace_root.resolve() if workspace_root else None
        self.policy = policy or CommandPolicy()

    def _execute(self, args: GitDiffArgs) -> ToolResult:
        try:
            cwd = _resolve_cwd(self.workspace_root, args.cwd)
            file_path = (
                validate_path(args.file_path, self.workspace_root)
                if args.file_path and self.workspace_root
                else Path(args.file_path).resolve()
                if args.file_path
                else None
            )
        except (PathTraversalError, ValueError) as exc:
            return ToolResult.fail(str(exc))
        command = "git diff --cached" if args.staged else "git diff"
        decision = self.policy.evaluate(command, self.workspace_root or cwd)
        if decision.tier != CommandTier.AUTO_ALLOW:
            return ToolResult.fail(f"git diff denied by policy: {decision.reason}")
        argv = ["diff"]
        if args.staged:
            argv.append("--cached")
        if file_path is not None:
            argv.extend(["--", str(file_path)])
        result = _run_git(argv, cwd)
        if result.returncode != 0:
            return ToolResult.fail(
                f"git diff failed: {redact_sensitive_text(result.stderr.strip())}"
            )
        return ToolResult.ok(redact_sensitive_text(result.stdout) or "(no changes)")


class GitCommitArgs(BaseModel):
    message: str = Field(min_length=1, description="Commit message.")
    add_all: bool = Field(
        default=False, description="Stage all changes in this worktree before committing."
    )
    cwd: str | None = Field(default=None, description="Workspace-relative repository directory.")


class GitCommitTool(BaseAegisTool):
    """Commit inside the workspace only after an approval callback grants it."""

    name = "git_commit"
    description = "Request approval, then create a Git commit in the current workspace."
    args_schema = GitCommitArgs

    def __init__(
        self,
        workspace_root: Path | None = None,
        policy: CommandPolicy | None = None,
        approval_callback: Callable[[str], bool] | None = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve() if workspace_root else None
        self.policy = policy or CommandPolicy()
        self.approval_callback = approval_callback

    def _execute(self, args: GitCommitArgs) -> ToolResult:
        try:
            cwd = _resolve_cwd(self.workspace_root, args.cwd)
        except (PathTraversalError, ValueError) as exc:
            return ToolResult.fail(str(exc))
        decision = self.policy.evaluate("git commit", self.workspace_root or cwd)
        approved = bool(self.approval_callback and self.approval_callback(args.message))
        if decision.tier == CommandTier.DENY or (
            decision.tier == CommandTier.REQUIRE_APPROVAL and not approved
        ):
            return ToolResult.fail(
                f"Human approval required for git commit: {decision.reason}",
                metadata={
                    "policy_tier": decision.tier.value,
                    "policy_reason": decision.reason,
                    "approval_required": decision.tier == CommandTier.REQUIRE_APPROVAL,
                    "command": "git commit",
                },
            )

        if args.add_all:
            status = _run_git(["status", "--porcelain", "-z"], cwd)
            if status.returncode != 0:
                return ToolResult.fail(f"git status failed: {status.stderr.strip()}")
            protected = _protected_status_paths(status.stdout)
            if protected:
                return ToolResult.fail(
                    "Commit blocked because sensitive paths are changed: " + ", ".join(protected),
                    metadata={"policy_tier": decision.tier.value, "approval_granted": True},
                )
            add_result = _run_git(["add", "-A"], cwd)
            if add_result.returncode != 0:
                return ToolResult.fail(f"git add failed: {add_result.stderr.strip()}")

        commit_result = _run_git(["commit", "-m", args.message], cwd)
        output = redact_sensitive_text((commit_result.stdout + commit_result.stderr).strip())
        return ToolResult(
            success=commit_result.returncode == 0,
            output=output,
            error=None if commit_result.returncode == 0 else "git commit failed.",
            metadata={
                "exit_code": commit_result.returncode,
                "message": redact_sensitive_text(args.message),
                "policy_tier": decision.tier.value,
                "approval_granted": approved,
            },
        )


class GitLogArgs(BaseModel):
    max_count: int = Field(
        default=10, ge=1, le=100, description="Maximum number of commits to show."
    )
    file_path: str | None = Field(default=None, description="Optional path to restrict log to.")
    cwd: str | None = Field(default=None, description="Workspace-relative repository directory.")


class GitLogTool(BaseAegisTool):
    """Show git commit logs."""

    name = "git_log"
    description = "Show recent git commit history with hashes, authors, dates, and messages."
    args_schema = GitLogArgs
    parallel_safe = True

    def __init__(
        self, workspace_root: Path | None = None, policy: CommandPolicy | None = None
    ) -> None:
        self.workspace_root = workspace_root
        self.policy = policy or CommandPolicy()

    def _execute(self, args: GitLogArgs) -> ToolResult:
        try:
            cwd = _resolve_cwd(self.workspace_root, args.cwd)
            file_path = (
                validate_path(args.file_path, self.workspace_root)
                if args.file_path and self.workspace_root
                else Path(args.file_path).resolve()
                if args.file_path
                else None
            )
        except (PathTraversalError, ValueError) as exc:
            return ToolResult.fail(str(exc))

        decision = self.policy.evaluate(f"git log -n {args.max_count}", self.workspace_root or cwd)
        if decision.tier != CommandTier.AUTO_ALLOW:
            return ToolResult.fail(f"git log denied by policy: {decision.reason}")

        argv = ["log", f"-n{args.max_count}", "--oneline", "--decorate"]
        if file_path is not None:
            argv.extend(["--", str(file_path)])
        result = _run_git(argv, cwd)
        if result.returncode != 0:
            return ToolResult.fail(
                f"git log failed: {redact_sensitive_text(result.stderr.strip())}"
            )
        return ToolResult.ok(redact_sensitive_text(result.stdout) or "(no commits)")


def _resolve_cwd(workspace_root: Path | None, requested: str | None) -> Path:
    if workspace_root:
        return validate_path(requested or ".", workspace_root)
    return Path(requested).resolve() if requested else Path.cwd().resolve()


def _run_git(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(
            ["git", *arguments], returncode=124, stdout="", stderr=str(exc)
        )


def _protected_status_paths(status: str) -> list[str]:
    protected = []
    for record in status.split("\0"):
        path = record[3:] if len(record) >= 4 else ""
        folded = path.casefold().replace("\\", "/")
        basename = Path(path).name.casefold()
        if (
            basename.startswith(".env")
            or basename in {"credentials", "secrets", "id_rsa", "id_ed25519", "id_ecdsa"}
            or any(
                part in {".git", ".aegis", ".ssh", ".aws", ".azure", ".gcloud", ".kube"}
                for part in folded.split("/")
            )
            or Path(basename).suffix in {".pem", ".key", ".p12", ".pfx", ".ppk"}
        ):
            protected.append(path)
    return protected
