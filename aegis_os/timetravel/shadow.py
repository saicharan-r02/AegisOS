"""Git shadow branch and filesystem snapshot management for time-travel debugging."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class ShadowBranchManager:
    """Manages ephemeral git shadow branches and tagged filesystem step checkpoints."""

    def __init__(self, workspace_root: Path, snapshots_dir: Path | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.snapshots_dir = (snapshots_dir or (self.workspace_root / ".aegis" / "snapshots")).resolve()
        self._base_branch: str | None = None

    def _run_git(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )

    def is_git_repo(self) -> bool:
        """Check if workspace is a git repository."""
        proc = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return proc.returncode == 0 and "true" in proc.stdout.lower()

    def get_current_branch(self) -> str:
        """Get the active git branch name or HEAD."""
        proc = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return proc.stdout.strip() if proc.returncode == 0 else "main"

    def create_shadow_branch(self, session_id: str) -> str:
        """Create and checkout an isolated shadow branch for the mission: aegis/mission/{session_id}."""
        clean_id = session_id.replace("/", "_").replace("\\", "_")
        branch_name = f"aegis/mission/{clean_id}"

        if not self.is_git_repo():
            return branch_name

        self._base_branch = self.get_current_branch()
        # Checkout existing or create new branch
        proc = self._run_git(["checkout", "-b", branch_name])
        if proc.returncode != 0:
            # If already exists, switch to it
            self._run_git(["checkout", branch_name])

        return branch_name

    def commit_step(self, session_id: str, step_index: int, message: str = "") -> str:
        """Commit current filesystem state and tag with aegis/checkpoint/{session_id}/{step_index}."""
        clean_id = session_id.replace("/", "_").replace("\\", "_")
        tag_name = f"aegis/checkpoint/{clean_id}/{step_index}"

        if self.is_git_repo():
            # Stage all changes except ignored directories
            self._run_git(["add", "-A"])
            commit_msg = message or f"aegis checkpoint: step {step_index} [{session_id}]"
            self._run_git(["commit", "-m", commit_msg, "--allow-empty"])
            # Create or update tag
            self._run_git(["tag", "-f", tag_name])
            rev_proc = self._run_git(["rev-parse", "HEAD"])
            return rev_proc.stdout.strip() if rev_proc.returncode == 0 else tag_name

        # Fallback: copy snapshot to .aegis/snapshots/{session_id}/{step_index}
        snap_path = self.snapshots_dir / clean_id / str(step_index)
        if snap_path.exists():
            shutil.rmtree(snap_path, ignore_errors=True)
        snap_path.mkdir(parents=True, exist_ok=True)

        for item in self.workspace_root.iterdir():
            if item.name in {".git", ".aegis", ".venv", "node_modules", "__pycache__"}:
                continue
            dest = snap_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            elif item.is_file():
                shutil.copy2(item, dest)

        return str(snap_path)

    def restore_step(self, session_id: str, step_index: int) -> tuple[bool, str]:
        """Restore filesystem to the exact state at step_index."""
        clean_id = session_id.replace("/", "_").replace("\\", "_")
        tag_name = f"aegis/checkpoint/{clean_id}/{step_index}"

        if self.is_git_repo():
            # Verify tag exists
            tag_check = self._run_git(["rev-parse", "--verify", tag_name])
            if tag_check.returncode == 0:
                # Reset hard to tag and clean untracked files
                reset_proc = self._run_git(["reset", "--hard", tag_name])
                self._run_git(["clean", "-fd"])
                if reset_proc.returncode == 0:
                    return True, f"Filesystem restored to git tag '{tag_name}'."
                return False, f"Git reset failed: {reset_proc.stderr}"

        # Fallback snapshot restore
        snap_path = self.snapshots_dir / clean_id / str(step_index)
        if not snap_path.is_dir():
            return False, f"No filesystem snapshot found for step {step_index}."

        # Remove existing files except protected dirs and open database files
        locked_suffixes = {".db", ".sqlite", ".sqlite3"}
        for item in self.workspace_root.iterdir():
            if item.name in {".git", ".aegis", ".venv", "node_modules", "__pycache__"}:
                continue
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            elif item.is_file():
                if item.suffix.lower() in locked_suffixes:
                    # Skip database files that may be held open by an active connection
                    continue
                try:
                    item.unlink(missing_ok=True)
                except PermissionError:
                    # File is locked by another process – skip gracefully
                    pass

        # Copy back from snapshot
        for item in snap_path.iterdir():
            dest = self.workspace_root / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            elif item.is_file():
                shutil.copy2(item, dest)

        return True, f"Filesystem restored from snapshot '{snap_path}'."

    def finalize_mission(
        self,
        session_id: str,
        success: bool,
        target_branch: str | None = None,
    ) -> bool:
        """Merge shadow branch on success or restore base branch on abort."""
        if not self.is_git_repo():
            return True

        clean_id = session_id.replace("/", "_").replace("\\", "_")
        shadow_branch = f"aegis/mission/{clean_id}"
        base = target_branch or self._base_branch or "main"

        if success:
            # Checkout base branch and merge shadow branch
            self._run_git(["checkout", base])
            proc = self._run_git(["merge", "--no-ff", "-m", f"Merge Aegis mission {session_id}", shadow_branch])
            return proc.returncode == 0
        else:
            # Mission failed or aborted: switch back to base branch leaving it untouched
            self._run_git(["checkout", base])
            self._run_git(["reset", "--hard", "HEAD"])
            return True
