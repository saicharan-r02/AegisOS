"""Canonical workspace path validation and sensitive-file denial."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

_BLOCKED_NAMES = {
    ".git",
    ".aegis",
    ".ssh",
    ".aws",
    ".azure",
    ".gcloud",
    ".kube",
    "credentials",
    "secrets",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
}
_BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".ppk"}


class PathTraversalError(PermissionError):
    """Raised when a path escapes the workspace or targets protected data."""

    def __init__(
        self, requested: str | Path, workspace: Path, reason: str = "outside the workspace"
    ) -> None:
        self.requested = str(requested)
        self.workspace = str(workspace)
        self.reason = reason
        super().__init__(
            f"PATH TRAVERSAL BLOCKED: '{requested}' is {reason}; workspace '{workspace}'. "
            "This operation is not permitted."
        )


def _long_windows_path(path: Path) -> Path:
    """Expand 8.3 aliases on Windows when the target already exists."""
    if os.name != "nt":
        return path

    try:
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return path

        buffer = ctypes.create_unicode_buffer(32768)
        length = windll.kernel32.GetLongPathNameW(str(path), buffer, len(buffer))

        if length and length < len(buffer):
            return Path(buffer.value)
    except (AttributeError, OSError):
        pass

    return path


def _has_sensitive_component(path: Path) -> bool:
    for component in path.parts:
        folded = component.casefold().rstrip(" .")
        if folded in _BLOCKED_NAMES or folded.startswith(".env"):
            return True
        if Path(folded).suffix in _BLOCKED_SUFFIXES:
            return True
    return False


def _is_relative_to_casefold(target: Path, root: Path) -> bool:
    try:
        common = os.path.commonpath((str(root), str(target)))
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(str(root))


def validate_path(path: str | Path, workspace_root: Path) -> Path:
    """Resolve a path and deny traversal, symlink escapes, and credentials.

    On Windows this also expands existing 8.3 aliases and uses case-insensitive
    containment checks. Symlinks and junctions are resolved before containment.
    """
    if not workspace_root.is_absolute():
        raise ValueError(f"workspace_root must be an absolute path. Got: '{workspace_root}'")
    canonical_root = _long_windows_path(workspace_root.resolve())
    normalized_path = str(path).replace("\\", "/")
    requested = Path(normalized_path)
    if _has_sensitive_component(requested):
        raise PathTraversalError(path, canonical_root, "a protected credential or internal path")
    candidate = requested if requested.is_absolute() else canonical_root / requested
    canonical_target = _long_windows_path(candidate.resolve())
    if not _is_relative_to_casefold(canonical_target, canonical_root):
        raise PathTraversalError(path, canonical_root)
    relative = canonical_target.relative_to(canonical_root)
    if _has_sensitive_component(relative):
        raise PathTraversalError(path, canonical_root, "a protected credential or internal path")
    return canonical_target
