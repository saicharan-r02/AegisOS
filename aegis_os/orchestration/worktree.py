"""Git worktree isolation for concurrent or isolated task execution."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class WorktreeManager:
    """Manages isolated git worktrees for parallel agent task execution."""

    def __init__(self, workspace_root: Path, base_dir: Path | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.worktrees_dir = (base_dir or (self.workspace_root / ".aegis" / "worktrees")).resolve()
        self.active_worktrees: dict[str, Path] = {}

    def _run_git(
        self, args: list[str], cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.workspace_root,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )

    def is_git_repo(self) -> bool:
        """Check if workspace is a git repository."""
        proc = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return proc.returncode == 0 and "true" in proc.stdout.lower()

    def create_worktree(self, task_id: str) -> Path:
        """Create an isolated worktree for a task, falling back to directory copy if non-git."""
        clean_id = task_id.replace("/", "_").replace("\\", "_")
        target_dir = self.worktrees_dir / f"task_{clean_id}"
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

        if target_dir.exists():
            self.cleanup_worktree(task_id)

        if self.is_git_repo():
            branch_name = f"aegis/task-{clean_id}"
            # Delete branch if already exists from prior run
            self._run_git(["branch", "-D", branch_name])
            proc = self._run_git(["worktree", "add", "-b", branch_name, str(target_dir), "HEAD"])
            if proc.returncode == 0:
                self.active_worktrees[task_id] = target_dir
                return target_dir

        # Fallback: create isolated directory copy of workspace
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in self.workspace_root.iterdir():
            if item.name in {".git", ".aegis", ".venv", "node_modules", "__pycache__"}:
                continue
            dest = target_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            elif item.is_file():
                shutil.copy2(item, dest)

        self.active_worktrees[task_id] = target_dir
        return target_dir

    def merge_worktree(self, task_id: str) -> tuple[bool, str]:
        """Merge changes from worktree branch or copy modified files back to main workspace."""
        clean_id = task_id.replace("/", "_").replace("\\", "_")
        worktree_path = self.active_worktrees.get(task_id) or (
            self.worktrees_dir / f"task_{clean_id}"
        )

        if not worktree_path.exists():
            return False, f"Worktree not found for task '{task_id}'."

        if self.is_git_repo():
            branch_name = f"aegis/task-{clean_id}"
            # Commit any pending changes inside worktree
            self._run_git(["add", "-A"], cwd=worktree_path)
            self._run_git(
                ["commit", "-m", f"Auto-commit worktree task {task_id}"], cwd=worktree_path
            )

            # Merge branch into workspace
            proc = self._run_git(
                ["merge", "--no-ff", "-m", f"Merge worktree {task_id}", branch_name]
            )
            if proc.returncode == 0:
                return True, "Merged successfully."
            # Attempt rebase / abort on conflict
            self._run_git(["merge", "--abort"])
            return False, f"Merge conflict on branch {branch_name}: {proc.stderr}"

        # Fallback for non-git directory: copy modified files back
        for root, _, files in worktree_path.walk():
            for fname in files:
                src_file = root / fname
                rel_path = src_file.relative_to(worktree_path)
                dest_file = self.workspace_root / rel_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest_file)

        return True, "Synced directory changes back to workspace."

    def cleanup_worktree(self, task_id: str) -> None:
        """Remove worktree and delete its ephemeral branch."""
        clean_id = task_id.replace("/", "_").replace("\\", "_")
        worktree_path = self.active_worktrees.pop(task_id, None) or (
            self.worktrees_dir / f"task_{clean_id}"
        )

        if self.is_git_repo():
            self._run_git(["worktree", "remove", "--force", str(worktree_path)])
            self._run_git(["branch", "-D", f"aegis/task-{clean_id}"])

        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

    def cleanup_all(self) -> None:
        """Cleanup all managed worktrees."""
        for task_id in list(self.active_worktrees.keys()):
            self.cleanup_worktree(task_id)
        if self.worktrees_dir.exists():
            shutil.rmtree(self.worktrees_dir, ignore_errors=True)
