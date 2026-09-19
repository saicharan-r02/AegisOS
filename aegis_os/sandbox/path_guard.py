from pathlib import Path
class PathTraversalError(PermissionError):
    """
    Raised when a requested path resolves to a location outside the
    allowed workspace root. This is a security violation — not a user error.
    """
    def __init__(self, requested: str | Path, workspace: Path) -> None:
        self.requested = str(requested)
        self.workspace = str(workspace)
        super().__init__(
            f"PATH TRAVERSAL BLOCKED: '{requested}' resolves outside "
            f"workspace '{workspace}'. This operation is not permitted.")

def validate_path(path: str | Path, workspace_root: Path) -> Path:
    """
    Validate and canonicalize a path relative to the workspace root.
    The workspace_root itself is first canonicalized. Then the requested
    path is resolved relative to the workspace root if it is not absolute,
    or canonicalized directly if it is absolute. The final canonical path
    must be a sub-path of (or equal to) the workspace root.
    Args:
        path:             The path string or Path object as provided by the caller.
        workspace_root:   The absolute root directory all file access is confined to.
    Returns:
        The fully resolved, safe, absolute Path object.
    Raises:
        PathTraversalError: If the resolved path escapes the workspace.
        ValueError:          If workspace_root is not an absolute path.
    """
    if not workspace_root.is_absolute():
        raise ValueError(
            f"workspace_root must be an absolute path. Got: '{workspace_root}'")
    # Canonicalize the workspace root (resolve any symlinks, .., etc.)
    canonical_root = workspace_root.resolve()
    # Convert input to Path object
    target = Path(path)
    # Resolve target: if relative, interpret relative to workspace_root
    if target.is_absolute():
        canonical_target = target.resolve()
    else:
        canonical_target = (canonical_root / target).resolve()
    # The security check: canonical_target must be INSIDE canonical_root
    try:
        canonical_target.relative_to(canonical_root)
    except ValueError:
        raise PathTraversalError(path, canonical_root)
    return canonical_target