import zipfile

from fastapi.testclient import TestClient

from aegis_os.api import app
from aegis_os.workspace.repo_manager import (
    create_workspace_zip,
    prepare_workspace,
)


def test_prepare_workspace_scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "aegis_os.workspace.repo_manager.BASE_WORKSPACES_DIR", tmp_path
    )
    ws = prepare_workspace(session_id="test-scratch-1", repo_url=None)
    assert ws.exists()
    assert (ws / ".git").exists()
    assert ws.name == "test-scratch-1"


def test_create_workspace_zip_and_download(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "aegis_os.workspace.repo_manager.BASE_WORKSPACES_DIR", tmp_path
    )
    session_id = "test-pkg-1"
    ws = prepare_workspace(session_id=session_id, repo_url=None)

    # Add a sample project file
    sample_file = ws / "calculator.py"
    sample_file.write_text("def add(a, b): return a + b\n", encoding="utf-8")

    zip_path = create_workspace_zip(session_id)
    assert zip_path.exists()
    assert zip_path.suffix == ".zip"

    # Verify zip content
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert "calculator.py" in namelist
        assert not any(n.startswith(".git") for n in namelist)

    # Test download endpoint via test client
    client = TestClient(app)
    resp = client.get(f"/api/missions/{session_id}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
