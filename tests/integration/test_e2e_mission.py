from pathlib import Path
import subprocess
from unittest.mock import MagicMock
import pytest
from aegis_os.agents.cto.agent import AegisCTO,MissionPlan,MissionTask
from aegis_os.agents.dev.agent import AegisDev
from aegis_os.agents.ops.agent import AegisOps
from aegis_os.agents.qa.agent import AegisQA,TestFinding,TestReport
from aegis_os.agents.sec.agent import AegisSec,SecurityReport,SecuritySummary
from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.events import EventBus,KernelEvent
from aegis_os.kernel.state import AgentRole,MissionStatus
from aegis_os.kernel.state_machine import MissionOrchestrator


@pytest.fixture
def git_workspace(tmp_path:Path)->Path:
    """Create a temporary initialized Git repository."""
    ws=tmp_path/"repo"
    ws.mkdir(parents=True,exist_ok=True)

    subprocess.run(["git","init"],cwd=ws,check=True,capture_output=True)
    subprocess.run(["git","config","user.name","AegisBot"],cwd=ws,check=True,capture_output=True)
    subprocess.run(["git","config","user.email","bot@aegis.os"],cwd=ws,check=True,capture_output=True)

    init_file=ws/"README.md"
    init_file.write_text("# Project\nInitial commit.\n",encoding="utf-8")
    subprocess.run(["git","add","."],cwd=ws,check=True,capture_output=True)
    subprocess.run(["git","commit","-m","Initial commit"],cwd=ws,check=True,capture_output=True)

    return ws

class TestE2EMissionLifecycle:
    """Full end-to-end integration test of the autonomous engineering lifecycle."""

    def test_complete_mission_with_closed_loop_repair_and_git_audit(self,git_workspace:Path) -> None:
        """
        Verify an entire mission execution:
        1. CTO produces structured MissionPlan.
        2. Dev implements source file and tests, creating real Git commits.
        3. QA catches an initial failure, triggering closed-loop repair.
        4. Dev commits repair patch; QA verifies green.
        5. Sec audits code and validates zero critical/high vulnerabilities.
        6. Ops runs health check confirming importability.
        7. StateMachine persists all steps into SQLite WAL CheckpointStore.
        8. CheckpointStore rollbacks are validated.
        """
        db_path=git_workspace/"checkpoints.db"
        store=CheckpointStore(db_path=db_path)
        bus=EventBus()

        captured_events:list[KernelEvent]=[]
        bus.subscribe("*",lambda e:captured_events.append(e))

        cto=MagicMock(spec=AegisCTO)
        cto.role=AgentRole.CTO
        cto.plan_mission.return_value=MissionPlan(
            mission_title="Build Calculator Service",
            objective="Implement math library with test suite",
            tasks=[
                MissionTask(
                    task_id="TASK-1",
                    title="Implement math functions",
                    description="Write calc.py with add, sub, mul, div",
                    assigned_to="AegisDev",
                    depends_on=[],
                ),
                MissionTask(
                    task_id="TASK-2",
                    title="Add test suite",
                    description="Write test_calc.py",
                    assigned_to="AegisDev",
                    depends_on=["TASK-1"],
                ),
            ],
            risk_flags=["Handle ZeroDivisionError cleanly"],
        )

        dev=MagicMock(spec=AegisDev)
        dev.role=AgentRole.DEV

        def dev_run_mock(task_prompt:str)->str:
            if "TASK-1"in task_prompt:
                calc_file=git_workspace/"calc.py"
                calc_file.write_text(
                    "def add(a, b): return a + b\n"
                    "def divide(a, b): return a / b  # intentional unhandled bug\n",
                    encoding="utf-8",
                )
                subprocess.run(["git","add","calc.py"],cwd=git_workspace,check=True,capture_output=True)
                subprocess.run(["git","commit","-m","feat: implement calculator functions"],cwd=git_workspace,check=True,capture_output=True)
                return "Implemented calc.py and committed"
            elif "TASK-2" in task_prompt:
                test_file=git_workspace/"test_calc.py"
                test_file.write_text(
                    "from calc import add, divide\n"
                    "def test_add(): assert add(2, 3) == 5\n"
                    "def test_divide_by_zero():\n"
                    "    try:\n"
                    "        divide(10, 0)\n"
                    "        assert False, 'Should have raised ValueError'\n"
                    "    except ValueError:\n"
                    "        assert True\n",
                    encoding="utf-8",
                )
                subprocess.run(["git","add","test_calc.py"],cwd=git_workspace,check=True,capture_output=True)
                subprocess.run(["git","commit","-m","test: add test suite for calculator"],cwd=git_workspace,check=True,capture_output=True)
                return "Created test_calc.py and committed"
            elif "Repair Cycle" in task_prompt:
                calc_file = git_workspace / "calc.py"
                calc_file.write_text(
                    "def add(a, b): return a + b\n"
                    "def divide(a, b):\n"
                    "    if b == 0:\n"
                    "        raise ValueError('Cannot divide by zero')\n"
                    "    return a / b\n",
                    encoding="utf-8",
                )
                subprocess.run(["git","add","calc.py"],cwd=git_workspace,check=True,capture_output=True)
                subprocess.run(["git","commit","-m","fix: handle division by zero in divide()"],cwd=git_workspace,check=True,capture_output=True)
                return "Fixed ZeroDivisionError and committed patch"
            return "Task completed"

        dev.run.side_effect=dev_run_mock

        qa=MagicMock(spec=AegisQA)
        qa.role=AgentRole.QA

        qa_failing=TestReport(
            passed=1,
            failed=1,
            errors=0,
            findings=[
                TestFinding(
                    test_name="test_divide_by_zero",
                    error_message="ZeroDivisionError: division by zero",
                    root_cause_hypothesis="divide() does not catch b == 0 and raise ValueError",
                )
            ],
        )
        qa_passing=TestReport(passed=2,failed=0,errors=0,findings=[])
        qa.run_and_report.side_effect=[qa_failing,qa_passing]

        sec=MagicMock(spec=AegisSec)
        sec.role=AgentRole.SEC
        sec.audit.return_value=SecurityReport(
            audit_target=str(git_workspace),
            findings=[],
            summary=SecuritySummary(critical=0,high=0,medium=0,low=0),
        )

        ops=MagicMock(spec=AegisOps)
        ops.role=AgentRole.OPS
        ops.health_check.return_value="Imports OK, Git clean, All dependencies satisfied."

        orchestrator=MissionOrchestrator(
            workspace_root=git_workspace,
            checkpoint_store=store,
            event_bus=bus,
            cto=cto,
            dev=dev,
            qa=qa,
            sec=sec,
            ops=ops,
            max_repair_cycles=3,
        )

        summary=orchestrator.execute_mission("Build resilient calculator library")

        assert summary.status==MissionStatus.COMPLETED
        assert summary.tasks_executed==["TASK-1","TASK-2"]
        assert summary.repair_cycles==1
        assert len(summary.repair_history)==1
        assert summary.repair_history[0].resolved is True
        assert "ZeroDivisionError" in summary.repair_history[0].issues_detected[0]
        assert summary.qa_report.passed==2
        assert summary.sec_report.summary.critical==0

        log_res=subprocess.run(
            ["git","log","--oneline"],
            cwd=git_workspace,
            capture_output=True,
            text=True,
            check=True,
        )
        git_log=log_res.stdout
        assert "feat: implement calculator functions" in git_log
        assert "test: add test suite for calculator" in git_log
        assert "fix: handle division by zero in divide()" in git_log

        final_calc=(git_workspace/"calc.py").read_text(encoding="utf-8")
        assert "Cannot divide by zero" in final_calc

        event_types=[e.event_type for e in captured_events]
        assert "mission.status_changed" in event_types
        assert "state.transition" in event_types

        missions=store.list_missions()
        assert len(missions)==1
        assert missions[0]["status"]=="COMPLETED"

        steps=store.list_steps(summary.session_id)
        if len(steps)>1:
            restored=store.rollback_to_step(summary.session_id,1)
            assert restored.current_step_index==1

        store.close()