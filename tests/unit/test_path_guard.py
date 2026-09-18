"""
Test Suite: Path Traversal Defense
====================================
These tests PROVE that the PathGuard module correctly blocks all known
path traversal attack vectors before any filesystem tool is invoked.

Test philosophy:
    These are SECURITY tests. A single failure means the filesystem
    boundary has been breached. All tests must pass, always.
"""

import pytest
from pathlib import Path

from aegis_os.sandbox.path_guard import PathTraversalError, validate_path


class TestValidPathsAreAccepted:
    """Valid paths within the workspace must resolve cleanly."""

    def test_simple_relative_path(self, tmp_workspace: Path) -> None:
        """A simple filename relative to workspace root is valid."""
        result = validate_path("file.py", tmp_workspace)
        assert result == tmp_workspace / "file.py"

    def test_nested_relative_path(self, tmp_workspace: Path) -> None:
        """A nested relative path within workspace is valid."""
        result = validate_path("src/kernel/state.py", tmp_workspace)
        assert result == tmp_workspace / "src" / "kernel" / "state.py"

    def test_absolute_path_within_workspace(self, tmp_workspace: Path) -> None:
        """An absolute path that resolves inside workspace is valid."""
        target = tmp_workspace / "aegis_os" / "tools" / "base.py"
        result = validate_path(target, tmp_workspace)
        assert result == target

    def test_workspace_root_itself(self, tmp_workspace: Path) -> None:
        """The workspace root itself is a valid path."""
        result = validate_path(".", tmp_workspace)
        assert result == tmp_workspace

    def test_dot_in_middle_of_path_normalizes(self, tmp_workspace: Path) -> None:
        """Paths with '.' in the middle normalize correctly."""
        result = validate_path("src/./tools/base.py", tmp_workspace)
        assert result == tmp_workspace / "src" / "tools" / "base.py"


class TestPathTraversalAttacksAreBlocked:
    """All traversal attack patterns must raise PathTraversalError."""

    def test_simple_double_dot_escape(self, tmp_workspace: Path) -> None:
        """The classic '../../' escape attempt must be blocked."""
        with pytest.raises(PathTraversalError):
            validate_path("../../etc/passwd", tmp_workspace)

    def test_nested_double_dot_escape(self, tmp_workspace: Path) -> None:
        """Nested double-dot traversal attempts must be blocked."""
        with pytest.raises(PathTraversalError):
            validate_path("src/../../../etc/shadow", tmp_workspace)

    def test_absolute_path_outside_workspace(self, tmp_workspace: Path) -> None:
        """An absolute path outside the workspace is a traversal violation."""
        with pytest.raises(PathTraversalError):
            validate_path("/etc/passwd", tmp_workspace)

    def test_windows_style_traversal(self, tmp_workspace: Path) -> None:
        """Windows-style traversal with backslashes must be normalized and blocked."""
        with pytest.raises(PathTraversalError):
            validate_path("..\\..\\Windows\\System32", tmp_workspace)

    def test_traversal_to_parent_only(self, tmp_workspace: Path) -> None:
        """Even a single '../' escaping workspace root must be blocked."""
        with pytest.raises(PathTraversalError):
            validate_path("..", tmp_workspace)

    def test_env_file_access_attempt(self, tmp_workspace: Path) -> None:
        """An attempt to read the .env credentials file above workspace is blocked."""
        with pytest.raises(PathTraversalError):
            validate_path("../../.env", tmp_workspace)


class TestPathTraversalErrorContainsUsefulInfo:
    """The PathTraversalError must contain enough info for debugging."""

    def test_error_message_contains_attempted_path(self, tmp_workspace: Path) -> None:
        """Error message must reference the attempted path."""
        with pytest.raises(PathTraversalError) as exc_info:
            validate_path("../../etc/passwd", tmp_workspace)
        assert "../../etc/passwd" in str(exc_info.value)

    def test_error_message_contains_workspace(self, tmp_workspace: Path) -> None:
        """Error message must reference the workspace root."""
        with pytest.raises(PathTraversalError) as exc_info:
            validate_path("../../etc/passwd", tmp_workspace)
        assert str(tmp_workspace.resolve()) in str(exc_info.value)

    def test_error_is_permission_error_subclass(self, tmp_workspace: Path) -> None:
        """PathTraversalError must be a PermissionError so callers can catch it."""
        with pytest.raises(PermissionError):
            validate_path("../../etc/passwd", tmp_workspace)


class TestWorkspaceRootValidation:
    """Invalid workspace root configurations must be caught early."""

    def test_relative_workspace_root_raises_value_error(self, tmp_path: Path) -> None:
        """A relative workspace_root is a misconfiguration — raise ValueError."""
        with pytest.raises(ValueError, match="absolute path"):
            validate_path("file.py", Path("relative/path"))
