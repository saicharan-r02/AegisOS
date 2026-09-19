from typing import Optional
from pydantic import BaseModel,Field
from aegis_os.sandbox.subprocess_sandbox import SubprocessSandbox
from aegis_os.sandbox.quotas import ExecutionQuota
from aegis_os.tools.base import BaseAegisTool, ToolResult

_sandbox=SubprocessSandbox()
_quota=ExecutionQuota(timeout_seconds=30.0)

class GitStatusArgs(BaseModel):
    cwd: Optional[str]=Field(
        default=None,
        description="Path to git repository. Defaults to current directory."
    )

class GitStatusTool(BaseAegisTool):
    """Get the current git status of the repository."""
    name="git_status"
    description="Get current git status showing staged, unstaged, and untracked files."
    args_schema=GitStatusArgs

    def _execute(self,args: GitStatusArgs) -> ToolResult:  # type: ignore[override]
        from pathlib import Path
        cwd=Path(args.cwd)if args.cwd else None
        result=_sandbox.execute_command("git status",cwd=cwd,quota=_quota)
        if result.timed_out:
            return ToolResult.fail(error="git status timed out.")
        output=result.stdout+result.stderr
        return ToolResult(
            success=result.exit_code==0,
            output=output.strip(),
            error=None if result.exit_code==0 else f"git status failed (exit {result.exit_code})",
            metadata={"exit_code": result.exit_code},
        )

class GitDiffArgs(BaseModel):
    staged: bool=Field(
        default=False,
        description="If True, show diff of staged changes. Otherwise shows unstaged diff."
    )
    file_path: Optional[str]=Field(
        default=None,
        description="Limit diff to a specific file path."
    )
    cwd: Optional[str]=Field(default=None,description="Path to git repository.")

class GitDiffTool(BaseAegisTool):
    """Get the diff of current changes in the repository."""
    name="git_diff"
    description="Show unified diff of changes in the repository. Use staged=True to see staged changes."
    args_schema=GitDiffArgs

    def _execute(self,args: GitDiffArgs) -> ToolResult:  # type: ignore[override]
        from pathlib import Path
        cmd_parts=["git","diff"]
        if args.staged:
            cmd_parts.append("--cached")
        if args.file_path:
            cmd_parts.extend(["--",args.file_path])

        cwd=Path(args.cwd)if args.cwd else None
        result=_sandbox.execute_command(" ".join(cmd_parts),cwd=cwd,quota=_quota)
        if result.timed_out:
            return ToolResult.fail(error="git diff timed out.")
        output=result.stdout or "(no changes)"
        return ToolResult(
            success=result.exit_code==0,
            output=output,
            error=None if result.exit_code==0 else result.stderr,
            metadata={"exit_code":result.exit_code,"staged":args.staged},
        )

class GitCommitArgs(BaseModel):
    message: str=Field(description="Commit message (should follow conventional commits format).")
    add_all: bool=Field(
        default=False,
        description="If True, stage all tracked modified files before committing (git add -u)."
    )
    cwd: Optional[str]=Field(default=None,description="Path to git repository.")


class GitCommitTool(BaseAegisTool):
    """Stage and commit changes to the git repository."""
    name:str="git_commit"
    description=(
        "Stage modified files and create a git commit. "
        "Set add_all=True to stage all modified tracked files automatically."
    )
    args_schema=GitCommitArgs

    def _execute(self,args: GitCommitArgs) -> ToolResult:  # type: ignore[override]
        from pathlib import Path
        cwd = Path(args.cwd) if args.cwd else None

        if args.add_all:
            add_result = _sandbox.execute_command("git add -u", cwd=cwd, quota=_quota)
            if add_result.exit_code != 0:
                return ToolResult.fail(
                    error=f"git add -u failed: {add_result.stderr}"
                )

        safe_message=args.message.replace('"','\\"')
        commit_result=_sandbox.execute_command(
            f'git commit -m "{safe_message}"',
            cwd=cwd,
            quota=_quota,
        )
        output=commit_result.stdout+commit_result.stderr
        return ToolResult(
            success=commit_result.exit_code==0,
            output=output.strip(),
            error=None if commit_result.exit_code==0 else f"git commit failed: {commit_result.stderr}",
            metadata={"exit_code": commit_result.exit_code,"message":args.message},
        )