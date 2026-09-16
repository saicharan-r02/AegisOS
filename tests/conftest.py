import pytest
from pathlib import Path
@pytest.fixture
def tmp_workspace(tmp_path:Path)->Path:
    """Create and return an empty workspace directory inside a temporary directory."""
    workspace=tmp_path/"workspace"
    workspace.mkdir()
    return workspace
