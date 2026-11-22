"""Reviewer + test-integrity gates are REAL (not hardcoded True) inside the adaptive mission loop."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aegis_os.agents.cto.agent import AegisCTO, MissionPlan, MissionTask
from aegis_os.agents.dev.agent import AegisDev
from aegis_os.agents.ops.agent import AegisOps
from aegis_os.agents.qa.agent import AegisQA, TestReport
from aegis_os.agents.sec.agent import AegisSec, SecurityReport, SecuritySummary
from aegis_os.kernel.state import AgentRole, MissionStatus
from aegis_os.orchestration.adaptive import AdaptiveOrchestrator
from aegis_os.verification.reviewer import AegisReviewer, ReviewDecision, ReviewReport
from aegis_os.verification.workspace_audit import collect_diff, current_commit

TEST_FILE = "def test_add():\n    assert 1 + 1 == 2\n\ndef test_sub():\n    assert 3 - 1 == 2\n"
GOOD_JSON = '```json\n{"decision": "APPROVED", "score": 9, "summary": "ok", "findings": [], "blocking_reasons": []}\n```'
CLEAN_QA = TestReport(passed=4, failed=0, errors=0, findings=[])
CLEAN_SEC = SecurityReport(audit_target=".", findings=[], summary=SecuritySummary(critical=0, high=0, medium=0, low=0))
DIFF = "diff --git a/app.py b/app.py\n+def f(): return 1"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_math.py").write_text(TEST_FILE)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def _llm(*contents: str | Exception) -> MagicMock:
    llm = MagicMock()
    outcomes = []
    for c in contents:
        if isinstance(c, Exception):
            outcomes.append(c)
        else:
            outcomes.append(MagicMock(content=c))
    llm.invoke.side_effect = outcomes
    return llm


def _review(llm: MagicMock) -> ReviewReport:
    return AegisReviewer(llm=llm).review("obj", DIFF, CLEAN_QA, CLEAN_SEC)


# ---------------------------------------------------------------- reviewer fails CLOSED
def test_reviewer_does_not_approve_when_output_is_not_json():
    llm = _llm("Looks fine to me!", "Honestly it looks great.")
    report = _review(llm)
    assert report.decision == ReviewDecision.CHANGES_REQUESTED
    assert report.verdict_failed and not report.is_approved
    assert llm.invoke.call_count == 2  # one retry


def test_reviewer_does_not_approve_when_llm_raises():
    report = _review(_llm(RuntimeError("503"), RuntimeError("503")))
    assert report.verdict_failed and not report.is_approved
    assert "503" in report.summary


def test_reviewer_missing_decision_key_is_not_an_approval():
    report = _review(_llm('{"score": 9, "summary": "fine"}', '{"summary": "fine"}'))
    assert report.verdict_failed and not report.is_approved


def test_reviewer_retry_recovers_after_a_prose_first_answer():
    report = _review(_llm("Let me think about it...", GOOD_JSON))
    assert report.is_approved and not report.verdict_failed


def test_reviewer_ignores_braces_in_reasoning_text_before_the_json():
    noisy = "Considering {the diff} and a set {1, 2}.\n" + GOOD_JSON
    assert _review(_llm(noisy)).is_approved


def test_reviewer_changes_requested_is_respected():
    bad = '{"decision": "CHANGES_REQUESTED", "score": 3, "summary": "bug", "blocking_reasons": ["off by one"]}'
    report = _review(_llm(bad))
    assert report.decision == ReviewDecision.CHANGES_REQUESTED and not report.verdict_failed


# ---------------------------------------------------------------- diff collection
def test_collect_diff_contains_edits_and_new_uncommitted_files_but_not_secrets(repo: Path):
    base = current_commit(repo)
    (repo / "tests" / "test_math.py").write_text(TEST_FILE + "\ndef test_mul():\n    assert 2 * 2 == 4\n")
    (repo / "app.py").write_text("def f():\n    return 1\n")
    (repo / ".env").write_text("NVIDIA_API_KEY=super-secret-value\n")
    diff = collect_diff(repo, base)
    assert "test_mul" in diff and "+++ b/app.py" in diff and "+def f():" in diff
    assert "super-secret-value" not in diff


def test_collect_diff_without_base_commit_is_empty(tmp_path: Path):
    assert collect_diff(tmp_path, None) == ""


# ---------------------------------------------------------------- full mission loop
class FakeReviewer:
    def __init__(self, *reports: ReviewReport) -> None:
        self.reports = list(reports)
        self.diffs: list[str] = []

    def review(self, objective, git_diff, qa_report=None, sec_report=None) -> ReviewReport:
        self.diffs.append(git_diff)
        return self.reports.pop(0) if len(self.reports) > 1 else self.reports[0]


APPROVE = ReviewReport(decision=ReviewDecision.APPROVED, summary="good")
REJECT = ReviewReport(
    decision=ReviewDecision.CHANGES_REQUESTED, score=3, summary="not good",
    blocking_reasons=["divide() ignores zero"],
)
FAILED = ReviewReport(
    decision=ReviewDecision.CHANGES_REQUESTED, score=1, summary="no verdict", verdict_failed=True,
    blocking_reasons=["Reviewer produced no valid verdict"],
)


def _orchestrator(repo: Path, dev_run, reviewer) -> tuple[AdaptiveOrchestrator, MagicMock]:
    cto = MagicMock(spec=AegisCTO)
    cto.role = AgentRole.CTO
    cto.plan_mission.return_value = MissionPlan(
        mission_title="m", objective="make a change",
        tasks=[MissionTask(task_id="T1", title="t", description="d", assigned_to="AegisDev")],
    )
    dev = MagicMock(spec=AegisDev)
    dev.role = AgentRole.DEV
    dev.run.side_effect = dev_run
    qa = MagicMock(spec=AegisQA)
    qa.role = AgentRole.QA
    qa.run_and_report.return_value = CLEAN_QA
    sec = MagicMock(spec=AegisSec)
    sec.role = AgentRole.SEC
    sec.audit.return_value = CLEAN_SEC
    ops = MagicMock(spec=AegisOps)
    ops.role = AgentRole.OPS
    ops.health_check.return_value = "healthy"
    orch = AdaptiveOrchestrator(
        workspace_root=repo, cto=cto, dev=dev, qa=qa, sec=sec, ops=ops,
        reviewer=reviewer, max_repair_cycles=3,
    )
    return orch, dev


def test_reviewer_rejection_triggers_repair_and_reviewer_sees_new_files(repo: Path):
    def dev_run(prompt: str, *a, **k) -> str:
        (repo / "app.py").write_text("def divide(a, b):\n    return a / b\n")
        return "implemented"

    reviewer = FakeReviewer(REJECT, APPROVE)
    orch, dev = _orchestrator(repo, dev_run, reviewer)
    summary = orch.execute_mission("add divide")

    assert summary.status == MissionStatus.COMPLETED
    assert summary.repair_cycles == 1
    assert len(reviewer.diffs) == 2
    assert "+++ b/app.py" in reviewer.diffs[0]           # new uncommitted file was reviewed
    repair_prompt = dev.run.call_args_list[-1].args[0]
    assert "divide() ignores zero" in repair_prompt      # reviewer feedback reaches Dev


def test_test_deletion_is_caught_by_the_gate_then_repaired(repo: Path):
    calls = {"n": 0}

    def dev_run(prompt: str, *a, **k) -> str:
        calls["n"] += 1
        path = repo / "tests" / "test_math.py"
        if calls["n"] == 1:   # cheating: delete the inconvenient test
            path.write_text("def test_add():\n    assert 1 + 1 == 2\n")
        else:                 # repair: restore it
            path.write_text(TEST_FILE)
        return "done"

    orch, dev = _orchestrator(repo, dev_run, FakeReviewer(APPROVE))
    summary = orch.execute_mission("speed things up")

    assert summary.status == MissionStatus.COMPLETED
    assert summary.repair_cycles == 1
    assert "TEST DELETION" in dev.run.call_args_list[-1].args[0]


def test_unrepaired_test_deletion_fails_the_mission(repo: Path):
    def dev_run(prompt: str, *a, **k) -> str:
        (repo / "tests" / "test_math.py").write_text("def test_add():\n    assert 1 + 1 == 2\n")
        return "done"

    orch, _ = _orchestrator(repo, dev_run, FakeReviewer(APPROVE))
    summary = orch.execute_mission("speed things up")
    assert summary.status == MissionStatus.FAILED


def test_reviewer_that_cannot_judge_stops_the_mission_without_wasting_repairs(repo: Path):
    def dev_run(prompt: str, *a, **k) -> str:
        (repo / "app.py").write_text("x = 1\n")
        return "done"

    orch, dev = _orchestrator(repo, dev_run, FakeReviewer(FAILED))
    summary = orch.execute_mission("anything")
    assert summary.status == MissionStatus.FAILED
    assert summary.repair_cycles == 0
    assert dev.run.call_count == 1


def test_reviewer_construction_failure_fails_closed(repo: Path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("NVIDIA_API_KEY is missing")

    monkeypatch.setattr("aegis_os.verification.reviewer.AegisReviewer.__init__", boom)
    orch, _ = _orchestrator(repo, lambda *a, **k: "done", None)
    summary = orch.execute_mission("anything")
    assert summary.status == MissionStatus.FAILED
