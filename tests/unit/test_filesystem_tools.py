from pathlib import Path
import pytest
from aegis_os.tools.filesystem_tools import ListDirTool,ReadFileTool,WriteFileTool

class TestReadFileTool:
    """ReadFileTool tests for line numbering, slicing, and security."""
    def test_read_entire_file_with_line_numbers(self, tmp_workspace: Path) -> None:
        file_path = tmp_workspace / "sample.txt"
        file_path.write_text("first line\nsecond line\nthird line", encoding="utf-8")
        tool = ReadFileTool(workspace_root=tmp_workspace)
        result = tool.run({"path": "sample.txt"})
        assert result.success is True
        assert result.error is None
        lines = result.output.splitlines()
        assert len(lines) == 3
        assert "   1: first line" in lines[0]
        assert "   2: second line" in lines[1]
        assert "   3: third line" in lines[2]
        assert result.metadata["total_lines"] == 3
        assert result.metadata["lines_returned"] == 3

    def test_read_line_range_slice(self, tmp_workspace: Path) -> None:
        file_path = tmp_workspace / "numbers.txt"
        file_path.write_text("\n".join(f"line {i}" for i in range(1, 11)), encoding="utf-8")
        tool = ReadFileTool(workspace_root=tmp_workspace)
        result = tool.run({"path": "numbers.txt", "start_line": 3, "end_line": 5})
        assert result.success is True
        lines = result.output.splitlines()
        assert len(lines) == 3
        assert "   3: line 3" in lines[0]
        assert "   4: line 4" in lines[1]
        assert "   5: line 5" in lines[2]
        assert result.metadata["start_line"] == 3
        assert result.metadata["end_line"] == 5

    def test_nonexistent_file_returns_failure(self, tmp_workspace: Path) -> None:
        tool = ReadFileTool(workspace_root=tmp_workspace)
        result = tool.run({"path": "does_not_exist.py"})
        assert result.success is False
        assert result.error is not None
        assert "File not found" in result.error

    def test_reading_directory_returns_failure(self, tmp_workspace: Path) -> None:
        sub_dir = tmp_workspace / "subdir"
        sub_dir.mkdir()
        tool = ReadFileTool(workspace_root=tmp_workspace)
        result = tool.run({"path": "subdir"})
        assert result.success is False
        assert "not a file" in (result.error or "")

    def test_path_traversal_blocked(self, tmp_workspace: Path) -> None:
        tool = ReadFileTool(workspace_root=tmp_workspace)
        result = tool.run({"path": "../../etc/passwd"})
        assert result.success is False
        assert result.error is not None
        assert "PATH TRAVERSAL BLOCKED" in result.error


class TestWriteFileTool:
    """WriteFileTool tests for atomic writing, directory creation, and security."""
    def test_write_new_file_and_verify(self, tmp_workspace: Path) -> None:
        tool = WriteFileTool(workspace_root=tmp_workspace)
        content = "print('Hello, AegisOS!')\n"
        result = tool.run({"path": "src/main.py", "content": content})

        assert result.success is True
        created_file = tmp_workspace / "src" / "main.py"
        assert created_file.exists()
        assert created_file.read_text(encoding="utf-8") == content
        assert result.metadata["line_count"] == 2

    def test_overwrite_existing_file(self, tmp_workspace: Path) -> None:
        file_path = tmp_workspace / "config.json"
        file_path.write_text('{"version": 1}', encoding="utf-8")

        tool = WriteFileTool(workspace_root=tmp_workspace)
        result = tool.run({"path": "config.json", "content": '{"version": 2}'})

        assert result.success is True
        assert file_path.read_text(encoding="utf-8") == '{"version": 2}'

    def test_create_dirs_false_fails_when_dir_missing(self, tmp_workspace: Path) -> None:
        tool = WriteFileTool(workspace_root=tmp_workspace)
        result = tool.run({
            "path": "missing_dir/output.txt",
            "content": "test",
            "create_dirs": False,
        })

        assert result.success is False
        assert "does not exist" in (result.error or "")

    def test_write_path_traversal_blocked(self, tmp_workspace: Path) -> None:
        tool = WriteFileTool(workspace_root=tmp_workspace)
        result = tool.run({"path": "../../../evil.sh", "content": "rm -rf /"})

        assert result.success is False
        assert result.error is not None
        assert "PATH TRAVERSAL BLOCKED" in result.error


class TestListDirTool:
    """ListDirTool tests for directory listing, hidden files, and security."""

    def test_list_directory_contents(self, tmp_workspace: Path) -> None:
        (tmp_workspace / "file1.py").write_text("print(1)", encoding="utf-8")
        (tmp_workspace / "file2.md").write_text("# Doc", encoding="utf-8")
        (tmp_workspace / "subfolder").mkdir()

        tool = ListDirTool(workspace_root=tmp_workspace)
        result = tool.run({"path": "."})

        assert result.success is True
        assert "subfolder/" in result.output
        assert "file1.py" in result.output
        assert "file2.md" in result.output
        assert result.metadata["file_count"] == 2
        assert result.metadata["dir_count"] == 1

    def test_hidden_files_filtering(self, tmp_workspace: Path) -> None:
        (tmp_workspace / ".env").write_text("SECRET=123", encoding="utf-8")
        (tmp_workspace / "normal.txt").write_text("normal", encoding="utf-8")

        tool = ListDirTool(workspace_root=tmp_workspace)

        # By default, show_hidden is False
        result_default = tool.run({"path": "."})
        assert ".env" not in result_default.output
        assert "normal.txt" in result_default.output

        # When show_hidden is True
        result_hidden = tool.run({"path": ".", "show_hidden": True})
        assert ".env" in result_hidden.output
        assert "normal.txt" in result_hidden.output

    def test_list_nonexistent_directory_fails(self, tmp_workspace: Path) -> None:
        tool = ListDirTool(workspace_root=tmp_workspace)
        result = tool.run({"path": "non_existent_folder"})

        assert result.success is False
        assert "Directory not found" in (result.error or "")

    def test_list_path_traversal_blocked(self, tmp_workspace: Path) -> None:
        tool = ListDirTool(workspace_root=tmp_workspace)
        result = tool.run({"path": "../../"})

        assert result.success is False
        assert result.error is not None
        assert "PATH TRAVERSAL BLOCKED" in result.error
