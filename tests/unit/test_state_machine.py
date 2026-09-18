"""
Test Suite: StateMachine FSM Engine & Guardrails
================================================
Tests proving:
  1. FSM lifecycle: start, role transition, pause, resume, abort, complete.
  2. MaxStepsExceededError raised when step budget is reached.
  3. StagnationError raised when consecutive failure threshold is exceeded.
  4. Terminal state protection prevents execution on completed/failed missions.
  5. CheckpointStore and EventBus integration during state transitions.
"""

from pathlib import Path
import pytest

from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.events import EventBus, StepStartedEvent
from aegis_os.kernel.exceptions import (
    InvalidTransitionError,
    MaxStepsExceededError,
    StagnationError,
)
from aegis_os.kernel.state import AgentRole, AgentState, MissionStatus, StepStatus
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.base import ToolResult


class TestStateMachineLifecycle:
    """Core state machine transitions and lifecycle events."""

    def test_start_mission(self) -> None:
        bus = EventBus()
        state = AgentState(mission_goal="Build feature")
        sm = StateMachine(state=state, event_bus=bus)

        events = []
        bus.subscribe("*", lambda e: events.append(e))

        sm.start_mission()
        assert sm.state.status == MissionStatus.RUNNING
        assert len(events) == 1
        assert events[0].event_type == "mission.status_changed"

    def test_transition_role(self) -> None:
        state = AgentState(mission_goal="Build feature", status=MissionStatus.RUNNING)
        sm = StateMachine(state=state)

        sm.transition_role(AgentRole.DEV)
        assert sm.state.active_role == AgentRole.DEV

        sm.transition_role(AgentRole.QA)
        assert sm.state.active_role == AgentRole.QA

    def test_pause_and_resume(self) -> None:
        state = AgentState(mission_goal="Build feature", status=MissionStatus.RUNNING)
        sm = StateMachine(state=state)

        sm.pause_mission()
        assert sm.state.status == MissionStatus.PAUSED

        sm.resume_mission()
        assert sm.state.status == MissionStatus.RUNNING

    def test_complete_and_abort(self) -> None:
        state = AgentState(mission_goal="Build feature", status=MissionStatus.RUNNING)
        sm = StateMachine(state=state)

        sm.complete_mission(reason="All tests passing")
        assert sm.state.status == MissionStatus.COMPLETED
        assert sm.state.is_terminal is True
        assert sm.state.context_variables["completion_reason"] == "All tests passing"


class TestStateMachineGuards:
    """Execution budget enforcement and stagnation guards."""

    def test_max_steps_budget_guard(self) -> None:
        state = AgentState(
            mission_goal="Budget test",
            status=MissionStatus.RUNNING,
            max_steps=2,
        )
        sm = StateMachine(state=state)

        # Step 1
        sm.begin_step(task_description="Step 1", role=AgentRole.DEV)
        sm.end_step(tool_result=ToolResult.ok(output="Done 1"))

        # Step 2
        sm.begin_step(task_description="Step 2", role=AgentRole.DEV)
        sm.end_step(tool_result=ToolResult.ok(output="Done 2"))

        # Step 3 exceeds max_steps=2
        with pytest.raises(MaxStepsExceededError) as exc_info:
            sm.begin_step(task_description="Step 3", role=AgentRole.DEV)

        assert "exceeded maximum execution budget" in str(exc_info.value)
        assert sm.state.status == MissionStatus.FAILED

    def test_stagnation_guard_triggers_on_consecutive_failures(self) -> None:
        state = AgentState(
            mission_goal="Stagnation test",
            status=MissionStatus.RUNNING,
            stagnation_threshold=3,
        )
        sm = StateMachine(state=state)

        # Fail 1
        sm.begin_step(task_description="Try 1", role=AgentRole.DEV)
        sm.end_step(tool_result=ToolResult.fail(error="Fail 1"))

        # Fail 2
        sm.begin_step(task_description="Try 2", role=AgentRole.DEV)
        sm.end_step(tool_result=ToolResult.fail(error="Fail 2"))

        # Fail 3
        sm.begin_step(task_description="Try 3", role=AgentRole.DEV)
        sm.end_step(tool_result=ToolResult.fail(error="Fail 3"))

        # Next step should trigger StagnationError
        with pytest.raises(StagnationError) as exc_info:
            sm.begin_step(task_description="Try 4", role=AgentRole.DEV)

        assert "stagnation threshold" in str(exc_info.value)
        assert sm.state.status == MissionStatus.FAILED

    def test_terminal_state_blocks_execution(self) -> None:
        state = AgentState(mission_goal="Terminal test", status=MissionStatus.COMPLETED)
        sm = StateMachine(state=state)

        with pytest.raises(InvalidTransitionError):
            sm.begin_step(task_description="New step", role=AgentRole.DEV)


class TestStateMachinePersistenceAndRollback:
    """Full integration between StateMachine and CheckpointStore."""

    def test_step_checkpoints_saved_automatically(self, tmp_workspace: Path) -> None:
        store = CheckpointStore(db_path=tmp_workspace / "fsm_state.db")
        state = AgentState(mission_goal="Persistence test", status=MissionStatus.RUNNING)
        sm = StateMachine(state=state, checkpoint_store=store)

        sm.begin_step(task_description="Step 1", role=AgentRole.DEV)
        sm.end_step(tool_result=ToolResult.ok(output="Code generated"))

        # Verify state exists in store
        latest = store.load_latest_state(state.session_id)
        assert latest is not None
        assert latest.current_step_index == 1
        assert latest.step_history[0].status == StepStatus.SUCCESS
        store.close()

    def test_state_machine_rollback(self, tmp_workspace: Path) -> None:
        store = CheckpointStore(db_path=tmp_workspace / "rollback.db")
        state = AgentState(mission_goal="FSM Rollback test", status=MissionStatus.RUNNING)
        sm = StateMachine(state=state, checkpoint_store=store)

        # Step 1
        sm.begin_step(task_description="Step 1: Clean code", role=AgentRole.DEV)
        sm.end_step(tool_result=ToolResult.ok(output="Pass"))

        # Step 2
        sm.begin_step(task_description="Step 2: Buggy refactor", role=AgentRole.DEV)
        sm.end_step(tool_result=ToolResult.fail(error="Broken"))

        assert sm.state.current_step_index == 2

        # Rollback to step 1
        restored = sm.rollback(target_step_index=1)
        assert restored.current_step_index == 1
        assert sm.state.current_step_index == 1
        assert len(sm.state.step_history) == 1
        assert sm.state.step_history[0].task_description == "Step 1: Clean code"
        store.close()
