import pytest
from eval.models import BenchmarkTask, JudgeResult, BenchmarkReport
from eval.dataset import get_golden_dataset
from eval.engine import AegisJudge
from unittest.mock import patch, MagicMock

def test_golden_dataset_structure():
    dataset = get_golden_dataset()
    assert len(dataset) > 0
    for task in dataset:
        assert isinstance(task, BenchmarkTask)
        assert task.id.startswith("easy-")
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
    mock_orchestrator_instance.execute_mission.return_value = mock_summary
    mock_orchestrator.return_value = mock_orchestrator_instance
    
    mock_run_result = MagicMock()
    mock_run_result.returncode = 0
    mock_run.return_value = mock_run_result
    
    task = BenchmarkTask(
        id="test-01",
        goal="Do nothing",
        verification_script="print('ok')"
    )
    
    judge = AegisJudge()
    result = judge.run_task(task)
    
    assert result.task_id == "test-01"
    assert result.passed is True
    assert result.pass_at_1 is True
    assert result.repair_cycles == 0
    assert result.error_message is None
