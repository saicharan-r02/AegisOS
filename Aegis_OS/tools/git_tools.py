import subprocess
from typing import Optional
from pydantic import BaseModel,Field
from Aegis_OS.tools.base import BaseAegisTool,ToolResult
from Aegis_OS.kernel.sandbox import SandboxExecutor

# 1. Git Status Tool
class GitStatusInput(BaseModel):
    pass

class GitStatusTool(BaseAegisTool):
    name="git_status"
    description="Checks current Git branch, modified files, staged and unstaged changes."
    args_schema=GitStatusInput

    def _run(self)->ToolResult:
        executor=SandboxExecutor()
        res=executor.run_command("git status --short")
        if not res.is_success:
            return ToolResult(success=False,error=res.stderr)
        output=res.stdout if res.stdout else "Working directory clean."
        return ToolResult(success=True,output=output)


# 2. Git Diff Tool
class GitDiffInput(BaseModel):
    staged: bool =Field(default=False,description="View staged diffs if True,unstaged if False.")

class GitDiffTool(BaseAegisTool):
    name="git_diff"
    description="Returns standard unified diff of modified files in the repository."
    args_schema=GitDiffInput

    def _run(self,staged: bool =False) -> ToolResult:
        executor=SandboxExecutor()
        cmd="git diff --staged" if staged else "git diff"
        res=executor.run_command(cmd)
        if not res.is_success:
            return ToolResult(success=False,error=res.stderr)
        output=res.stdout if res.stdout else "(No changes detected)"
        return ToolResult(success=True,output=output)

# 3. Git Create Branch Tool
class GitBranchInput(BaseModel):
    branch_name: str =Field(description="Name of the new branch to create and checkout.")

class GitBranchTool(BaseAegisTool):
    name="git_create_branch"
    description="Creates and checks out a new Git branch for an incident fix or feature."
    args_schema=GitBranchInput

    def _run(self,branch_name: str) -> ToolResult:
        executor=SandboxExecutor()
        res=executor.run_command(f"git checkout -b {branch_name}")
        if not res.is_success:
            return ToolResult(success=False,error=res.stderr)
        return ToolResult(success=True,output=f"Successfully created and checked out branch '{branch_name}'.")

# 4. Git Commit Tool
class GitCommitInput(BaseModel):
    message: str =Field(description="Descriptive commit message.")


class GitCommitTool(BaseAegisTool):
    name="git_commit"
    description="Stages all modified tracked files and creates a git commit."
    args_schema=GitCommitInput

    def _run(self,message: str) -> ToolResult:
        executor=SandboxExecutor()
        add_res=executor.run_command("git add -A")
        if not add_res.is_success:
            return ToolResult(success=False,error=add_res.stderr)

        commit_res=executor.run_command(f'git commit -m "{message}"')
        if not commit_res.is_success:
            return ToolResult(success=False,error=commit_res.stderr)
        return ToolResult(success=True,output=commit_res.stdout)

# 5. Git Rollback Tool
class GitRollbackInput(BaseModel):
    pass

class GitRollbackTool(BaseAegisTool):
    name="git_rollback"
    description="Discards all unstaged changes in the working directory to restore last clean state."
    args_schema=GitRollbackInput

    def _run(self) -> ToolResult:
        executor=SandboxExecutor()
        res=executor.run_command("git reset --hard HEAD")
        if not res.is_success:
            return ToolResult(success=False,error=res.stderr)
        return ToolResult(success=True,output="Successfully rolled back to last clean commit.")