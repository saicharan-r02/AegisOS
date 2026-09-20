import sys
from pathlib import Path

# Ensure the project root is on sys.path so `aegis_os` is importable
# regardless of whether the package was installed in editable mode.
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create and return an empty workspace directory inside a temporary directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace