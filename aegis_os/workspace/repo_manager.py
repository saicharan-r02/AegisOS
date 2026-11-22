"""
AegisOS External Repository & Workspace Manager.

Responsible for:
1. Cloning external Git repositories (GitHub/GitLab/etc.) into isolated mission workspaces.
2. Creating new project workspaces for missions without a repo URL.
3. Packaging completed mission workspaces as downloadable ZIP archives.
4. Pushing fixes to the origin remote when requested.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

logger = logging.getLogger("aegis_os.workspace.repo_manager")

BASE_WORKSPACES_DIR = Path("workspaces").resolve()


def get_mission_workspace(session_id: str) -> Path:
    """Return the absolute path for a mission's isolated workspace."""
    ws = BASE_WORKSPACES_DIR / session_id
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _reset_dir(path: Path) -> None:
    """Cleanly remove and recreate a workspace directory (handling Windows read-only .git files)."""
    def _on_rm_error(func, fpath, _exc_info):
        try:
            os.chmod(fpath, 0o777)
            func(fpath)
        except Exception:
            pass

    if path.exists():
        shutil.rmtree(path, onerror=_on_rm_error)
    path.mkdir(parents=True, exist_ok=True)


def _sanitize_url(u: str) -> str:
    """Strip authentication tokens from git URLs for safe logging and error reporting."""
    return re.sub(r"://[^@]+@", "://", u)


def prepare_workspace(
    session_id: str,
    repo_url: str | None = None,
    repo_branch: str | None = "main",
    working_branch: str | None = None,
) -> Path:
    """
    Prepare an isolated workspace for a mission.
    If repo_url is provided, clones the repository into workspaces/{session_id}.
    Otherwise, creates an empty git repository in workspaces/{session_id}.
    Never modifies the host AegisOS repository.
    """
    ws = BASE_WORKSPACES_DIR / session_id
    _reset_dir(ws)

    if repo_url and repo_url.strip():
        url = repo_url.strip()

        # Check if URL is a GitHub issue URL: https://github.com/<owner>/<repo>/issues/<num>
        issue_match = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", url)
        target_branch_name = working_branch
        if issue_match:
            owner, repo_name, issue_num = issue_match.group(1), issue_match.group(2), issue_match.group(3)
            url = f"https://github.com/{owner}/{repo_name}.git"
            if not target_branch_name:
                target_branch_name = f"aegis/issue-{issue_num}"

        if not target_branch_name:
            target_branch_name = f"aegis-fix-{session_id[:8]}"

        clean_url = _sanitize_url(url)
        token = os.getenv("GITHUB_TOKEN", "").strip()
        auth_url = url
        if token and "github.com/" in url and "@" not in url:
            auth_url = url.replace("https://github.com/", f"https://x-access-token:{token}@github.com/")

        logger.info("Cloning external repo %s (branch: %s) into %s", clean_url, repo_branch, ws)
        try:
            # 1. Try branch clone with auth_url
            cmd = ["git", "clone", "-c", "core.longpaths=true"]
            if repo_branch and repo_branch.strip():
                cmd.extend(["--branch", repo_branch.strip()])
            cmd.extend(["--depth", "50", auth_url, str(ws)])
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)

            # 2. If branch clone failed, try default branch
            if res.returncode != 0:
                logger.warning(
                    "Branch clone failed (%s), cloning default branch...",
                    _sanitize_url(res.stderr.strip()),
                )
                _reset_dir(ws)
                res_fallback = subprocess.run(
                    ["git", "clone", "-c", "core.longpaths=true", "--depth", "50", auth_url, str(ws)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                # 3. If authenticated clone failed, try unauthenticated public clone
                if res_fallback.returncode != 0 and auth_url != url:
                    logger.warning("Authenticated clone failed, trying public clone...")
                    _reset_dir(ws)
                    res_fallback = subprocess.run(
                        ["git", "clone", "-c", "core.longpaths=true", "--depth", "50", url, str(ws)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                if res_fallback.returncode != 0:
                    raw_err = res_fallback.stderr.strip() or res.stderr.strip()
                    err_msg = _sanitize_url(raw_err)
                    raise RuntimeError(f"Failed to clone repository '{clean_url}': {err_msg}")

            # Configure git author inside the cloned repo
            subprocess.run(
                ["git", "config", "user.name", "Rallabandi Sai Charan"],
                cwd=ws,
                check=False,
            )
            subprocess.run(
                ["git", "config", "user.email", "saicharanr227@gmail.com"],
                cwd=ws,
                check=False,
            )
            # Create a dedicated working branch for the mission
            subprocess.run(["git", "checkout", "-b", target_branch_name], cwd=ws, check=False)
            logger.info("Successfully cloned %s and created branch %s", clean_url, target_branch_name)
        except Exception as exc:
            logger.error("Error preparing external repo workspace: %s", exc)
            raise
    else:
        # Standalone mission: initialize a clean git repo
        try:
            subprocess.run(["git", "init"], cwd=ws, check=False, capture_output=True)
            subprocess.run(
                ["git", "config", "user.name", "Rallabandi Sai Charan"],
                cwd=ws,
                check=False,
            )
            subprocess.run(
                ["git", "config", "user.email", "saicharanr227@gmail.com"],
                cwd=ws,
                check=False,
            )
        except Exception:
            pass

    return ws


def create_workspace_zip(session_id: str) -> Path:
    """
    Package the completed workspace into a ZIP archive for user download.
    Excludes .git folder to keep zip clean and compact.
    """
    ws = get_mission_workspace(session_id)
    if not ws.exists():
        raise FileNotFoundError(f"Workspace for session {session_id} not found")

    zip_dir = BASE_WORKSPACES_DIR / "archives"
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / f"aegis_solved_{session_id}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(ws):
            dirs[:] = [d for d in dirs if d != ".git"]
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(ws)
                zipf.write(file_path, arcname)

    return zip_path

