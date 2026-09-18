"""
Test Suite: Kernel State & DAG Graph Models
===========================================
Tests proving:
  1. StepRecord duration calculation and completion status.
  2. AgentState step tracking, failure counters, and cloning.
  3. Pydantic V2 serialization / deserialization roundtrips.
  4. MissionDAG acyclicity enforcement and cycle detection.
"""

import pytest

from aegis_os.kernel.exceptions import CycleDetectedError
from aegis_os.kernel.state import (
    AgentRole,
    AgentState,
    DAGNode,
    MissionDAG,
    MissionStatus,
    StepRecord,
    StepStatus,
)
from aegis_os.tools.base import ToolResult


class TestStepRecord:
    """StepRecord tests for state changes and duration metrics."""

    def test_step_record_creation(self) -> None:
        step = StepRecord(
            step_index=1,
            role=AgentRole.DEV,
            task_description="Implement feature X",
            tool_name="read_file",
            tool_args={"path": "main.py"},
        )
        assert step.step_index == 1
        assert step.role == AgentRole.DEV
        assert step.status == StepStatus.PENDING
        assert step.finished_at is None
        assert step.duration_ms is None

    def test_step_record_complete_success(self) -> None:
        step = StepRecord(
            step_index=1,
            role=AgentRole.DEV,
            task_description="Inspect file",
        )
        res = ToolResult.ok(output="content")
        step.complete(tool_result=res)

        assert step.status == StepStatus.SUCCESS
        assert step.tool_result == res
        assert step.finished_at is not None
        assert step.duration_ms is not None
        assert step.duration_ms >= 0

    def test_step_record_complete_failure(self) -> None:
        step = StepRecord(
            step_index=2,
            role=AgentRole.QA,
            task_description="Run tests",
        )
        res = ToolResult.fail(error="Assertion failed")
        step.complete(tool_result=res)

        assert step.status == StepStatus.FAILURE
        assert step.error == "Assertion failed"


class TestAgentState:
    """AgentState working memory and execution history tests."""

    def test_initial_state(self) -> None:
        state = AgentState(mission_goal="Build auth service")
        assert state.status == MissionStatus.PENDING
        assert state.current_step_index == 0
        assert len(state.step_history) == 0
        assert state.consecutive_failures == 0
        assert state.is_terminal is False

    def test_add_and_complete_step(self) -> None:
        state = AgentState(mission_goal="Build auth service")
        step = state.add_step(
            role=AgentRole.DEV,
            task_description="Create model",
            tool_name="write_file",
            tool_args={"path": "model.py", "content": "class User: pass"},
        )
        assert state.current_step_index == 1
        assert state.active_role == AgentRole.DEV
        assert step.status == StepStatus.RUNNING

        completed = state.complete_current_step(tool_result=ToolResult.ok(output="Done"))
        assert completed.status == StepStatus.SUCCESS
        assert state.consecutive_failures == 0
        assert state.get_last_step() == completed
        assert state.get_last_successful_step() == completed

    def test_consecutive_failure_tracking(self) -> None:
        state = AgentState(mission_goal="Fix bug")
        # Step 1 fails
        state.add_step(role=AgentRole.DEV, task_description="Attempt 1")
        state.complete_current_step(tool_result=ToolResult.fail(error="Err 1"))
        assert state.consecutive_failures == 1

        # Step 2 fails
        state.add_step(role=AgentRole.DEV, task_description="Attempt 2")
        state.complete_current_step(tool_result=ToolResult.fail(error="Err 2"))
        assert state.consecutive_failures == 2

        # Step 3 succeeds -> resets counter
        state.add_step(role=AgentRole.DEV, task_description="Attempt 3")
        state.complete_current_step(tool_result=ToolResult.ok(output="Fixed"))
        assert state.consecutive_failures == 0

    def test_state_serialization_roundtrip(self) -> None:
        state = AgentState(
            mission_goal="Test serialization",
            context_variables={"repo_name": "AegisOS", "priority": 1},
        )
        state.add_step(role=AgentRole.CTO, task_description="Plan architecture")
        state.complete_current_step(tool_result=ToolResult.ok(output="Plan created"))

        json_str = state.model_dump_json()
        restored = AgentState.model_validate_json(json_str)

        assert restored.session_id == state.session_id
        assert restored.mission_goal == state.mission_goal
        assert restored.context_variables["repo_name"] == "AegisOS"
        assert len(restored.step_history) == 1
        assert restored.step_history[0].role == AgentRole.CTO
        assert restored.step_history[0].status == StepStatus.SUCCESS

    def test_clone_creates_deep_copy(self) -> None:
        state = AgentState(mission_goal="Clone test")
        state.context_variables["data"] = [1, 2, 3]
        cloned = state.clone()

        assert cloned.session_id == state.session_id
        cloned.context_variables["data"].append(4)
        assert len(state.context_variables["data"]) == 3


class TestMissionDAG:
    """MissionDAG planning graph and cycle detection tests."""

    def test_valid_dag_topological_flow(self) -> None:
        dag = MissionDAG()
        dag.add_node(DAGNode(node_id="plan", role=AgentRole.CTO, task="Create Plan"))
        dag.add_node(DAGNode(node_id="code", role=AgentRole.DEV, task="Write Code"))
        dag.add_node(DAGNode(node_id="test", role=AgentRole.QA, task="Run Tests"))

        dag.add_edge("plan", "code", condition="on_success")
        dag.add_edge("code", "test", condition="on_success")

        entries = dag.get_entry_nodes()
        assert len(entries) == 1
        assert entries[0].node_id == "plan"

        next_nodes = dag.get_next_nodes("plan")
        assert len(next_nodes) == 1
        assert next_nodes[0].node_id == "code"

    def test_cycle_detection_raises_error(self) -> None:
        dag = MissionDAG()
        dag.add_node(DAGNode(node_id="A", role=AgentRole.DEV, task="Task A"))
        dag.add_node(DAGNode(node_id="B", role=AgentRole.QA, task="Task B"))
        dag.add_node(DAGNode(node_id="C", role=AgentRole.DEV, task="Task C"))

        dag.add_edge("A", "B")
        dag.add_edge("B", "C")

        # Adding edge C -> A creates a cycle: A -> B -> C -> A
        with pytest.raises(CycleDetectedError) as exc_info:
            dag.add_edge("C", "A")

        assert "Cycle detected" in str(exc_info.value)
        assert "A" in str(exc_info.value)

    def test_self_cycle_detection(self) -> None:
        dag = MissionDAG()
        dag.add_node(DAGNode(node_id="loop", role=AgentRole.DEV, task="Self loop"))

        with pytest.raises(CycleDetectedError):
            dag.add_edge("loop", "loop")
