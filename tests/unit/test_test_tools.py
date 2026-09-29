from pathlib import Path
import pytest
from aegis_os.tools.test_tools import PytestRunnerTool, PytestRunnerArgs

class TestPytestRunnerTool:
    def test_run_pytest_against_known_passing_test(self) -> None:
        tool=PytestRunnerTool()
        result=tool._execute(
            PytestRunnerArgs(
                target="tests/unit/test_state.py::TestStepRecord::test_step_record_creation",
                timeout_seconds=30.0
            )
        )
        assert result.success is True
        assert result.metadata["passed"]>=1
        assert result.metadata["failed"]==0
        assert result.metadata["errors"]==0
        assert result.metadata["exit_code"]==0

    def test_run_pytest_failing_test_parsed_correctly(self,tmp_path: Path) -> None:
        
        test_file=tmp_path/"test_failing.py"
        test_file.write_text("def test_will_fail():\n    assert 1 == 2\n")

        tool=PytestRunnerTool()
        result=tool._execute(
            PytestRunnerArgs(
                target=str(test_file),
                timeout_seconds=30.0
            )
        )
        assert result.success is False
        assert result.metadata["failed"]==1
        assert len(result.metadata["failing_tests"])>=1
        assert "test_will_fail" in str(result.metadata["failing_tests"]) or "test_failing.py" in str(result.metadata["failing_tests"])
        assert result.error is not None
        assert "1 failed" in result.error

    def test_pytest_timeout_returns_failure(self,tmp_path: Path) -> None:
        test_file=tmp_path/"test_sleep.py"
        test_file.write_text("import time\ndef test_slow():\n    time.sleep(5)\n")

        tool=PytestRunnerTool()
        result=tool._execute(
            PytestRunnerArgs(target=str(test_file),timeout_seconds=0.5)
        )
        assert result.success is False
        assert result.metadata.get("timed_out") is True
        assert "timed out" in result.error