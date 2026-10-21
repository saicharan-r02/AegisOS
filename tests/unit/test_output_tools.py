from pathlib import Path

from aegis_os.kernel.context import LargeOutputStore
from aegis_os.tools.output_tools import ReadOutputTool


def test_read_output_tool_returns_requested_line_range(tmp_path: Path) -> None:
    store=LargeOutputStore(tmp_path)
    artifact=store.store("line one\nline two\nline three\nline four",max_tokens=1)
    tool=ReadOutputTool(store)

    result=tool.run({"artifact_id":artifact.reference,"start_line":2,"end_line":3})

    assert result.success
    assert result.output=="line two\nline three"


def test_read_output_tool_rejects_paths_instead_of_artifact_ids(tmp_path: Path) -> None:
    tool=ReadOutputTool(LargeOutputStore(tmp_path))

    result=tool.run({"artifact_id":"../../.env"})

    assert result.success is False
    assert "artifact_id" in (result.error or "")
