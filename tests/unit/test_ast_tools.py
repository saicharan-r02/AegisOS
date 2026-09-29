from pathlib import Path
import pytest
from aegis_os.tools.ast_tools import ASTGrepTool,ASTGrepArgs

@pytest.fixture
def sample_python_project(tmp_path: Path) -> Path:
    """Create a temporary Python project with classes, functions, and nested structures."""
    src=tmp_path/"src"
    src.mkdir()

    file_a=src/"service.py"
    file_a.write_text(
        "class UserService:\n"
        "    def get_user(self, user_id: int):\n"
        "        pass\n"
        "\n"
        "    async def create_user(self, name: str):\n"
        "        pass\n"
        "\n"
        "def standalone_func():\n"
        "    pass\n"
    )

    file_b=src/"models.py"
    file_b.write_text(
        "class UserModel:\n"
        "    pass\n"
    )
    return tmp_path

class TestASTGrepTool:
    def test_find_class_definition(self,sample_python_project: Path) -> None:
        tool=ASTGrepTool()
        result=tool._execute(
            ASTGrepArgs(symbol_name="UserService",search_path=str(sample_python_project))
        )
        assert result.success is True
        assert "UserService" in result.output
        assert "[class]" in result.output
        assert result.metadata["match_count"] >= 1

    def test_find_function_definition(self,sample_python_project: Path) -> None:
        tool=ASTGrepTool()
        result=tool._execute(
            ASTGrepArgs(symbol_name="standalone_func",search_path=str(sample_python_project))
        )
        assert result.success is True
        assert "standalone_func" in result.output
        assert "[function]" in result.output

    def test_find_class_method_with_qualified_name(self,sample_python_project: Path) -> None:
        tool=ASTGrepTool()
        result=tool._execute(
            ASTGrepArgs(symbol_name="get_user",search_path=str(sample_python_project))
        )
        assert result.success is True
        assert "UserService.get_user" in result.output

    def test_filter_by_symbol_type_class(self,sample_python_project: Path) -> None:
        tool=ASTGrepTool()
        result=tool._execute(
            ASTGrepArgs(
                symbol_name="User",
                search_path=str(sample_python_project),
                symbol_type="class",
            )
        )
        assert result.success is True
        assert "UserService" in result.output
        assert "UserModel" in result.output
        assert "[function]" not in result.output

    def test_filter_by_symbol_type_function(self,sample_python_project: Path) -> None:
        tool=ASTGrepTool()
        result=tool._execute(
            ASTGrepArgs(
                symbol_name="User",
                search_path=str(sample_python_project),
                symbol_type="function",
            )
        )
        assert result.success is True
        assert "create_user" in result.output or "get_user" in result.output
        assert "[class]" not in result.output

    def test_nonexistent_symbol_returns_graceful_message(self,sample_python_project: Path) -> None:
        tool=ASTGrepTool()
        result=tool._execute(
            ASTGrepArgs(symbol_name="NonExistentClass",search_path=str(sample_python_project))
        )
        assert result.success is True
        assert "No symbols matching" in result.output
        assert result.metadata["match_count"]==0

    def test_invalid_path_returns_failure(self) -> None:
        tool=ASTGrepTool()
        result=tool._execute(
            ASTGrepArgs(symbol_name="Any",search_path="non_existent_dir_12345")
        )
        assert result.success is False
        assert "Path does not exist" in result.error