from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock,patch
import pytest
from rich.console import Console
from aegis_os.agents.cto.agent import MissionPlan,MissionTask
from aegis_os.agents.qa.agent import TestFinding,TestReport
from aegis_os.agents.sec.agent import SecurityFinding,SecurityReport,SecuritySummary
from aegis_os.cli.display import AegisDisplay
from aegis_os.cli.main import build_parser,main
from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.events import MissionStatusChangedEvent,StateTransitionEvent,StepCompletedEvent,StepStartedEvent
from aegis_os.kernel.state import AgentRole,AgentState,MissionStatus,StepRecord,StepStatus
from aegis_os.orchestrator.models import MissionSummary,RepairCycleRecord

class TestCLIParser:
    """Test CLI argument parsing for all subcommands."""

    def test_run_parser(self) -> None:
        parser=build_parser()
        args=parser.parse_args(["run","Build a feature","-w","/tmp","--max-repairs","5"])
        assert args.subcommand=="run"
        assert args.goal=="Build a feature"
        assert args.workspace=="/tmp"
        assert args.max_repairs==5
        assert args.provider=="openai"

    def test_audit_parser(self) -> None:
        parser=build_parser()
        args=parser.parse_args(["audit","-t","src/","-p","groq"])
        assert args.subcommand=="audit"
        assert args.target=="src/"
        assert args.provider=="groq"

    def test_test_parser(self) -> None:
        parser=build_parser()
        args=parser.parse_args(["test","-t","tests/unit/"])
        assert args.subcommand=="test"
        assert args.target=="tests/unit/"

    def test_status_parser_with_and_without_session(self) -> None:
        parser=build_parser()
        args_no_id=parser.parse_args(["status"])
        assert args_no_id.subcommand=="status"
        assert args_no_id.session_id is None

        args_id=parser.parse_args(["status","sess-1234"])
        assert args_id.session_id=="sess-1234"

    def test_rollback_parser(self) -> None:
        parser=build_parser()
        args=parser.parse_args(["rollback","sess-abc","5"])
        assert args.subcommand=="rollback"
        assert args.session_id=="sess-abc"
        assert args.step_index==5


class TestAegisDisplay:
    """Test rich visual formatting components."""

    @pytest.fixture
    def string_console(self) -> tuple[Console,StringIO]:
        buf=StringIO()
        console=Console(file=buf,force_terminal=True,width=120)
        return console,buf

    def test_show_banner(self,string_console) -> None:
        console,buf=string_console
        display=AegisDisplay(console=console)
        display.show_banner()
        output=buf.getvalue()
        assert "AegisOS" in output or "AEGIS" in output
        assert "CTO" in output
        assert "DEV" in output

    def test_show_plan(self,string_console) -> None:
        console,buf=string_console
        display=AegisDisplay(console=console)
        plan=MissionPlan(
            mission_title="Auth Pipeline",
            objective="Add JWT auth",
            tasks=[
                MissionTask(
                    task_id="T1",
                    title="JWT Module",
                    description="Implement token verification",
                    assigned_to="AegisDev",
                    depends_on=[]
                ),
                MissionTask(
                    task_id="T2",
                    title="Tests",
                    description="Write test fixtures",
                    assigned_to="AegisQA",
                    depends_on=["T1"]
                )
            ],
            risk_flags=["Clock skew vulnerability"]
        )
        display.show_plan(plan)
        output=buf.getvalue()
        assert "Auth Pipeline" in output
        assert "T1" in output
        assert "Clock skew" in output

    def test_show_qa_report(self,string_console) -> None:
        console,buf=string_console
        display=AegisDisplay(console=console)
        report=TestReport(
            passed=8,
            failed=1,
            errors=0,
            findings=[
                TestFinding(
                    test_name="test_jwt",
                    error_message="Invalid signature",
                    root_cause_hypothesis="Secret key mismatch"
                )
            ]
        )
        display.show_qa_report(report)
        output=buf.getvalue()
        assert "FAILING" in output
        assert "test_jwt" in output
        assert "Secret key mismatch" in output

    def test_show_sec_report(self,string_console) -> None:
        console,buf=string_console
        display=AegisDisplay(console=console)
        report=SecurityReport(
            audit_target="aegis_os/",
            findings=[
                SecurityFinding(
                    id="SEC-001",
                    severity="HIGH",
                    category="Injection",
                    file="db.py",
                    line=15,
                    description="SQL injection",
                    remediation="Use bound parameters"
                )
            ],
            summary=SecuritySummary(critical=0,high=1)
        )
        display.show_sec_report(report)
        output=buf.getvalue()
        assert "SEC-001" in output
        assert "HIGH" in output
        assert "SQL injection" in output

    def test_show_repair_cycle(self,string_console) -> None:
        console,buf=string_console
        display=AegisDisplay(console=console)
        record=RepairCycleRecord(
            cycle_index=1,
            trigger="QA_FAILURES",
            issues_detected=["test_jwt failed"],
            dev_patch_summary="Applied key fix",
            resolved=True
        )
        display.show_repair_cycle(record)
        output=buf.getvalue()
        assert "Repair Cycle #1" in output
        assert "RESOLVED" in output
        assert "Applied key fix" in output

    def test_show_summary(self,string_console) -> None:
        console,buf=string_console
        display=AegisDisplay(console=console)
        summary=MissionSummary(
            session_id="sess-xyz",
            goal="Add JWT auth",
            status=MissionStatus.COMPLETED,
            total_steps=12,
            tasks_executed=["T1","T2"],
            repair_cycles=1,
            duration_seconds=5.42
        )
        display.show_summary(summary)
        output=buf.getvalue()
        assert "COMPLETED" in output
        assert "sess-xyz" in output
        assert "5.42s" in output

    def test_telemetry_handler_renders_events(self,string_console) -> None:
        console,buf=string_console
        display=AegisDisplay(console=console)
        handler=display.create_telemetry_handler()

        handler(StateTransitionEvent(from_role=AgentRole.CTO,to_role=AgentRole.DEV,step_index=2))
        
        step=StepRecord(step_index=3,role=AgentRole.DEV,task_description="Refactoring handler",tool_name="write_file")
        handler(StepStartedEvent(step=step))
        
        step.complete(status=StepStatus.SUCCESS)
        handler(StepCompletedEvent(step=step))
        
        handler(MissionStatusChangedEvent(old_status=MissionStatus.PENDING,new_status=MissionStatus.RUNNING,goal="Test Goal"))

        output=buf.getvalue()
        assert "Control handoff" in output
        assert "Refactoring handler" in output
        assert "Success" in output
        assert "Mission Status" in output


class TestCLISubcommands:
    """Test CLI execution flows with mocks."""

    def test_main_help_returns_zero(self) -> None:
        exit_code=main([])
        assert exit_code==0

    def test_status_subcommand(self,tmp_path) -> None:
        db_path=tmp_path/"test_cp.db"
        store=CheckpointStore(db_path=db_path)
        state=AgentState(mission_goal="Status test",status=MissionStatus.COMPLETED)
        state.add_step(role=AgentRole.CTO,task_description="Planning")
        state.complete_current_step()
        store.save_checkpoint(state)
        store.close()

        exit_code=main(["status","--db-path",str(db_path)])
        assert exit_code==0

        exit_code=main(["status",state.session_id,"--db-path",str(db_path)])
        assert exit_code==0

    def test_rollback_subcommand(self,tmp_path) -> None:
        db_path=tmp_path/"test_cp.db"
        store=CheckpointStore(db_path=db_path)
        state=AgentState(mission_goal="Rollback test",status=MissionStatus.RUNNING)
        state.add_step(role=AgentRole.CTO,task_description="Step 1")
        state.complete_current_step()
        store.save_checkpoint(state)

        state.add_step(role=AgentRole.DEV,task_description="Step 2")
        state.complete_current_step()
        store.save_checkpoint(state)
        store.close()

        exit_code=main(["rollback",state.session_id,"1","--db-path",str(db_path)])
        assert exit_code==0

    def test_test_subcommand_mocked(self,tmp_path) -> None:
        with patch("aegis_os.cli.main.AegisQA") as mock_qa_cls:
            mock_qa=mock_qa_cls.return_value
            mock_qa.run_and_report.return_value=TestReport(passed=5,failed=0,errors=0)

            exit_code=main(["test","-w",str(tmp_path)])
            assert exit_code==0
            mock_qa.run_and_report.assert_called_once_with(target="tests/")

    def test_audit_subcommand_mocked(self,tmp_path) -> None:
        with patch("aegis_os.cli.main.AegisSec") as mock_sec_cls,patch("aegis_os.cli.main.AegisOps") as mock_ops_cls:
            mock_sec=mock_sec_cls.return_value
            mock_sec.audit.return_value=SecurityReport(
                audit_target="aegis_os/",
                findings=[],
                summary=SecuritySummary(critical=0,high=0)
            )
            mock_ops=mock_ops_cls.return_value
            mock_ops.health_check.return_value="All healthy"

            exit_code=main(["audit","-w",str(tmp_path)])
            assert exit_code==0

    def test_run_subcommand_mocked(self,tmp_path) -> None:
        with patch("aegis_os.cli.main.MissionOrchestrator") as mock_orch_cls:
            mock_orch=mock_orch_cls.return_value
            mock_orch.execute_mission.return_value=MissionSummary(
                session_id="sess-run-1",
                goal="Deploy service",
                status=MissionStatus.COMPLETED,
                total_steps=5,
                tasks_executed=["T1"],
                repair_cycles=0,
                duration_seconds=1.23
            )

            db_path=tmp_path/"checkpoints.db"
            exit_code=main(["run","Deploy service","-w",str(tmp_path),"--db-path",str(db_path)])
            assert exit_code==0
            mock_orch.execute_mission.assert_called_once_with("Deploy service")