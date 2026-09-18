"""
Kernel State Machine: Deterministic FSM Engine
==============================================
Orchestrates agent state transitions, enforces execution budgets,
detects stagnation and cycles, records checkpoints, and publishes telemetry.
"""

from typing import Any, Optional

from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.events import (
    EventBus,
    MissionStatusChangedEvent,
    StateTransitionEvent,
    StepCompletedEvent,
    StepStartedEvent,
)
from aegis_os.kernel.exceptions import (
    InvalidTransitionError,
    MaxStepsExceededError,
    StagnationError,
)
from aegis_os.kernel.state import (
    AgentRole,
    AgentState,
    MissionStatus,
    StepRecord,
    StepStatus,
)
from aegis_os.tools.base import ToolResult


class StateMachine:
    """
    Deterministic state machine and execution coordinator.
    Enforces the central rule: the LLM decides intent; the state machine
    governs progression, isolation, budget enforcement, and rollbacks.
    """

    def __init__(
        self,
        state: AgentState,
        checkpoint_store: Optional[CheckpointStore] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.state = state
        self.checkpoint_store = checkpoint_store
        self.event_bus = event_bus

    def start_mission(self) -> None:
        """Move mission from PENDING to RUNNING."""
        if self.state.status != MissionStatus.PENDING:
            raise InvalidTransitionError(
                from_state=self.state.status.value,
                to_state=MissionStatus.RUNNING.value,
                reason="Mission can only be started from PENDING state.",
            )

        old_status = self.state.status
        self.state.status = MissionStatus.RUNNING

        self._emit(
            MissionStatusChangedEvent(
                session_id=self.state.session_id,
                old_status=old_status,
                new_status=self.state.status,
                goal=self.state.mission_goal,
            )
        )
        self._persist()

    def transition_role(self, new_role: AgentRole) -> None:
        """Shift active execution to a new autonomous agent role."""
        if self.state.is_terminal:
            raise InvalidTransitionError(
                from_state=self.state.status.value,
                to_state=new_role.value,
                reason="Cannot transition roles on a terminated mission.",
            )

        old_role = self.state.active_role
        self.state.active_role = new_role

        self._emit(
            StateTransitionEvent(
                session_id=self.state.session_id,
                from_role=old_role,
                to_role=new_role,
                step_index=self.state.current_step_index,
            )
        )
        self._persist()

    def begin_step(
        self,
        task_description: str,
        role: Optional[AgentRole] = None,
        tool_name: Optional[str] = None,
        tool_args: Optional[dict[str, Any]] = None,
    ) -> StepRecord:
        """
        Allocate and initiate a new step in the mission.
        Enforces execution budgets and stagnation limits before proceeding.
        """
        if self.state.is_terminal:
            raise InvalidTransitionError(
                from_state=self.state.status.value,
                to_state="BEGIN_STEP",
                reason="Cannot execute steps on a terminated mission.",
            )

        # 1. Budget enforcement (token & runaway loop guard)
        if self.state.current_step_index >= self.state.max_steps:
            self.fail_mission("Max execution step budget exceeded.")
            raise MaxStepsExceededError(
                current_steps=self.state.current_step_index,
                max_steps=self.state.max_steps,
            )

        # 2. Stagnation guard (repeated failure detection)
        if self.state.consecutive_failures >= self.state.stagnation_threshold:
            current_role = (role or self.state.active_role or AgentRole.CTO).value
            self.fail_mission("Execution halted due to repeated agent stagnation.")
            raise StagnationError(
                failure_count=self.state.consecutive_failures,
                threshold=self.state.stagnation_threshold,
                role=current_role,
            )

        # 3. Create active step
        target_role = role or self.state.active_role or AgentRole.CTO
        step = self.state.add_step(
            role=target_role,
            task_description=task_description,
            tool_name=tool_name,
            tool_args=tool_args,
        )

        self._emit(
            StepStartedEvent(
                session_id=self.state.session_id,
                step=step,
            )
        )
        self._persist()
        return step

    def end_step(
        self,
        tool_result: Optional[ToolResult] = None,
        error: Optional[str] = None,
        status: Optional[StepStatus] = None,
    ) -> StepRecord:
        """
        Complete the currently running step and evaluate status outcomes.
        """
        completed_step = self.state.complete_current_step(
            tool_result=tool_result,
            error=error,
            status=status,
        )

        self._emit(
            StepCompletedEvent(
                session_id=self.state.session_id,
                step=completed_step,
            )
        )
        self._persist()
        return completed_step

    def complete_mission(self, reason: str = "Mission goal accomplished.") -> None:
        """Conclude the mission successfully."""
        old_status = self.state.status
        self.state.status = MissionStatus.COMPLETED
        self.state.context_variables["completion_reason"] = reason

        self._emit(
            MissionStatusChangedEvent(
                session_id=self.state.session_id,
                old_status=old_status,
                new_status=self.state.status,
                goal=self.state.mission_goal,
            )
        )
        self._persist()

    def fail_mission(self, reason: str) -> None:
        """Terminate the mission with a failure status."""
        old_status = self.state.status
        self.state.status = MissionStatus.FAILED
        self.state.context_variables["failure_reason"] = reason

        self._emit(
            MissionStatusChangedEvent(
                session_id=self.state.session_id,
                old_status=old_status,
                new_status=self.state.status,
                goal=self.state.mission_goal,
            )
        )
        self._persist()

    def pause_mission(self) -> None:
        """Pause mission execution (e.g. awaiting human input)."""
        if self.state.is_terminal:
            raise InvalidTransitionError(
                from_state=self.state.status.value,
                to_state=MissionStatus.PAUSED.value,
                reason="Cannot pause a terminated mission.",
            )

        old_status = self.state.status
        self.state.status = MissionStatus.PAUSED

        self._emit(
            MissionStatusChangedEvent(
                session_id=self.state.session_id,
                old_status=old_status,
                new_status=self.state.status,
                goal=self.state.mission_goal,
            )
        )
        self._persist()

    def resume_mission(self) -> None:
        """Resume execution of a paused mission."""
        if self.state.status != MissionStatus.PAUSED:
            raise InvalidTransitionError(
                from_state=self.state.status.value,
                to_state=MissionStatus.RUNNING.value,
                reason="Can only resume from PAUSED state.",
            )

        old_status = self.state.status
        self.state.status = MissionStatus.RUNNING

        self._emit(
            MissionStatusChangedEvent(
                session_id=self.state.session_id,
                old_status=old_status,
                new_status=self.state.status,
                goal=self.state.mission_goal,
            )
        )
        self._persist()

    def abort_mission(self, reason: str = "Aborted by operator.") -> None:
        """Abort execution immediately."""
        old_status = self.state.status
        self.state.status = MissionStatus.ABORTED
        self.state.context_variables["abort_reason"] = reason

        self._emit(
            MissionStatusChangedEvent(
                session_id=self.state.session_id,
                old_status=old_status,
                new_status=self.state.status,
                goal=self.state.mission_goal,
            )
        )
        self._persist()

    def rollback(self, target_step_index: int) -> AgentState:
        """Revert mission state to a prior step snapshot using CheckpointStore."""
        if not self.checkpoint_store:
            raise RuntimeError("Cannot rollback without a configured CheckpointStore.")

        restored_state = self.checkpoint_store.rollback_to_step(
            session_id=self.state.session_id,
            target_step_index=target_step_index,
        )
        self.state = restored_state

        self._emit(
            MissionStatusChangedEvent(
                session_id=self.state.session_id,
                old_status=MissionStatus.RUNNING,
                new_status=self.state.status,
                goal=self.state.mission_goal,
            )
        )
        return self.state

    def _emit(self, event: Any) -> None:
        if self.event_bus:
            self.event_bus.publish(event)

    def _persist(self) -> None:
        if self.checkpoint_store:
            self.checkpoint_store.save_checkpoint(self.state)
