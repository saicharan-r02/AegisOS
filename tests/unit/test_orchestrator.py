from unittest.mock import MagicMock
import pytest
from aegis_os.agents.cto.agent import AegisCTO,MissionPlan,MissionTask
from aegis_os.agents.dev.agent import AegisDev
from aegis_os.agents.ops.agent import AegisOps
from aegis_os.agents.qa.agent import AegisQA,TestFinding,TestReport
from aegis_os.agents.sec.agent import AegisSec,SecurityFinding,SecurityReport,SecuritySummary
from aegis_os.kernel.exceptions import CycleDetectedError
from aegis_os.kernel.state import AgentRole,DAGNode,MissionDAG,MissionStatus
from aegis_os.kernel.state_machine import MissionOrchestrator
from aegis_os.kernel.state import MissionPhase


class TestMissionDAGTopologicalSort:
    """Unit tests for topological sort on MissionDAG."""

    def test_linear_topological_sort(self) -> None:
        dag = MissionDAG()
        dag.add_node(DAGNode(node_id="A",role=AgentRole.CTO,task="Plan"))
        dag.add_node(DAGNode(node_id="B",role=AgentRole.DEV,task="Code"))
        dag.add_node(DAGNode(node_id="C",role=AgentRole.QA,task="Test"))

        dag.add_edge("A","B")
        dag.add_edge("B","C")

        sorted_nodes=dag.topological_sort()
        order=[n.node_id for n in sorted_nodes]
        assert order==["A","B","C"]

    def test_diamond_topological_sort(self) -> None:
        dag = MissionDAG()
        dag.add_node(DAGNode(node_id="start",role=AgentRole.CTO,task="Start"))
        dag.add_node(DAGNode(node_id="left",role=AgentRole.DEV,task="Left branch"))
        dag.add_node(DAGNode(node_id="right",role=AgentRole.DEV,task="Right branch"))
        dag.add_node(DAGNode(node_id="join",role=AgentRole.QA,task="Join branch"))

        dag.add_edge("start","left")
        dag.add_edge("start","right")
        dag.add_edge("left","join")
        dag.add_edge("right","join")

        sorted_nodes=dag.topological_sort()
        order=[n.node_id for n in sorted_nodes]

        assert order[0]=="start"
        assert order[-1]=="join"
        assert set(order[1:3])=={"left","right"}

    def test_cycle_detection_in_topological_sort(self) -> None:
        dag = MissionDAG()
        dag.add_node(DAGNode(node_id="1",role=AgentRole.DEV,task="One"))
        dag.add_node(DAGNode(node_id="2",role=AgentRole.DEV,task="Two"))
        dag.add_edge("1","2")

        with pytest.raises(CycleDetectedError):
            dag.add_edge("2","1")


class TestMissionOrchestrator:
    """End-to-end department orchestration tests."""

    @pytest.fixture
    def mock_cto(self) -> MagicMock:
        cto=MagicMock(spec=AegisCTO)
        cto.role=AgentRole.CTO
        cto.plan_mission.return_value=MissionPlan(
            mission_title="Build User Service",
            objective="Implement authenticated user microservice",
            tasks=[
                MissionTask(
                    task_id="T1",
                    title="Design models",
                    description="Create User and Session models",
                    assigned_to="AegisDev",
                    depends_on=[]
                ),
                MissionTask(
                    task_id="T2",
                    title="Implement API endpoints",
                    description="Create login and registration routes",
                    assigned_to="AegisDev",
                    depends_on=["T1"]
                )
            ],
            risk_flags=["Rate limiting required"]
        )
        return cto

    @pytest.fixture
    def mock_dev(self) -> MagicMock:
        dev=MagicMock(spec=AegisDev)
        dev.role=AgentRole.DEV
        dev.run.return_value="Task completed and committed."
        return dev

    @pytest.fixture
    def mock_qa(self) -> MagicMock:
        qa=MagicMock(spec=AegisQA)
        qa.role=AgentRole.QA
        qa.run_and_report.return_value=TestReport(
            passed=12,
            failed=0,
            errors=0,
            findings=[]
        )
        return qa

    @pytest.fixture
    def mock_sec(self) -> MagicMock:
        sec=MagicMock(spec=AegisSec)
        sec.role=AgentRole.SEC
        sec.audit.return_value=SecurityReport(
            audit_target="aegis_os/",
            findings=[],
            summary=SecuritySummary(critical=0,high=0,medium=0,low=0)
        )
        return sec

    @pytest.fixture
    def mock_ops(self) -> MagicMock:
        ops=MagicMock(spec=AegisOps)
        ops.role=AgentRole.OPS
        ops.health_check.return_value="Operational Health Check: 100% HEALTHY"
        return ops

    def test_clean_mission_flow(self,tmp_workspace,mock_cto,mock_dev,mock_qa,mock_sec,mock_ops) -> None:
        """Test clean happy path without any verification failures."""
        orchestrator=MissionOrchestrator(
            workspace_root=tmp_workspace,
            cto=mock_cto,
            dev=mock_dev,
            qa=mock_qa,
            sec=mock_sec,
            ops=mock_ops
        )

        summary=orchestrator.execute_mission("Build User Service")

        assert summary.status==MissionStatus.COMPLETED
        assert summary.goal=="Build User Service"
        assert summary.tasks_executed==["T1","T2"]
        assert summary.repair_cycles==0
        assert len(summary.repair_history)==0
        assert summary.qa_report is not None
        assert summary.qa_report.passed==12
        assert summary.sec_report is not None
        assert summary.sec_report.summary.critical==0
        assert summary.ops_report =="Operational Health Check: 100% HEALTHY"
        assert summary.duration_seconds>=0.0

        mock_cto.plan_mission.assert_called_once_with("Build User Service")
        assert mock_dev.run.call_count==2
        mock_qa.run_and_report.assert_called_once()
        mock_sec.audit.assert_called_once()
        mock_ops.health_check.assert_called_once()

    def test_closed_loop_repair_qa_failure(self,tmp_workspace,mock_cto,mock_dev,mock_qa,mock_sec,mock_ops) -> None:
        """Test that QA test failures trigger a repair cycle to AegisDev and pass on retry."""

        qa_failing=TestReport(
            passed=10,
            failed=1,
            errors=0,
            findings=[
                TestFinding(
                    test_name="test_login_auth",
                    error_message="Invalid credentials returned 200 instead of 401",
                    root_cause_hypothesis="Missing credential validation check in login route"
                )
            ],
        )
        qa_passing=TestReport(passed=11,failed=0,errors=0,findings=[])
        mock_qa.run_and_report.side_effect=[qa_failing,qa_passing]

        mock_dev.run.side_effect=[
            "T1 completed",
            "T2 completed",
            "Fixed credential validation and committed patch."
        ]

        orchestrator=MissionOrchestrator(
            workspace_root=tmp_workspace,
            cto=mock_cto,
            dev=mock_dev,
            qa=mock_qa,
            sec=mock_sec,
            ops=mock_ops,
            max_repair_cycles=3
        )

        summary=orchestrator.execute_mission("Build User Service")

        assert summary.status==MissionStatus.COMPLETED
        assert summary.repair_cycles==1
        assert len(summary.repair_history)==1
        assert summary.repair_history[0].trigger=="QA_FAILURES"
        assert summary.repair_history[0].resolved is True
        assert "Missing credential validation" in summary.repair_history[0].issues_detected[0]
        assert summary.repair_history[0].dev_patch_summary=="Fixed credential validation and committed patch."

        assert mock_dev.run.call_count==3
        assert mock_qa.run_and_report.call_count==2
        assert mock_ops.health_check.call_count==1

    def test_closed_loop_repair_security_vulnerability(self,tmp_workspace,mock_cto,mock_dev,mock_qa,mock_sec,mock_ops) -> None:
        """Test that security vulnerabilities trigger a repair cycle to AegisDev."""
        
        sec_failing=SecurityReport(
            audit_target="aegis_os/",
            findings=[
                SecurityFinding(
                    id="SEC-001",
                    severity="CRITICAL",
                    category="A03:Injection",
                    file="models.py",
                    line=42,
                    description="Raw SQL query string interpolation",
                    remediation="Use parameterized queries"
                )
            ],
            summary=SecuritySummary(critical=1)
        )
        sec_passing=SecurityReport(
            audit_target="aegis_os/",
            findings=[],
            summary=SecuritySummary(critical=0)
        )
        mock_sec.audit.side_effect=[sec_failing,sec_passing]

        orchestrator=MissionOrchestrator(
            workspace_root=tmp_workspace,
            cto=mock_cto,
            dev=mock_dev,
            qa=mock_qa,
            sec=mock_sec,
            ops=mock_ops,
            max_repair_cycles=3
        )

        summary=orchestrator.execute_mission("Build User Service")

        assert summary.status==MissionStatus.COMPLETED
        assert summary.repair_cycles==1
        assert "SECURITY_VULNERABILITIES" in summary.repair_history[0].trigger
        assert summary.repair_history[0].resolved is True

    def test_max_repair_cycles_guard_fails_mission(self,tmp_workspace,mock_cto,mock_dev,mock_qa,mock_sec,mock_ops) -> None:
        """Test that exceeding max_repair_cycles gracefully marks the mission as FAILED."""

        mock_qa.run_and_report.return_value = TestReport(
            passed=0,
            failed=3,
            errors=0,
            findings=[
                TestFinding(
                    test_name="test_stub",
                    error_message="Persistent regression",
                    root_cause_hypothesis="Fundamental design flaw"
                )
            ]
        )

        orchestrator=MissionOrchestrator(
            workspace_root=tmp_workspace,
            cto=mock_cto,
            dev=mock_dev,
            qa=mock_qa,
            sec=mock_sec,
            ops=mock_ops,
            max_repair_cycles=2
        )

        summary=orchestrator.execute_mission("Build Faulty Service")

        assert summary.status==MissionStatus.FAILED
        assert summary.repair_cycles==2

        mock_ops.health_check.assert_not_called()

    def test_topological_execution_dependency_order(self,tmp_workspace,mock_dev,mock_qa,mock_sec,mock_ops) -> None:
        """Verify tasks execute strictly according to DAG dependency order, not list order."""
        
        cto=MagicMock(spec=AegisCTO)
        cto.role=AgentRole.CTO
        cto.plan_mission.return_value=MissionPlan(
            mission_title="Multi-stage Pipeline",
            objective="Pipeline ordering test",
            tasks=[
                MissionTask(task_id="step_3",title="Final",description="Final step",assigned_to="AegisDev",depends_on=["step_2"]),
                MissionTask(task_id="step_2",title="Middle",description="Middle step",assigned_to="AegisDev",depends_on=["step_1"]),
                MissionTask(task_id="step_1",title="Init",description="Initial step",assigned_to="AegisDev",depends_on=[])
            ]
        )

        executed_tasks=[]

        def dev_run_side_effect(prompt: str) -> str:
            if "step_1" in prompt:
                executed_tasks.append("step_1")
            elif "step_2" in prompt:
                executed_tasks.append("step_2")
            elif "step_3" in prompt:
                executed_tasks.append("step_3")
            return "Done"

        mock_dev.run.side_effect=dev_run_side_effect

        orchestrator=MissionOrchestrator(
            workspace_root=tmp_workspace,
            cto=cto,
            dev=mock_dev,
            qa=mock_qa,
            sec=mock_sec,
            ops=mock_ops
        )

        summary=orchestrator.execute_mission("Pipeline Test")

        assert summary.status==MissionStatus.COMPLETED
        assert summary.tasks_executed==["step_1","step_2","step_3"]
        assert executed_tasks==["step_1","step_2","step_3"]

    def test_dag_cycle_fails_gracefully(self,tmp_workspace,mock_dev,mock_qa,mock_sec,mock_ops) -> None:
        """Test that if the CTO produces a plan with circular dependencies, orchestrator fails cleanly."""
        
        cto=MagicMock(spec=AegisCTO)
        cto.role=AgentRole.CTO

        cto.plan_mission.return_value=MissionPlan(
            mission_title="Cyclic Pipeline",
            objective="Cycle test",
            tasks=[
                MissionTask(task_id="task_A",title="A",description="Task A",assigned_to="AegisDev",depends_on=["task_B"]),
                MissionTask(task_id="task_B",title="B",description="Task B",assigned_to="AegisDev",depends_on=["task_A"])
            ]
        )

        orchestrator=MissionOrchestrator(
            workspace_root=tmp_workspace,
            cto=cto,
            dev=mock_dev,
            qa=mock_qa,
            sec=mock_sec,
            ops=mock_ops
        )

        summary=orchestrator.execute_mission("Cyclic Test")

        assert summary.status==MissionStatus.FAILED
        assert summary.error is not None
        assert "Cycle detected" in summary.error
        mock_dev.run.assert_not_called()