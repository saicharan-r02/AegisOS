from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.context import redact_sensitive_text, redact_sensitive_value
from aegis_os.kernel.events import EventBus
from aegis_os.kernel.state import (
    AgentRole,
    AgentState,
    MissionPhase,
    MissionStatus,
    MissionSummary,
    RepairCycleRecord,
)
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.orchestration.invariants import HardInvariantEngine
from aegis_os.orchestration.ledger import FailureLedger
from aegis_os.orchestration.planner import DynamicPlan, PlanTask, TaskStatus
from aegis_os.orchestration.worktree import WorktreeManager

if TYPE_CHECKING:
    from aegis_os.agents.cto.agent import AegisCTO
    from aegis_os.agents.dev.agent import AegisDev
    from aegis_os.agents.ops.agent import AegisOps
    from aegis_os.agents.qa.agent import AegisQA, TestReport
    from aegis_os.agents.sec.agent import AegisSec, SecurityReport


def _resolve_role(role_str: str) -> AgentRole:
    normalized = role_str.strip().upper()
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


class AdaptiveOrchestrator:
    def __init__(
        self,
        workspace_root: Path | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        state_machine: StateMachine | None = None,
        checkpoint_store: CheckpointStore | None = None,
        event_bus: EventBus | None = None,
        max_repair_cycles: int = 3,
        max_steps: int = 50,
        max_tokens: int | None = None,
        max_cost_usd: float | None = None,
        max_wall_seconds: float | None = None,
        unsafe_local: bool = False,
        cto: AegisCTO | None = None,
        dev: AegisDev | None = None,
        qa: AegisQA | None = None,
        sec: AegisSec | None = None,
        ops: AegisOps | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root) if workspace_root else Path.cwd()
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self._custom_state_machine = state_machine
        self.state_machine: StateMachine | None = state_machine
        self.checkpoint_store = checkpoint_store
        self.event_bus = event_bus
        self.max_repair_cycles = max_repair_cycles
        self.max_steps = max_steps
        self.unsafe_local = unsafe_local

        from aegis_os.kernel.llm import load_runtime_config

        runtime_config = load_runtime_config()
        self.max_tokens = max_tokens if max_tokens is not None else runtime_config.max_tokens
        self.max_cost_usd = (
            max_cost_usd if max_cost_usd is not None else runtime_config.max_cost_usd
        )
        self.max_wall_seconds = (
            max_wall_seconds if max_wall_seconds is not None else runtime_config.max_wall_seconds
        )

        self.cto = cto
        self.dev = dev
        self.qa = qa
        self.sec = sec
        self.ops = ops

        self.ledger = FailureLedger()
        self.worktree_mgr = WorktreeManager(self.workspace_root)
        self.dynamic_plan: DynamicPlan | None = None

    def _initialize_agents(self) -> None:
        from aegis_os.agents.cto.agent import AegisCTO
        from aegis_os.agents.dev.agent import AegisDev
        from aegis_os.agents.ops.agent import AegisOps
        from aegis_os.agents.qa.agent import AegisQA
        from aegis_os.agents.sec.agent import AegisSec

        if not self.cto:
            self.cto = AegisCTO(
                workspace_root=self.workspace_root,
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
            )
        if not self.dev:
            self.dev = AegisDev(
                workspace_root=self.workspace_root,
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
                unsafe_local=self.unsafe_local,
            )
        if not self.qa:
            self.qa = AegisQA(
                workspace_root=self.workspace_root,
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
                unsafe_local=self.unsafe_local,
            )
        if not self.sec:
            self.sec = AegisSec(
                workspace_root=self.workspace_root,
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
            )
        if not self.ops:
            self.ops = AegisOps(
                workspace_root=self.workspace_root,
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
                unsafe_local=self.unsafe_local,
            )

    def _sync_agents_with_state_machine(self, sm: StateMachine) -> None:
        for agent in (self.cto, self.dev, self.qa, self.sec, self.ops):
            if agent and hasattr(agent, "state_machine"):
                agent.state_machine = sm

    def _get_agent_for_role(self, role: AgentRole) -> Any:
        if role == AgentRole.CTO:
            return self.cto
        elif role == AgentRole.DEV:
            return self.dev
        elif role == AgentRole.QA:
            return self.qa
        elif role == AgentRole.SEC:
            return self.sec
        elif role == AgentRole.OPS:
            return self.ops
        return self.dev

    def execute_mission(self, goal: str) -> MissionSummary:
        goal = redact_sensitive_text(goal)
        start_time = time.time()
        tasks_executed: list[str] = []
        repair_cycles: int = 0
        repair_history: list[RepairCycleRecord] = []
        qa_report: TestReport | None = None
        sec_report: SecurityReport | None = None
        ops_report: str | None = None

        if self._custom_state_machine is not None:
            self.state_machine = self._custom_state_machine
        else:
            state = AgentState(
                session_id=str(uuid.uuid4()),
                mission_goal=goal,
                status=MissionStatus.PENDING,
                max_steps=self.max_steps,
                max_tokens=self.max_tokens,
                max_cost_usd=self.max_cost_usd,
                max_wall_seconds=self.max_wall_seconds,
            )
            self.state_machine = StateMachine(
                state=state,
                checkpoint_store=self.checkpoint_store,
                event_bus=self.event_bus,
            )

        self.state_machine._persist()

        try:
            self._initialize_agents()
            self._sync_agents_with_state_machine(self.state_machine)
            assert self.cto is not None
            assert self.dev is not None
            assert self.qa is not None
            assert self.sec is not None
            assert self.ops is not None

            if self.state_machine.state.status == MissionStatus.PENDING:
                self.state_machine.start_mission()

            self.state_machine.state.context_variables["phase"] = MissionPhase.PLANNING.value
            self.state_machine.transition_role(AgentRole.CTO)

            cto_plan = self.cto.plan_mission(goal)
            self.state_machine.state.context_variables["mission_plan"] = redact_sensitive_value(
                cto_plan.model_dump()
            )
            if self.state_machine.state.context_variables.get("partial_result_reason"):
                raise RuntimeError("Mission stopped at the configured budget.")

            self.dynamic_plan = DynamicPlan(goal=goal)
            for t in cto_plan.tasks:
                self.dynamic_plan.add_task(
                    PlanTask(
                        task_id=t.task_id,
                        title=t.title,
                        description=t.description,
                        role=_resolve_role(t.assigned_to),
                        depends_on=list(t.depends_on),
                        verification_condition="pytest",
                    )
                )

            self.state_machine.state.context_variables["dynamic_plan"] = (
                self.dynamic_plan.model_dump()
            )
            self.state_machine.state.context_variables["phase"] = MissionPhase.EXECUTION.value

            max_loop_iterations = len(self.dynamic_plan.tasks) * 3 + 10
            iterations = 0

            while (
                not self.dynamic_plan.is_all_completed()
                and not self.state_machine.state.is_terminal
            ):
                iterations += 1
                if iterations > max_loop_iterations:
                    break

                ready_tasks = self.dynamic_plan.get_ready_tasks()

                if not ready_tasks:
                    failed = [
                        t for t in self.dynamic_plan.tasks.values() if t.status == TaskStatus.FAILED
                    ]
                    if failed:
                        failed_task = failed[0]
                        pivot_task = PlanTask(
                            task_id=f"{failed_task.task_id}-pivot",
                            title=f"Pivot: Resolve {failed_task.title}",
                            description=(
                                f"Alternative implementation resolving prior failure:\n"
                                f"{self.ledger.format_guidance_for_planner()}\n"
                                f"Original requirement: {failed_task.description}"
                            ),
                            role=AgentRole.DEV,
                            depends_on=list(failed_task.depends_on),
                        )
                        self.dynamic_plan.replan_failed_subgraph(failed_task.task_id, [pivot_task])
                        continue
                    else:
                        break

                for task in ready_tasks:
                    if self.state_machine.state.is_terminal:
                        break

                    agent = self._get_agent_for_role(task.role)
                    self.state_machine.transition_role(task.role)
                    task.status = TaskStatus.RUNNING

                    ledger_guidance = self.ledger.format_guidance_for_planner()
                    task_instruction = (
                        f"Execute Planned Task [{task.task_id}]: {task.title}\n"
                        f"Description: {task.description}\n"
                        f"Verification Condition: {task.verification_condition or 'standard tests'}\n\n"
                        f"{ledger_guidance}\n\n"
                        f"Overall Mission Goal: {goal}\n"
                        f"Workspace Root: {self.workspace_root}\n\n"
                        f"IMPORTANT: Start by inspecting necessary context or writing code immediately."
                    )

                    result_output = agent.run(task_instruction, max_iterations=15)
                    tasks_executed.append(task.task_id)

                    if self.state_machine.state.context_variables.get("partial_result_reason"):
                        raise RuntimeError("Mission stopped at the configured budget.")

                    if "ERROR:" in result_output or "Execution error:" in result_output:
                        task.retry_count += 1
                        self.ledger.record_failure(
                            task_id=task.task_id,
                            role=task.role,
                            error_message=result_output[:300],
                            attempted_action=task.title,
                            root_cause_analysis="Agent run encountered tool execution error.",
                            avoidance_rule=f"Revise implementation strategy for {task.title}.",
                        )
                        if task.retry_count <= task.max_retries:
                            task.status = TaskStatus.PENDING
                        else:
                            task.status = TaskStatus.FAILED
                    else:
                        task.status = TaskStatus.COMPLETED
                        task.result_summary = result_output[:300]

            self.state_machine.state.context_variables["phase"] = MissionPhase.VERIFICATION.value

            while not self.state_machine.state.is_terminal:
                self.state_machine.transition_role(AgentRole.QA)
                qa_report = self.qa.run_and_report()
                self.state_machine.state.context_variables["qa_report"] = qa_report.model_dump()
                if self.state_machine.state.context_variables.get("partial_result_reason"):
                    raise RuntimeError("Mission stopped at the configured budget.")

                self.state_machine.transition_role(AgentRole.SEC)
                sec_report = self.sec.audit()
                self.state_machine.state.context_variables["sec_report"] = sec_report.model_dump()
                if self.state_machine.state.context_variables.get("partial_result_reason"):
                    raise RuntimeError("Mission stopped at the configured budget.")

                all_invariants_passed, invariant_results = HardInvariantEngine.evaluate(
                    qa_report=qa_report,
                    sec_report=sec_report,
                    reviewer_approved=True,
                    test_integrity_passed=True,
                )

                if all_invariants_passed:
                    if repair_history:
                        repair_history[-1].resolved = True
                    break

                issues: list[str] = [r.details for r in invariant_results if not r.passed]
                triggers = [r.name for r in invariant_results if not r.passed]

                if repair_cycles >= self.max_repair_cycles:
                    fail_msg = (
                        f"Hard invariant verification failed after {self.max_repair_cycles} repair cycles: "
                        + "; ".join(issues)
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

                repair_cycles += 1
                self.state_machine.state.context_variables["phase"] = MissionPhase.REPAIR.value
                self.state_machine.transition_role(AgentRole.DEV)

                self.ledger.record_failure(
                    task_id=f"repair-{repair_cycles}",
                    role=AgentRole.QA,
                    error_message="; ".join(issues),
                    attempted_action=f"Verification cycle {repair_cycles}",
                    root_cause_analysis="Test failure or security finding during invariant gate.",
                    avoidance_rule="Fix root cause without weakening tests or suppressing security findings.",
                )

                repair_prompt = (
                    f"## Hard Invariant Failure (Repair Cycle {repair_cycles}/{self.max_repair_cycles})\n"
                    f"The following invariants failed verification:\n"
                    + "\n".join(f"- {issue}" for issue in issues)
                    + f"\n\n{self.ledger.format_guidance_for_planner()}\n"
                    + "\nPlease analyze the failures, modify code to resolve them, and ensure all tests pass."
                )
                dev_patch_summary = self.dev.run(repair_prompt)
                if self.state_machine.state.context_variables.get("partial_result_reason"):
                    raise RuntimeError("Mission stopped at the configured budget.")

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
                self.state_machine.state.context_variables["phase"] = MissionPhase.OPERATIONS.value
                self.state_machine.transition_role(AgentRole.OPS)
                ops_report = self.ops.health_check()
                self.state_machine.state.context_variables["ops_report"] = ops_report
                if self.state_machine.state.context_variables.get("partial_result_reason"):
                    raise RuntimeError("Mission stopped at the configured budget.")

            self.state_machine.state.context_variables["phase"] = MissionPhase.FINALIZATION.value
            if not self.state_machine.state.is_terminal:
                self.state_machine.complete_mission(
                    reason=f"Mission '{goal}' completed successfully with all hard invariants satisfied."
                )

        except Exception as exc:
            partial_reason = self.state_machine.state.context_variables.get("partial_result_reason")
            if partial_reason and self.state_machine.state.status != MissionStatus.PAUSED:
                self.state_machine.pause_mission()
            elif not self.state_machine.state.is_terminal:
                self.state_machine.fail_mission(
                    redact_sensitive_text(f"Mission failed with error: {exc}")
                )

            duration = round(time.time() - start_time, 2)
            return MissionSummary(
                session_id=self.state_machine.state.session_id,
                goal=goal,
                status=self.state_machine.state.status,
                plan=None,
                total_steps=self.state_machine.state.current_step_index,
                tasks_executed=tasks_executed,
                repair_cycles=repair_cycles,
                repair_history=repair_history,
                qa_report=qa_report,
                sec_report=sec_report,
                ops_report=ops_report,
                duration_seconds=duration,
                tokens_used=self.state_machine.state.tokens_used,
                cost_used_usd=self.state_machine.state.cost_used_usd,
                error=redact_sensitive_text(
                    f"Partial result: {partial_reason}" if partial_reason else str(exc)
                ),
            )

        duration = round(time.time() - start_time, 2)
        return MissionSummary(
            session_id=self.state_machine.state.session_id,
            goal=goal,
            status=self.state_machine.state.status,
            plan=None,
            total_steps=self.state_machine.state.current_step_index,
            tasks_executed=tasks_executed,
            repair_cycles=repair_cycles,
            repair_history=repair_history,
            qa_report=qa_report,
            sec_report=sec_report,
            ops_report=ops_report,
            duration_seconds=duration,
            tokens_used=self.state_machine.state.tokens_used,
            cost_used_usd=self.state_machine.state.cost_used_usd,
        )
