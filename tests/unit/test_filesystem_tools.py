from pathlib import Path
import pytest
from aegis_os.tools.filesystem_tools import (
    FindFilesTool,
    GrepSearchTool,
    ListDirTool,
    ReadFileTool,
    ReplaceInFileTool,
    WriteFileTool,
)

class TestReadFileTool:
    """ReadFileTool tests for line numbering, slicing, and security."""
    def test_read_entire_file_with_line_numbers(self,tmp_workspace: Path) -> None:
        file_path=tmp_workspace/"sample.txt"
        file_path.write_text("first line\nsecond line\nthird line",encoding="utf-8")
        tool=ReadFileTool(workspace_root=tmp_workspace)
        result=tool.run({"path": "sample.txt"})
        assert result.success is True
        assert result.error is None
        lines=result.output.splitlines()
        assert len(lines)==3
        assert "   1: first line" in lines[0]
        assert "   2: second line" in lines[1]
        assert "   3: third line" in lines[2]
        assert result.metadata["total_lines"]==3
        assert result.metadata["lines_returned"]==3

    def test_read_line_range_slice(self,tmp_workspace: Path) -> None:
        file_path=tmp_workspace/"numbers.txt"
        file_path.write_text("\n".join(f"line {i}" for i in range(1,11)),encoding="utf-8")
        tool=ReadFileTool(workspace_root=tmp_workspace)
        result=tool.run({"path": "numbers.txt","start_line":3,"end_line":5})
        assert result.success is True
        lines = result.output.splitlines()
        assert len(lines)==3
        assert "   3: line 3" in lines[0]
        assert "   4: line 4" in lines[1]
        assert "   5: line 5" in lines[2]
        assert result.metadata["start_line"]==3
        assert result.metadata["end_line"]==5

    def test_nonexistent_file_returns_failure(self,tmp_workspace: Path) -> None:
        tool=ReadFileTool(workspace_root=tmp_workspace)
        result=tool.run({"path": "does_not_exist.py"})
        assert result.success is False
        assert result.error is not None
        assert "File not found" in result.error

    def test_reading_directory_returns_failure(self,tmp_workspace: Path) -> None:
        sub_dir=tmp_workspace / "subdir"
        sub_dir.mkdir()
        tool=ReadFileTool(workspace_root=tmp_workspace)
        result=tool.run({"path": "subdir"})
        assert result.success is False
        assert "not a file" in (result.error or "")

    def test_path_traversal_blocked(self, tmp_workspace: Path) -> None:
        tool=ReadFileTool(workspace_root=tmp_workspace)
        result=tool.run({"path": "../../etc/passwd"})
        assert result.success is False
        assert result.error is not None
        assert "PATH TRAVERSAL BLOCKED" in result.error


class TestWriteFileTool:
    """WriteFileTool tests for atomic writing, directory creation, and security."""
    def test_write_new_file_and_verify(self,tmp_workspace: Path) -> None:
        tool=WriteFileTool(workspace_root=tmp_workspace)
        content="print('Hello, AegisOS!')\n"
        result=tool.run({"path": "src/main.py","content": content})

        assert result.success is True
        created_file=tmp_workspace/"src"/"main.py"
        assert created_file.exists()
        assert created_file.read_text(encoding="utf-8")==content
        assert result.metadata["line_count"]==2

    def test_overwrite_existing_file(self, tmp_workspace: Path) -> None:
        file_path=tmp_workspace/"config.json"
        file_path.write_text('{"version": 1}',encoding="utf-8")

        tool=WriteFileTool(workspace_root=tmp_workspace)
        result=tool.run({"path": "config.json","content": '{"version": 2}'})

        assert result.success is True
        assert file_path.read_text(encoding="utf-8")=='{"version": 2}'

    def test_create_dirs_false_fails_when_dir_missing(self,tmp_workspace: Path) -> None:
        tool=WriteFileTool(workspace_root=tmp_workspace)
        result=tool.run({
            "path": "missing_dir/output.txt",
            "content": "test",
            "create_dirs": False
        })

        assert result.success is False
        assert "does not exist" in (result.error or "")

    def test_write_path_traversal_blocked(self,tmp_workspace: Path) -> None:
        tool=WriteFileTool(workspace_root=tmp_workspace)
        result=tool.run({"path": "../../../evil.sh","content": "rm -rf /"})

        assert result.success is False
        assert result.error is not None
        assert "PATH TRAVERSAL BLOCKED" in result.error

class TestListDirTool:
    """ListDirTool tests for directory listing, hidden files, and security."""

    def test_list_directory_contents(self,tmp_workspace: Path) -> None:
        (tmp_workspace/"file1.py").write_text("print(1)",encoding="utf-8")
        (tmp_workspace/"file2.md").write_text("# Doc",encoding="utf-8")
        (tmp_workspace/"subfolder").mkdir()

        tool=ListDirTool(workspace_root=tmp_workspace)
        result=tool.run({"path": "."})

        assert result.success is True
        assert "subfolder/" in result.output
        assert "file1.py" in result.output
        assert "file2.md" in result.output
        assert result.metadata["file_count"]==2
        assert result.metadata["dir_count"]==1

    def test_hidden_files_filtering(self,tmp_workspace: Path) -> None:
        (tmp_workspace/".env").write_text("SECRET=123",encoding="utf-8")
        (tmp_workspace/"normal.txt").write_text("normal",encoding="utf-8")

        tool=ListDirTool(workspace_root=tmp_workspace)
        result_default=tool.run({"path": "."})
        assert ".env" not in result_default.output
        assert "normal.txt" in result_default.output

        # When show_hidden is True
        result_hidden=tool.run({"path": ".","show_hidden": True})
        assert ".env" in result_hidden.output
        assert "normal.txt" in result_hidden.output

    def test_list_nonexistent_directory_fails(self,tmp_workspace: Path) -> None:
        tool=ListDirTool(workspace_root=tmp_workspace)
        result=tool.run({"path": "non_existent_folder"})

        assert result.success is False
        assert "Directory not found" in (result.error or "")

    def test_list_path_traversal_blocked(self,tmp_workspace: Path) -> None:
        tool=ListDirTool(workspace_root=tmp_workspace)
        result=tool.run({"path": "../../"})

        assert result.success is False
        assert result.error is not None
        assert "PATH TRAVERSAL BLOCKED" in result.error


class TestReplaceInFileTool:
    """Unit tests for surgical code editing via ReplaceInFileTool."""

    def test_replace_single_occurrence_success(self, tmp_workspace: Path) -> None:
        file_path = tmp_workspace / "code.py"
        file_path.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

        tool = ReplaceInFileTool(workspace_root=tmp_workspace)
        result = tool.run({
            "path": "code.py",
            "target_content": "return a - b",
            "replacement_content": "return a + b",
        })

        assert result.success is True
        assert file_path.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"

    def test_replace_target_not_found_fails(self, tmp_workspace: Path) -> None:
        file_path = tmp_workspace / "code.py"
        file_path.write_text("def hello(): pass\n", encoding="utf-8")

        tool = ReplaceInFileTool(workspace_root=tmp_workspace)
        result = tool.run({
            "path": "code.py",
            "target_content": "def goodbye(): pass",
            "replacement_content": "def bye(): pass",
        })

        assert result.success is False
        assert "Target content was not found" in (result.error or "")

    def test_replace_ambiguous_multiple_occurrences_fails(self, tmp_workspace: Path) -> None:
        file_path = tmp_workspace / "code.py"
        file_path.write_text("value = 1\nvalue = 1\n", encoding="utf-8")

        tool = ReplaceInFileTool(workspace_root=tmp_workspace)
        result = tool.run({
            "path": "code.py",
            "target_content": "value = 1",
            "replacement_content": "value = 2",
        })

        assert result.success is False
        assert "appears 2 times" in (result.error or "")

    def test_replace_all_occurrences_success(self, tmp_workspace: Path) -> None:
        file_path = tmp_workspace / "code.py"
        file_path.write_text("value = 1\nvalue = 1\n", encoding="utf-8")

        tool = ReplaceInFileTool(workspace_root=tmp_workspace)
        result = tool.run({
            "path": "code.py",
            "target_content": "value = 1",
            "replacement_content": "value = 2",
            "replace_all": True,
        })

        assert result.success is True
        assert file_path.read_text(encoding="utf-8") == "value = 2\nvalue = 2\n"


class TestGrepSearchTool:
    """Unit tests for workspace-wide text and regex search."""

    def test_grep_finds_matching_lines(self, tmp_workspace: Path) -> None:
        (tmp_workspace / "module_a.py").write_text("def target_func(): pass\n", encoding="utf-8")
        (tmp_workspace / "module_b.py").write_text("import os\n# calls target_func\n", encoding="utf-8")

        tool = GrepSearchTool(workspace_root=tmp_workspace)
        result = tool.run({"query": "target_func"})

        assert result.success is True
        assert "module_a.py:1" in result.output
        assert "module_b.py:2" in result.output

    def test_grep_regex_search(self, tmp_workspace: Path) -> None:
        (tmp_workspace / "data.py").write_text("port = 8080\nport = 9000\n", encoding="utf-8")

        tool = GrepSearchTool(workspace_root=tmp_workspace)
        result = tool.run({"query": r"port\s*=\s*\d+", "is_regex": True})

        assert result.success is True
        assert "8080" in result.output
        assert "9000" in result.output

    def test_grep_no_matches_returns_empty(self, tmp_workspace: Path) -> None:
        (tmp_workspace / "test.py").write_text("x = 1\n", encoding="utf-8")

        tool = GrepSearchTool(workspace_root=tmp_workspace)
        result = tool.run({"query": "non_existent_symbol"})

        assert result.success is True
        assert "No matches found" in result.output


class TestFindFilesTool:
    """Unit tests for glob file searching."""

    def test_find_files_by_pattern(self, tmp_workspace: Path) -> None:
        (tmp_workspace / "src").mkdir()
        (tmp_workspace / "src" / "app.py").write_text("# main", encoding="utf-8")
        (tmp_workspace / "src" / "config.json").write_text("{}", encoding="utf-8")

        tool = FindFilesTool(workspace_root=tmp_workspace)
        result = tool.run({"pattern": "*.py"})

        assert result.success is True
        assert "app.py" in result.output
        assert "config.json" not in result.output

    def test_find_files_no_match(self, tmp_workspace: Path) -> None:
        tool = FindFilesTool(workspace_root=tmp_workspace)
        result = tool.run({"pattern": "*.rust"})

        assert result.success is True
        assert "No files matching" in result.output