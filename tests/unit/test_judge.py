from unittest.mock import MagicMock, patch

from aegis_os.sandbox.base import CommandResult
from eval.dataset import get_golden_dataset
from eval.engine import AegisJudge
from eval.models import BenchmarkReport, BenchmarkTask, JudgeResult


def test_golden_dataset_structure():
    dataset = get_golden_dataset()
    assert len(dataset) > 0
    for task in dataset:
        assert isinstance(task, BenchmarkTask)
        assert len(task.id) > 0 and isinstance(task.id, str)
        assert task.verification_script != ""

def test_benchmark_report_metrics():
    report = BenchmarkReport()
    assert report.total_tasks == 0
    assert report.passed_tasks == 0
    assert report.pass_rate == 0.0

    report.results.append(JudgeResult(task_id="t1", passed=True))
    report.results.append(JudgeResult(task_id="t2", passed=False))

    assert report.total_tasks == 2
    assert report.passed_tasks == 1
    assert report.pass_rate == 50.0

@patch("eval.engine.MissionOrchestrator")
@patch("subprocess.run")
def test_aegis_judge_execution(mock_run, mock_orchestrator):
    mock_orchestrator_instance = MagicMock()
    mock_summary = MagicMock()
    mock_summary.session_id = "test-session"
    mock_summary.repair_history = []
    mock_summary.tokens_used = 123
    mock_summary.cost_used_usd = 0.01
    mock_summary.error = None
    mock_orchestrator_instance.execute_mission.return_value = mock_summary
    mock_orchestrator.return_value = mock_orchestrator_instance

    mock_run_result = MagicMock()
    mock_run_result.returncode = 0
    mock_run_result.stdout = "verified"
    mock_run_result.stderr = ""
    mock_run.return_value = mock_run_result

    task = BenchmarkTask(
        id="test-01",
        goal="Do nothing",
        verification_script="print('ok')"
    )

    judge = AegisJudge(unsafe_local=True)
    result = judge.run_task(task)

    assert result.task_id == "test-01"
    assert result.passed is True
    assert result.pass_at_1 is True
    assert result.repair_cycles == 0
    assert result.total_tokens == 123
    assert result.cost_usd == 0.01
    assert result.error_message is None
    assert result.trace == []



@patch("eval.engine.MissionOrchestrator")
@patch("eval.engine.SubprocessSandbox.execute_command")
def test_aegis_judge_retains_verifier_stdout_on_failure(mock_exec, mock_orchestrator):
    mock_summary=MagicMock()
    mock_summary.session_id="session"
    mock_summary.repair_history=[]
    mock_summary.tokens_used=10
    mock_summary.cost_used_usd=0.02
    mock_summary.error=None
    mock_orchestrator.return_value.execute_mission.return_value=mock_summary
    mock_exec.return_value=CommandResult(
        exit_code=1,
        stdout="AssertionError: expected sum",
        stderr="",
        timed_out=False,
        output_truncated=False,
    )
    task=BenchmarkTask(id="test-02",goal="Fix sum",verification_script="assert False")

    result=AegisJudge(unsafe_local=True).run_task(task)

    assert result.passed is False
    assert "AssertionError: expected sum" in (result.error_message or "")
    assert result.total_tokens==10
    assert result.cost_usd==0.02
