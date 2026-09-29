import subprocess
import tempfile
from pathlib import Path
import pytest
from aegis_os.tools.git_tools import GitCommitTool,GitDiffTool,GitStatusTool

@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository for testing."""
    subprocess.run(["git","init",str(tmp_path)],check=True,capture_output=True)
    subprocess.run(
        ["git","config","user.email","test@aegis.ai"],
        cwd=tmp_path,check=True,capture_output=True
    )
    subprocess.run(
        ["git","config","user.name","AegisTest"],
        cwd=tmp_path,check=True,capture_output=True
    )
    initial_file=tmp_path/"README.md"
    initial_file.write_text("# AegisOSTest Repo\n")
    subprocess.run(["git","add","README.md"],cwd=tmp_path,check=True,capture_output=True)
    subprocess.run(
        ["git","commit","-m","chore: initial commit"],
        cwd=tmp_path,check=True,capture_output=True
    )
    return tmp_path

class TestGitStatusTool:
    def test_clean_repo_returns_success(self,git_repo: Path) -> None:
        tool=GitStatusTool()

        from aegis_os.tools.git_tools import GitStatusArgs
        result=tool._execute(GitStatusArgs(cwd=str(git_repo)))

        assert result.success is True
        assert result.output is not None

    def test_dirty_repo_shows_modified(self,git_repo: Path) -> None:
        (git_repo/"README.md").write_text("# Modified\n")
        tool=GitStatusTool()

        from aegis_os.tools.git_tools import GitStatusArgs
        result=tool._execute(GitStatusArgs(cwd=str(git_repo)))

        assert result.success is True
        assert "modified" in result.output.lower() or "README" in result.output

    def test_untracked_file_shows_in_status(self,git_repo: Path) -> None:
        (git_repo/"new_file.py").write_text("# new\n")
        tool=GitStatusTool()

        from aegis_os.tools.git_tools import GitStatusArgs
        result=tool._execute(GitStatusArgs(cwd=str(git_repo)))
        
        assert result.success is True
        assert "new_file.py" in result.output


class TestGitDiffTool:
    def test_no_diff_on_clean_repo(self,git_repo: Path) -> None:
        tool=GitDiffTool()
        from aegis_os.tools.git_tools import GitDiffArgs
        result=tool._execute(GitDiffArgs(cwd=str(git_repo)))
        assert result.success is True

        assert "(no changes)" in result.output or result.output.strip()==""

    def test_diff_shows_modification(self,git_repo: Path) -> None:
        (git_repo/"README.md").write_text("# Changed content\n")
        tool=GitDiffTool()
        from aegis_os.tools.git_tools import GitDiffArgs
        result=tool._execute(GitDiffArgs(cwd=str(git_repo)))
        assert result.success is True
        assert "Changed content" in result.output or "README" in result.output

    def test_staged_diff(self, git_repo: Path) -> None:
        (git_repo/"README.md").write_text("# Staged change\n")
        subprocess.run(["git","add","README.md"],cwd=git_repo,capture_output=True)
        tool=GitDiffTool()
        from aegis_os.tools.git_tools import GitDiffArgs
        result=tool._execute(GitDiffArgs(staged=True,cwd=str(git_repo)))
        assert result.success is True
        assert "Staged change" in result.output or "README" in result.output


class TestGitCommitTool:
    def test_commit_with_add_all(self, git_repo: Path) -> None:
        (git_repo/"README.md").write_text("# After commit\n")
        tool=GitCommitTool()
        from aegis_os.tools.git_tools import GitCommitArgs
        result=tool._execute(GitCommitArgs(message="feat: test commit",add_all=True,cwd=str(git_repo)))
        assert result.success is True
        assert result.metadata is not None
        assert result.metadata["exit_code"]==0

    def test_commit_without_staged_changes_fails(self,git_repo: Path) -> None:
        """Committing with nothing staged should fail gracefully."""
        tool=GitCommitTool()
        from aegis_os.tools.git_tools import GitCommitArgs
        result=tool._execute(GitCommitArgs(message="feat: empty commit",add_all=False,cwd=str(git_repo)))

        assert result.success is False

    def test_commit_message_with_special_chars(self,git_repo: Path) -> None:
        """Commit messages with double-quotes should be escaped, not cause shell injection."""
        (git_repo/"feature.py").write_text("# feature\n")
        subprocess.run(["git","add","feature.py"],cwd=git_repo,capture_output=True)
        tool=GitCommitTool()
        from aegis_os.tools.git_tools import GitCommitArgs
        result=tool._execute(GitCommitArgs(message='feat: add "quoted feature" support',add_all=False,cwd=str(git_repo)))
        assert result.success is True