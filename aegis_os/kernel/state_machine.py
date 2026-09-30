from typing import Any, Optional
from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.events import EventBus,MissionStatusChangedEvent,StateTransitionEvent,StepCompletedEvent,StepStartedEvent
from aegis_os.kernel.exceptions import InvalidTransitionError,MaxStepsExceededError,StagnationError
from aegis_os.kernel.state import AgentRole,AgentState,MissionStatus,StepRecord,StepStatus
from aegis_os.tools.base import ToolResult

class StateMachine:
    """
    Deterministic state machine and execution coordinator.
    Enforces the central rule: the LLM decides intent; the state machine
    governs progression, isolation, budget enforcement, and rollbacks.
    """
    def __init__(self,state: AgentState,checkpoint_store: Optional[CheckpointStore] = None,event_bus: Optional[EventBus] = None,) -> None:
        self.state=state
        self.checkpoint_store=checkpoint_store
        self.event_bus=event_bus

    def start_mission(self) -> None:
        """Move mission from PENDING to RUNNING."""
        if self.state.status != MissionStatus.PENDING:
            raise InvalidTransitionError(from_state=self.state.status.value,to_state=MissionStatus.RUNNING.value,reason="Mission can only be started from PENDING state.")

        old_status=self.state.status
        self.state.status=MissionStatus.RUNNING
        self._emit(MissionStatusChangedEvent(session_id=self.state.session_id,old_status=old_status,new_status=self.state.status,goal=self.state.mission_goal))
        self._persist()

    def transition_role(self, new_role: AgentRole) -> None:
        """Shift active execution to a new autonomous agent role."""
        if self.state.is_terminal:
            raise InvalidTransitionError(
                from_state=self.state.status.value,
                to_state=new_role.value,
                reason="Cannot transition roles on a terminated mission.",
            )

        old_role=self.state.active_role
        self.state.active_role=new_role
        self._emit(StateTransitionEvent(session_id=self.state.session_id,from_role=old_role,to_role=new_role,step_index=self.state.current_step_index))
        self._persist()

    def begin_step(self,task_description: str,role: Optional[AgentRole] = None,tool_name: Optional[str] = None,tool_args: Optional[dict[str, Any]] = None) -> StepRecord:
        """
        Allocate and initiate a new step in the mission.
        Enforces execution budgets and stagnation limits before proceeding.
        """
        if self.state.is_terminal:
            raise InvalidTransitionError(from_state=self.state.status.value,to_state="BEGIN_STEP",reason="Cannot execute steps on a terminated mission.")
        if self.state.current_step_index >= self.state.max_steps:
            self.fail_mission("Max execution step budget exceeded.")
            raise MaxStepsExceededError(
                current_steps=self.state.current_step_index,
                max_steps=self.state.max_steps,
            )

        if self.state.consecutive_failures >= self.state.stagnation_threshold:
            current_role=(role or self.state.active_role or AgentRole.CTO).value
            self.fail_mission("Execution halted due to repeated agent stagnation.")
            raise StagnationError(
                failure_count=self.state.consecutive_failures,
                threshold=self.state.stagnation_threshold,
                role=current_role,
            )

        target_role=role or self.state.active_role or AgentRole.CTO
        step=self.state.add_step(role=target_role,task_description=task_description,tool_name=tool_name,tool_args=tool_args)
        self._emit(StepStartedEvent(session_id=self.state.session_id,step=step))
        self._persist()
        return step

    def end_step(self,tool_result: Optional[ToolResult] = None,error: Optional[str] = None,status: Optional[StepStatus] = None,) -> StepRecord:
        """
        Complete the currently running step and evaluate status outcomes.
        """
        completed_step=self.state.complete_current_step(tool_result=tool_result,error=error,status=status)
        self._emit(StepCompletedEvent(session_id=self.state.session_id,step=completed_step))
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

        old_status=self.state.status
        self.state.status=MissionStatus.PAUSED

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

        old_status=self.state.status
        self.state.status=MissionStatus.RUNNING

        self._emit(
            MissionStatusChangedEvent(
                session_id=self.state.session_id,
                old_status=old_status,
                new_status=self.state.status,
                goal=self.state.mission_goal,
            )
        )
        self._persist()

    def abort_mission(self,reason: str = "Aborted by operator.") -> None:
        """Abort execution immediately."""
        old_status=self.state.status
        self.state.status=MissionStatus.ABORTED
        self.state.context_variables["abort_reason"]=reason

        self._emit(
            MissionStatusChangedEvent(
                session_id=self.state.session_id,
                old_status=old_status,
                new_status=self.state.status,
                goal=self.state.mission_goal,
            )
        )
        self._persist()

    def rollback(self,target_step_index: int) -> AgentState:
        """Revert mission state to a prior step snapshot using CheckpointStore."""
        if not self.checkpoint_store:
            raise RuntimeError("Cannot rollback without a configured CheckpointStore.")

        restored_state=self.checkpoint_store.rollback_to_step(session_id=self.state.session_id,target_step_index=target_step_index)
        self.state=restored_state

        self._emit(
            MissionStatusChangedEvent(
                session_id=self.state.session_id,
                old_status=MissionStatus.RUNNING,
                new_status=self.state.status,
                goal=self.state.mission_goal,
            )
        )
        return self.state

    def _emit(self,event: Any) -> None:
        if self.event_bus:
            self.event_bus.publish(event)

    def _persist(self) -> None:
        if self.checkpoint_store:
            self.checkpoint_store.save_checkpoint(self.state)

from pathlib import Path
import time
from typing import Optional
import uuid
from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.events import EventBus
from aegis_os.kernel.state import AgentRole,AgentState,DAGNode,MissionDAG,MissionStatus

from aegis_os.kernel.state import MissionPhase,MissionSummary,RepairCycleRecord


def _resolve_role(role_str:str)->AgentRole:
    """Normalize an agent name or role string to an AgentRole enum."""
    normalized=role_str.strip().upper()
    if "DEV" in normalized:
        return AgentRole.DEV
    elif "QA" in normalized:
        return AgentRole.QA
    elif "SEC" in normalized:
        return AgentRole.SEC
    elif "OPS" in normalized:
        return AgentRole.OPS
    elif "CTO" in normalized:
        return AgentRole.CTO
    return AgentRole.DEV

class MissionOrchestrator:
    """Coordinates planning, execution, verification, repair, and finalization of missions."""

    def __init__(
        self,
        workspace_root: Optional[Path]=None,
        llm_provider: str="openai",
        llm_model: Optional[str]=None,
        state_machine: Optional[StateMachine]=None,
        checkpoint_store: Optional[CheckpointStore]=None,
        event_bus: Optional[EventBus]=None,
        max_repair_cycles: int=3,
        max_steps: int=50,
        cto: Optional[AegisCTO]=None,
        dev: Optional[AegisDev]=None,
        qa: Optional[AegisQA]=None,
        sec: Optional[AegisSec]=None,
        ops: Optional[AegisOps]=None,
    ) -> None:
        self.workspace_root=Path(workspace_root) if workspace_root else Path.cwd()
        self.llm_provider=llm_provider
        self.llm_model=llm_model
        self._custom_state_machine=state_machine
        self.state_machine:Optional[StateMachine]=state_machine
        self.checkpoint_store=checkpoint_store
        self.event_bus=event_bus
        self.max_repair_cycles=max_repair_cycles
        self.max_steps=max_steps

        self.cto = cto
        self.dev = dev
        self.qa = qa
        self.sec = sec
        self.ops = ops

    def _initialize_agents(self) -> None:
        from aegis_os.agents.cto.agent import AegisCTO
        from aegis_os.agents.dev.agent import AegisDev
        from aegis_os.agents.qa.agent import AegisQA
        from aegis_os.agents.sec.agent import AegisSec
        from aegis_os.agents.ops.agent import AegisOps
        
        if not self.cto: self.cto = AegisCTO(workspace_root=self.workspace_root,llm_provider=self.llm_provider,llm_model=self.llm_model)
        if not self.dev: self.dev = AegisDev(workspace_root=self.workspace_root,llm_provider=self.llm_provider,llm_model=self.llm_model)
        if not self.qa: self.qa = AegisQA(workspace_root=self.workspace_root,llm_provider=self.llm_provider,llm_model=self.llm_model)
        if not self.sec: self.sec = AegisSec(workspace_root=self.workspace_root,llm_provider=self.llm_provider,llm_model=self.llm_model)
        if not self.ops: self.ops = AegisOps(workspace_root=self.workspace_root,llm_provider=self.llm_provider,llm_model=self.llm_model)

    def _sync_agents_with_state_machine(self,sm:StateMachine)->None:
        """Ensure all department agents share the active mission state machine."""
        for agent in (self.cto,self.dev,self.qa,self.sec,self.ops):
            if agent and hasattr(agent,"state_machine"):
                agent.state_machine=sm

    def _get_agent_for_role(self,role:AgentRole):
        if role==AgentRole.CTO:
            return self.cto
        elif role==AgentRole.DEV:
            return self.dev
        elif role==AgentRole.QA:
            return self.qa
        elif role==AgentRole.SEC:
            return self.sec
        elif role==AgentRole.OPS:
            return self.ops
        return self.dev

    def execute_mission(self,goal:str)->MissionSummary:
        """
        Execute an end-to-end engineering mission through all department phases.
        Args:
            goal: High-level engineering objective.
        Returns:
            MissionSummary with final status,reports,and repair records.
        """
        start_time=time.time()
        plan:Optional[MissionPlan]=None
        tasks_executed:list[str]=[]
        repair_cycles:int=0
        repair_history:list[RepairCycleRecord]=[]
        qa_report:Optional[TestReport]=None
        sec_report:Optional[SecurityReport]=None
        ops_report:Optional[str]=None

        if self._custom_state_machine is not None:
            self.state_machine=self._custom_state_machine
        else:
            state=AgentState(
                session_id=str(uuid.uuid4()),
                mission_goal=goal,
                status=MissionStatus.PENDING,
                max_steps=self.max_steps,
            )
            self.state_machine=StateMachine(
                state=state,
                checkpoint_store=self.checkpoint_store,
                event_bus=self.event_bus,
            )

        self.state_machine._persist()

        try:
            self._initialize_agents()
            self._sync_agents_with_state_machine(self.state_machine)
            if self.state_machine.state.status==MissionStatus.PENDING:
                self.state_machine.start_mission()

            self.state_machine.state.context_variables["phase"]=MissionPhase.PLANNING.value
            self.state_machine.transition_role(AgentRole.CTO)

            plan=self.cto.plan_mission(goal)
            self.state_machine.state.context_variables["mission_plan"]=plan.model_dump()

            dag=MissionDAG()
            for task in plan.tasks:
                dag.add_node(
                    DAGNode(
                        node_id=task.task_id,
                        role=_resolve_role(task.assigned_to),
                        task=task.description,
                        metadata={
                            "title": task.title,
                            "priority": task.priority,
                            "acceptance_criteria": task.acceptance_criteria,
                        }
                    )
                )

            for task in plan.tasks:
                for dep_id in task.depends_on:
                    if dep_id in dag.nodes:
                        dag.add_edge(from_node=dep_id, to_node=task.task_id)

            sorted_nodes=dag.topological_sort()
            self.state_machine.state.context_variables["dag"]=dag.model_dump()

            self.state_machine.state.context_variables["phase"]=MissionPhase.EXECUTION.value

            for node in sorted_nodes:
                if self.state_machine.state.is_terminal:
                    break

                agent=self._get_agent_for_role(node.role)
                self.state_machine.transition_role(node.role)

                task_instruction = (
                    f"Execute Planned Task [{node.node_id}]: {node.metadata.get('title', '')}\n"
                    f"Description: {node.task}\n"
                    f"Acceptance Criteria: {node.metadata.get('acceptance_criteria', [])}"
                )
                agent.run(task_instruction)
                tasks_executed.append(node.node_id)

            self.state_machine.state.context_variables["phase"]=MissionPhase.VERIFICATION.value

            while not self.state_machine.state.is_terminal:
                self.state_machine.transition_role(AgentRole.QA)
                qa_report = self.qa.run_and_report()
                self.state_machine.state.context_variables["qa_report"] = qa_report.model_dump()

                self.state_machine.transition_role(AgentRole.SEC)
                sec_report = self.sec.audit()
                self.state_machine.state.context_variables["sec_report"] = sec_report.model_dump()

                qa_failed = (qa_report.failed > 0) or (qa_report.errors > 0)
                sec_failed = (sec_report.summary.critical > 0) or (sec_report.summary.high > 0)

                if not qa_failed and not sec_failed:
                    if repair_history:
                        repair_history[-1].resolved=True
                    break
                issues: list[str]=[]
                triggers: list[str]=[]

                if qa_failed:
                    triggers.append("QA_FAILURES")
                    for finding in qa_report.findings:
                        issues.append(
                            f"QA [{finding.test_name}]: {finding.error_message} "
                            f"(Hypothesis: {finding.root_cause_hypothesis})"
                        )
                    if not issues:
                        issues.append(
                            f"QA: {qa_report.failed} test(s) failed, {qa_report.errors} error(s)."
                        )

                if sec_failed:
                    triggers.append("SECURITY_VULNERABILITIES")
                    for sf in sec_report.findings:
                        if sf.severity in ("CRITICAL", "HIGH"):
                            issues.append(
                                f"SEC [{sf.severity}] {sf.category} at {sf.file}:{sf.line} - "
                                f"{sf.description}. Remediation: {sf.remediation}"
                            )

                if repair_cycles>=self.max_repair_cycles:
                    fail_msg=(
                        f"Closed-loop repair budget exceeded ({self.max_repair_cycles} cycles). "
                        f"Remaining unresolved issues: {len(issues)}"
                    )
                    self.state_machine.fail_mission(fail_msg)
                    repair_history.append(
                        RepairCycleRecord(
                            cycle_index=repair_cycles + 1,
                            trigger="+".join(triggers),
                            issues_detected=issues,
                            dev_patch_summary=None,
                            resolved=False,
                        )
                    )
                    break

                repair_cycles+=1
                self.state_machine.state.context_variables["phase"]=MissionPhase.REPAIR.value
                self.state_machine.transition_role(AgentRole.DEV)

                repair_prompt=(
                    f"## Verification Feedback (Repair Cycle {repair_cycles}/{self.max_repair_cycles})\n"
                    f"The following automated verification issues were detected:\n"
                    + "\n".join(f"- {issue}" for issue in issues)
                    + "\n\nPlease analyze root causes, modify the code to resolve these failures, and commit the fixes."
                )
                dev_patch_summary=self.dev.run(repair_prompt)
                repair_history.append(
                    RepairCycleRecord(
                        cycle_index=repair_cycles,
                        trigger="+".join(triggers),
                        issues_detected=issues,
                        dev_patch_summary=dev_patch_summary,
                        resolved=False,
                    )
                )

            if not self.state_machine.state.is_terminal:
                self.state_machine.state.context_variables["phase"]=MissionPhase.OPERATIONS.value
                self.state_machine.transition_role(AgentRole.OPS)
                ops_report=self.ops.health_check()
                self.state_machine.state.context_variables["ops_report"]=ops_report

            self.state_machine.state.context_variables["phase"]=MissionPhase.FINALIZATION.value
            if not self.state_machine.state.is_terminal:
                self.state_machine.complete_mission(
                    reason=f"Mission '{goal}' completed successfully through all departments."
                )

        except Exception as exc:
            if not self.state_machine.state.is_terminal:
                self.state_machine.fail_mission(f"Mission failed with error: {exc}")
            duration = round(time.time() - start_time, 2)
            return MissionSummary(
                session_id=self.state_machine.state.session_id,
                goal=goal,
                status=self.state_machine.state.status,
                plan=plan,
                total_steps=self.state_machine.state.current_step_index,
                tasks_executed=tasks_executed,
                repair_cycles=repair_cycles,
                repair_history=repair_history,
                qa_report=qa_report,
                sec_report=sec_report,
                ops_report=ops_report,
                duration_seconds=duration,
                error=str(exc),
            )

        duration=round(time.time()-start_time,2)
        return MissionSummary(
            session_id=self.state_machine.state.session_id,
            goal=goal,
            status=self.state_machine.state.status,
            plan=plan,
            total_steps=self.state_machine.state.current_step_index,
            tasks_executed=tasks_executed,
            repair_cycles=repair_cycles,
            repair_history=repair_history,
            qa_report=qa_report,
            sec_report=sec_report,
            ops_report=ops_report,
            duration_seconds=duration,
        )



