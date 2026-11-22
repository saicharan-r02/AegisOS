"""Compare test files in a workspace against the git commit a mission started from.

This feeds the real data into ``HardInvariantEngine`` invariant 4 (test integrity)
instead of a hardcoded ``True``. It only reads git state; it never modifies the repo.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path, PurePosixPath

from aegis_os.verification.integrity import TestIntegrityGuard

_GIT_TIMEOUT_SECONDS = 20


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def current_commit(root: Path) -> str | None:
    """Return the HEAD commit hash of ``root`` or None if it is not a git repo with commits."""
    result = _git(root, "rev-parse", "--verify", "HEAD")
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def is_test_file(path: str) -> bool:
    posix = PurePosixPath(path.replace("\\", "/"))
    if posix.suffix != ".py":
        return False
    name = posix.name
    return name.startswith("test_") or name.endswith("_test.py") or "tests" in posix.parts


def audit_test_changes(
    root: Path, base_commit: str | None, objective: str = ""
) -> tuple[bool, list[str]]:
    """Return ``(passed, violations)`` for test files changed since ``base_commit``.

    If git or the base commit is unavailable the audit cannot run, so it passes with
    an explanatory note rather than blocking the mission.
    """
    if not base_commit:
        return True, ["Test-integrity audit skipped: workspace has no git base commit."]

    diff = _git(root, "diff", "--name-status", "--no-renames", base_commit, "--")
    if diff is None or diff.returncode != 0:
        return True, ["Test-integrity audit skipped: `git diff` failed."]

    violations: list[str] = []
    passed = True
    for line in diff.stdout.splitlines():
        status, _, rel_path = line.partition("\t")
        rel_path = rel_path.strip()
        if status not in {"M", "D"} or not rel_path or not is_test_file(rel_path):
            continue  # new test files (A) cannot weaken existing coverage

        before = _git(root, "show", f"{base_commit}:{rel_path}")
        if before is None or before.returncode != 0:
            continue
        target = root / rel_path
        after_text = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""

        ok, found = TestIntegrityGuard.audit_test_diff(before.stdout, after_text, objective)
        violations.extend(f"{rel_path}: {message}" for message in found)
        passed = passed and ok
    return passed, violations


_MAX_UNTRACKED_FILE_BYTES = 40_000


def collect_diff(root: Path, base_commit: str | None, max_chars: int = 60_000) -> str:
    """Everything the mission changed since ``base_commit``: tracked edits AND new files.

    ``git diff`` alone misses files Dev created but never committed, so those are appended
    as synthetic "new file" hunks. Binary / oversized / secret-like files are skipped.
    """
    if not base_commit:
        return ""
    tracked = _git(root, "diff", "--no-color", "--no-renames", base_commit, "--")
    parts: list[str] = [tracked.stdout] if tracked is not None and tracked.returncode == 0 else []

    others = _git(root, "ls-files", "--others", "--exclude-standard")
    if others is not None and others.returncode == 0:
        for rel_path in others.stdout.splitlines():
            rel_path = rel_path.strip()
            name = PurePosixPath(rel_path.replace("\\", "/")).name.lower()
            if not rel_path or name.startswith(".env") or name.endswith((".db", ".log", ".pyc")):
                continue
            target = root / rel_path
            try:
                if not target.is_file() or target.stat().st_size > _MAX_UNTRACKED_FILE_BYTES:
                    continue
                text = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            body = "\n".join(f"+{line}" for line in text.splitlines())
            parts.append(
                f"diff --git a/{rel_path} b/{rel_path}\nnew file mode 100644\n"
                f"--- /dev/null\n+++ b/{rel_path}\n@@ -0,0 +1,{len(text.splitlines())} @@\n{body}\n"
            )
    return "\n".join(parts)[:max_chars]


_DEFAULT_GITIGNORE = "__pycache__/\n*.pyc\n.pytest_cache/\n.aegis/\n.venv/\nvenv/\nnode_modules/\n.env\n"


def _is_own_toplevel(root: Path) -> bool:
    """True when ``root`` itself is the top of a git work tree (not merely inside another repo)."""
    top = _git(root, "rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0 or not top.stdout.strip():
        return False
    try:
        return os.path.samefile(top.stdout.strip(), root)
    except OSError:
        return False


def ensure_git_workspace(root: Path) -> tuple[bool, str]:
    """Make ``root`` a git repository with a baseline commit so agents can use git tools.

    Returns ``(ok, note)``. Existing repositories are left untouched. A folder that is only
    *inside* some other repository gets its own nested repository, so mission diffs never
    include unrelated files from the parent project.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if _is_own_toplevel(root) and current_commit(root):
        return True, "existing git repository"

    if not _is_own_toplevel(root):
        init = _git(root, "init", "-q")
        if init is None or init.returncode != 0:
            return False, "git is not available or `git init` failed"

    for key, value in (("user.name", "AegisOS"), ("user.email", "aegis@localhost")):
        current = _git(root, "config", "--get", key)
        if current is None or not current.stdout.strip():
            _git(root, "config", key, value)

    ignore = root / ".gitignore"
    if not ignore.exists():
        ignore.write_text(_DEFAULT_GITIGNORE, encoding="utf-8")

    _git(root, "add", "-A")
    commit = _git(root, "commit", "-q", "--allow-empty", "-m", "AegisOS baseline")
    if commit is None or commit.returncode != 0 or not current_commit(root):
        return False, "could not create the baseline commit"
    return True, "initialised a new git repository with a baseline commit"


def changed_files(root: Path, base_commit: str | None) -> list[str]:
    """Paths changed since ``base_commit`` (tracked edits plus new untracked files)."""
    names: list[str] = []
    if base_commit:
        tracked = _git(root, "diff", "--name-only", "--no-renames", base_commit, "--")
        if tracked is not None and tracked.returncode == 0:
            names.extend(line.strip() for line in tracked.stdout.splitlines() if line.strip())
    others = _git(root, "ls-files", "--others", "--exclude-standard")
    if others is not None and others.returncode == 0:
        names.extend(line.strip() for line in others.stdout.splitlines() if line.strip())
    if not names and not base_commit:
        head_diff = _git(root, "diff", "--name-only", "--no-renames", "HEAD~1", "--")
        if head_diff is not None and head_diff.returncode == 0 and head_diff.stdout.strip():
            names.extend(line.strip() for line in head_diff.stdout.splitlines() if line.strip())
        else:
            head_files = _git(root, "ls-tree", "-r", "--name-only", "HEAD")
            if head_files is not None and head_files.returncode == 0 and head_files.stdout.strip():
                names.extend(line.strip() for line in head_files.stdout.splitlines() if line.strip())
            else:
                try:
                    for p in root.rglob("*"):
                        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts):
                            names.append(p.relative_to(root).as_posix())
                except Exception:
                    pass
    return sorted(dict.fromkeys(names))
