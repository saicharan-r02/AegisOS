"""Unit tests for Phase 4: Dynamic Planning, Failure Ledger, Worktree Isolation, and Hard Invariants."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from aegis_os.agents.cto.agent import AegisCTO, MissionPlan, MissionTask
from aegis_os.agents.dev.agent import AegisDev
from aegis_os.agents.ops.agent import AegisOps
from aegis_os.agents.qa.agent import AegisQA, TestFinding, TestReport
from aegis_os.agents.sec.agent import AegisSec, SecurityFinding, SecurityReport, SecuritySummary
from aegis_os.kernel.state import AgentRole, MissionStatus
from aegis_os.kernel.state_machine import MissionOrchestrator
from aegis_os.orchestration.invariants import HardInvariantEngine
from aegis_os.orchestration.ledger import FailureLedger
from aegis_os.orchestration.planner import DynamicPlan, PlanTask, TaskStatus
from aegis_os.orchestration.worktree import WorktreeManager


class TestDynamicPlan:
    def test_plan_dag_ready_and_parallel_resolution(self) -> None:
        plan = DynamicPlan(goal="Build authenticated payments")
        t1 = PlanTask(task_id="T1", title="Auth module", description="Create Auth", role=AgentRole.DEV)
        t2 = PlanTask(task_id="T2", title="DB models", description="Create Models", role=AgentRole.DEV)
        t3 = PlanTask(task_id="T3", title="Payment API", description="Create API", role=AgentRole.DEV, depends_on=["T1", "T2"])

        plan.add_task(t1)
        plan.add_task(t2)
        plan.add_task(t3)

        # Initially, T1 and T2 have no dependencies and are ready
        ready = plan.get_ready_tasks()
        ready_ids = {t.task_id for t in ready}
        assert ready_ids == {"T1", "T2"}

        # Check parallel grouping: T1 and T2 can run concurrently
        groups = plan.get_parallel_groups()
        assert len(groups) >= 1
        assert any(len(g) == 2 for g in groups)

        plan.mark_task("T1", TaskStatus.COMPLETED)
        ready = plan.get_ready_tasks()
        assert [t.task_id for t in ready] == ["T2"]

        plan.mark_task("T2", TaskStatus.COMPLETED)
        ready = plan.get_ready_tasks()
        assert [t.task_id for t in ready] == ["T3"]

        plan.mark_task("T3", TaskStatus.COMPLETED)
        assert plan.is_all_completed()

    def test_dynamic_replan_failed_subgraph(self) -> None:
        plan = DynamicPlan(goal="Deploy microservice")
        t1 = PlanTask(task_id="T1", title="Docker build", description="Build image", role=AgentRole.OPS)
        t2 = PlanTask(task_id="T2", title="Kubernetes deploy", description="Deploy pod", role=AgentRole.OPS, depends_on=["T1"])
        plan.add_task(t1)
        plan.add_task(t2)

        # T1 fails (e.g. docker daemon unavailable)
        plan.mark_task("T1", TaskStatus.FAILED, error="Docker socket missing")

        # Re-plan: substitute T1 with T1-alt (local binary runner)
        alt_task = PlanTask(
            task_id="T1-alt",
            title="Local process build",
            description="Build binary locally without Docker",
            role=AgentRole.OPS,
        )
        plan.replan_failed_subgraph("T1", [alt_task])

        assert plan.replan_count == 1
        # T2 must now depend on T1-alt
        assert "T1-alt" in plan.tasks["T2"].depends_on
        assert "T1" not in plan.tasks["T2"].depends_on

        # T1-alt is now ready to run
        ready = plan.get_ready_tasks()
        assert [t.task_id for t in ready] == ["T1-alt"]


class TestFailureLedger:
    def test_ledger_records_and_formats_guidance(self) -> None:
        ledger = FailureLedger()
        ledger.record_failure(
            task_id="T1",
            role=AgentRole.DEV,
            error_message="ImportError: module 'jwt' not installed",
            attempted_action="import jwt in auth.py",
            root_cause_analysis="PyJWT dependency missing from requirements.",
            avoidance_rule="Install PyJWT before attempting to import jwt.",
        )

        assert ledger.failure_count_for_task("T1") == 1
        rules = ledger.get_avoidance_rules()
        assert len(rules) == 1
        assert "Install PyJWT" in rules[0]

        guidance = ledger.format_guidance_for_planner()
        assert "Failure Ledger" in guidance
        assert "ImportError: module 'jwt' not installed" in guidance
        assert "Avoidance Rule" in guidance


class TestHardInvariants:
    def test_hard_invariants_pass_on_clean_reports(self) -> None:
        qa = TestReport(passed=5, failed=0, errors=0, findings=[])
        sec = SecurityReport(audit_target=".", findings=[], summary=SecuritySummary(critical=0, high=0, medium=0, low=0))

        passed, results = HardInvariantEngine.evaluate(qa_report=qa, sec_report=sec)
        assert passed
        assert all(r.passed for r in results)

    def test_hard_invariant_rejects_zero_tests(self) -> None:
        # 0 tests executed is a violation: must have verified changes!
        qa = TestReport(passed=0, failed=0, errors=0, findings=[])
        sec = SecurityReport(audit_target=".", findings=[], summary=SecuritySummary(critical=0, high=0, medium=0, low=0))

        passed, results = HardInvariantEngine.evaluate(qa_report=qa, sec_report=sec)
        assert not passed
        qa_inv = next(r for r in results if r.name == "INVARIANT_1_QA_PASS")
        assert not qa_inv.passed
        assert "No tests were executed" in qa_inv.details

    def test_hard_invariant_rejects_sec_critical(self) -> None:
        qa = TestReport(passed=5, failed=0, errors=0, findings=[])
        sec = SecurityReport(
            audit_target=".",
            findings=[
                SecurityFinding(id="S1", severity="CRITICAL", category="Injection", file="a.py", line=1, description="SQLi", remediation="Use params")
            ],
            summary=SecuritySummary(critical=1, high=0, medium=0, low=0),
        )

        passed, results = HardInvariantEngine.evaluate(qa_report=qa, sec_report=sec)
        assert not passed
        sec_inv = next(r for r in results if r.name == "INVARIANT_2_SEC_CLEARANCE")
        assert not sec_inv.passed

    def test_hard_invariant_allows_non_python_deliverables(self, tmp_path: Path) -> None:
        login_html = tmp_path / "login.html"
        login_html.write_text("<html><body>Login</body></html>", encoding="utf-8")
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=False)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=tmp_path, check=False)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=False)
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=False)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=False)

        qa = TestReport(passed=0, failed=0, errors=0, findings=[])
        sec = SecurityReport(audit_target=".", findings=[], summary=SecuritySummary(critical=0, high=0, medium=0, low=0))

        passed, results = HardInvariantEngine.evaluate(
            qa_report=qa,
            sec_report=sec,
            workspace_root=tmp_path,
            objective="create an normal login page using HTML",
        )
        assert passed
        qa_inv = next(r for r in results if r.name == "INVARIANT_1_QA_PASS")
        assert qa_inv.passed


class TestWorktreeManager:
    def test_directory_fallback_worktree(self, tmp_path: Path) -> None:
        # Non-git workspace
        (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
        mgr = WorktreeManager(tmp_path)

        wt_dir = mgr.create_worktree("task-1")
        assert wt_dir.is_dir()
        assert (wt_dir / "main.py").is_file()

        # Modify file inside worktree
        (wt_dir / "main.py").write_text("print('updated in worktree')", encoding="utf-8")

        success, msg = mgr.merge_worktree("task-1")
        assert success
        assert (tmp_path / "main.py").read_text(encoding="utf-8") == "print('updated in worktree')"

        mgr.cleanup_worktree("task-1")
        assert not wt_dir.exists()


class TestPhase4BenchmarkAdaptivePivot:
    """Benchmark Phase 4: Test adaptive orchestrator pivoting when a task iteration fails."""

    def test_adaptive_orchestrator_pivots_and_completes(self, tmp_path: Path) -> None:
        mock_cto = MagicMock(spec=AegisCTO)
        mock_cto.role = AgentRole.CTO
        mock_cto.plan_mission.return_value = MissionPlan(
            mission_title="Fix Calculator Bug",
            objective="Fix division by zero without breaking existing tests",
            tasks=[
                MissionTask(
                    task_id="T1",
                    title="Implement ZeroDivision check",
                    description="Add check to raise ValueError on 0",
                    assigned_to="AegisDev",
                    depends_on=[],
                )
            ],
            risk_flags=[],
        )

        mock_dev = MagicMock(spec=AegisDev)
        mock_dev.role = AgentRole.DEV
        # First attempt by DEV returns an error requiring pivot; second attempt succeeds
        mock_dev.run.side_effect = [
            "ERROR: Division check broke legacy behavior.",
            "Pivoted implementation: Handled ZeroDivisionError cleanly with custom error.",
            "Verification repair applied.",
        ]

        # QA initially fails with 1 error, then passes
        qa_failing = TestReport(
            passed=3,
            failed=1,
            errors=0,
            findings=[TestFinding(test_name="test_div", error_message="ZeroDivisionError unexpected", root_cause_hypothesis="Need custom exception")],
        )
        qa_passing = TestReport(passed=4, failed=0, errors=0, findings=[])
        mock_qa = MagicMock(spec=AegisQA)
        mock_qa.role = AgentRole.QA
        mock_qa.run_and_report.side_effect = [qa_failing, qa_passing]

        mock_sec = MagicMock(spec=AegisSec)
        mock_sec.role = AgentRole.SEC
        mock_sec.audit.return_value = SecurityReport(
            audit_target=".",
            findings=[],
            summary=SecuritySummary(critical=0, high=0, medium=0, low=0),
        )

        mock_ops = MagicMock(spec=AegisOps)
        mock_ops.role = AgentRole.OPS
        mock_ops.health_check.return_value = "Operational Health Check: 100% HEALTHY"

        orchestrator = MissionOrchestrator(
            workspace_root=tmp_path,
            cto=mock_cto,
            dev=mock_dev,
            qa=mock_qa,
            sec=mock_sec,
            ops=mock_ops,
            strategy="adaptive",
            max_repair_cycles=3,
        )

        summary = orchestrator.execute_mission("Fix Calculator Bug")

        # Verify mission completed successfully after adaptive pivot and repair
        assert summary.status == MissionStatus.COMPLETED
        assert summary.repair_cycles == 1
        assert summary.qa_report is not None
        assert summary.qa_report.passed == 4
        assert summary.sec_report is not None
        assert summary.sec_report.summary.critical == 0
