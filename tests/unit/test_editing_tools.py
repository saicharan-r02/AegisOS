from pathlib import Path

from aegis_os.tools.codebase_tools import FileOutlineTool, FindReferencesTool
from aegis_os.tools.editing_tools import ApplyPatchTool, apply_unified_diff
from aegis_os.tools.filesystem_tools import ReplaceInFileTool, WriteFileTool


def test_apply_patch_rejects_context_mismatch() -> None:
    source="def add(a, b):\n    return a + b\n"
    patch="--- a/math.py\n+++ b/math.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"

    try:
        apply_unified_diff(source,patch)
    except ValueError as exc:
        assert "did not match" in str(exc)
    else:
        raise AssertionError("A mismatched patch must be rejected.")


def test_apply_patch_tool_applies_hunks_and_checks_python_syntax(tmp_path: Path) -> None:
    target=tmp_path/"math.py"
    target.write_text("def add(a, b):\n    return a - b\n",encoding="utf-8")
    patch="--- a/math.py\n+++ b/math.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"

    result=ApplyPatchTool(tmp_path).run({"file_path":"math.py","patch":patch})

    assert result.success
    assert "syntax validation passed" in result.output
    assert target.read_text(encoding="utf-8").endswith("return a + b\n")


def test_apply_patch_tool_returns_syntax_diagnostics(tmp_path: Path) -> None:
    target=tmp_path/"module.py"
    target.write_text("value = 1\n",encoding="utf-8")
    patch="--- a/module.py\n+++ b/module.py\n@@ -1 +1 @@\n-value = 1\n+def broken(:\n"

    result=ApplyPatchTool(tmp_path).run({"file_path":"module.py","patch":patch})

    assert result.success is False
    assert "SyntaxError" in result.output
    assert "SyntaxError" in result.error


def test_replace_in_file_matches_whitespace_tolerantly_and_checks_syntax(tmp_path: Path) -> None:
    target=tmp_path/"module.py"
    target.write_text("def add(a, b):\n    return a + b\n",encoding="utf-8")
    tool=ReplaceInFileTool(tmp_path)

    result=tool.run({
        "path":"module.py",
        "target_content":"def  add(a, b): return   a + b",
        "replacement_content":"def add(a, b):\n    return a - b",
    })

    assert result.success
    assert "return a - b" in target.read_text(encoding="utf-8")
    assert result.metadata["syntax_diagnostics"]==[]


def test_replace_in_file_rejects_ambiguous_whitespace_matches(tmp_path: Path) -> None:
    target=tmp_path/"module.py"
    target.write_text("return a + b\nreturn a + b\n",encoding="utf-8")

    result=ReplaceInFileTool(tmp_path).run({
        "path":"module.py",
        "target_content":"return a + b",
        "replacement_content":"return a - b",
    })

    assert result.success is False
    assert "appears 2 times" in (result.error or "")


def test_write_file_returns_syntax_diagnostics_after_edit(tmp_path: Path) -> None:
    result=WriteFileTool(tmp_path).run({"path":"broken.py","content":"def broken(:\n    pass\n"})

    assert result.success is False
    assert "SyntaxError" in result.output
    assert (tmp_path/"broken.py").is_file()


def test_file_outline_supports_python_and_typescript(tmp_path: Path) -> None:
    (tmp_path/"module.py").write_text("class Thing:\n    def work(self):\n        pass\n",encoding="utf-8")
    (tmp_path/"module.ts").write_text("export function compute() {}\nexport class Widget {}\n",encoding="utf-8")
    tool=FileOutlineTool(tmp_path)

    python_result=tool.run({"path":"module.py"})
    ts_result=tool.run({"path":"module.ts"})

    assert "ClassDef Thing" in python_result.output
    assert "FunctionDef work" in python_result.output
    assert "function compute" in ts_result.output
    assert "class Widget" in ts_result.output


def test_find_references_reports_file_and_line(tmp_path: Path) -> None:
    (tmp_path/"src").mkdir()
    (tmp_path/"src"/"one.py").write_text("value = parse_item(data)\n",encoding="utf-8")
    (tmp_path/"src"/"two.ts").write_text("const result = parse_item(input);\n",encoding="utf-8")

    result=FindReferencesTool(tmp_path).run({"symbol":"parse_item","path":"src"})

    assert result.success
    assert "one.py:1" in result.output
    assert "two.ts:1" in result.output
