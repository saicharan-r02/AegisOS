from pathlib import Path

from aegis_os.sandbox.docker_sandbox import DockerSandbox
from aegis_os.sandbox.policy import CommandPolicy


def test_docker_sandbox_snapshot_excludes_secrets_git_and_symlinks(tmp_path: Path) -> None:
    workspace=tmp_path/"workspace"
    workspace.mkdir()
    (workspace/"main.py").write_text("print('ok')\n",encoding="utf-8")
    (workspace/".env").write_text("API_KEY=not-for-container\n",encoding="utf-8")
    (workspace/".git").mkdir()
    (workspace/".git"/"config").write_text("secret remote",encoding="utf-8")
    (workspace/".aegis").mkdir()
    (workspace/".aegis"/"checkpoint.db").write_text("private state",encoding="utf-8")
    outside=tmp_path/"outside.txt"
    outside.write_text("outside",encoding="utf-8")
    try:
        (workspace/"linked.txt").symlink_to(outside)
    except (OSError,NotImplementedError):
        pass
    sandbox=DockerSandbox(workspace)
    snapshot=tmp_path/"snapshot"

    sandbox._copy_workspace(snapshot)

    assert (snapshot/"main.py").read_text(encoding="utf-8")=="print('ok')\n"
    assert not (snapshot/".env").exists()
    assert not (snapshot/".git").exists()
    assert not (snapshot/".aegis").exists()
    assert not (snapshot/"linked.txt").exists()


def test_docker_sandbox_fails_closed_when_docker_is_missing(tmp_path: Path,monkeypatch) -> None:
    monkeypatch.setattr("aegis_os.sandbox.docker_sandbox.shutil.which",lambda _:None)
    sandbox=DockerSandbox(tmp_path,policy=CommandPolicy())

    result=sandbox.execute_command("python -m pytest tests",quota=None)

    assert result.success is False
    assert result.exit_code==127
    assert "Docker CLI is not installed" in result.stderr
