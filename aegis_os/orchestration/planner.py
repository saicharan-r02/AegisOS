"""Dynamic DAG-based plan representation with typed tasks and runtime re-planning."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from aegis_os.kernel.exceptions import CycleDetectedError
from aegis_os.kernel.state import AgentRole, DAGNode, MissionDAG


class TaskStatus(str, Enum):
    """Lifecycle state of an individual planned engineering task."""

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class PlanTask(BaseModel):
    """A typed task in the dynamic mission DAG."""

    task_id: str = Field(description="Unique identifier e.g. T1, T2")
    title: str = Field(description="Short human-readable summary")
    description: str = Field(description="Detailed instructions and acceptance criteria")
    role: AgentRole = Field(
        default=AgentRole.DEV, description="Department responsible for execution"
    )
    depends_on: list[str] = Field(default_factory=list, description="IDs of prerequisite tasks")
    inputs: dict[str, Any] = Field(
        default_factory=dict, description="Typed input requirements e.g. files, specs"
    )
    outputs: dict[str, Any] = Field(
        default_factory=dict, description="Expected and generated output artifacts"
    )
    verification_condition: str | None = Field(
        default=None, description="Explicit verification check or test command"
    )
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current execution status")
    retry_count: int = Field(
        default=0, ge=0, description="Number of times this task has been retried"
    )
    max_retries: int = Field(
        default=2, ge=0, description="Maximum retry attempts before triggering a replan"
    )
    result_summary: str | None = Field(
        default=None, description="Summary of result when completed or failed"
    )
    error: str | None = Field(default=None, description="Error explanation if failed")
    assigned_worktree: str | None = Field(
        default=None, description="Isolated git worktree path if parallelized"
    )


class DynamicPlan(BaseModel):
    """Dynamic plan DAG supporting dependency resolution, parallel groupings, and re-planning."""

    goal: str = Field(description="High-level engineering mission goal")
    tasks: dict[str, PlanTask] = Field(
        default_factory=dict, description="Mapping of task_id to PlanTask"
    )
    replan_count: int = Field(default=0, ge=0, description="Number of dynamic re-plans executed")

    def add_task(self, task: PlanTask) -> None:
        """Register a task and validate that adding it does not create dependency cycles."""
        self.tasks[task.task_id] = task
        # Verify DAG acyclicity
        self.to_dag()

    def get_task(self, task_id: str) -> PlanTask | None:
        return self.tasks.get(task_id)

    def to_dag(self) -> MissionDAG:
        """Convert current tasks to a MissionDAG and validate topological order."""
        dag = MissionDAG()
        for task in self.tasks.values():
            dag.add_node(
                DAGNode(
                    node_id=task.task_id,
                    role=task.role,
                    task=task.description,
                    metadata={"title": task.title, "verification": task.verification_condition},
                )
            )
        for task in self.tasks.values():
            for dep in task.depends_on:
                if dep in self.tasks:
                    dag.add_edge(from_node=dep, to_node=task.task_id)
        # Check cycle detection
        dag.topological_sort()
        return dag

    def get_ready_tasks(self) -> list[PlanTask]:
        """Return tasks whose dependencies are all COMPLETED and that are currently PENDING."""
        ready: list[PlanTask] = []
        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            all_deps_done = all(
                self.tasks[dep].status == TaskStatus.COMPLETED
                for dep in task.depends_on
                if dep in self.tasks
            )
            if all_deps_done:
                ready.append(task)
        return ready

    def get_parallel_groups(self) -> list[list[PlanTask]]:
        """Identify sets of tasks that have no dependencies on each other and can run concurrently."""
        ready = self.get_ready_tasks()
        if not ready:
            return []

        # Tasks that don't depend on each other can run in parallel
        groups: list[list[PlanTask]] = []
        # Group by independent sets
        current_group: list[PlanTask] = []
        for task in ready:
            if not any(
                t.task_id in task.depends_on or task.task_id in t.depends_on for t in current_group
            ):
                current_group.append(task)
            else:
                groups.append(current_group)
                current_group = [task]
        if current_group:
            groups.append(current_group)
        return groups

    def mark_task(
        self,
        task_id: str,
        status: TaskStatus,
        result_summary: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update task lifecycle status and recording details."""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = status
            if result_summary:
                task.result_summary = result_summary
            if error:
                task.error = error

    def replan_failed_subgraph(
        self,
        failed_task_id: str,
        replacement_tasks: list[PlanTask],
    ) -> None:
        """Dynamically replace a failed task and reroute its dependents through the new subgraph."""
        if failed_task_id not in self.tasks:
            return

        failed_task = self.tasks[failed_task_id]
        failed_task.status = TaskStatus.SKIPPED
        failed_task.result_summary = f"Superseded by {[r.task_id for r in replacement_tasks]}"

        # Find tasks that depended on failed_task
        dependent_task_ids = [
            t.task_id for t in self.tasks.values() if failed_task_id in t.depends_on
        ]

        # Add replacement tasks
        for rep in replacement_tasks:
            # If replacement has no depends_on, inherit failed task's dependencies
            if not rep.depends_on:
                rep.depends_on = list(failed_task.depends_on)
            self.tasks[rep.task_id] = rep

        # Reroute dependents to depend on the last replacement task
        if replacement_tasks:
            last_replacement_id = replacement_tasks[-1].task_id
            for dep_id in dependent_task_ids:
                dep_task = self.tasks[dep_id]
                dep_task.depends_on = [
                    last_replacement_id if d == failed_task_id else d for d in dep_task.depends_on
                ]

        self.replan_count += 1
        # Validate DAG consistency
        try:
            self.to_dag()
        except CycleDetectedError as exc:
            raise RuntimeError(f"Re-planning created an illegal cycle: {exc}") from exc

    def is_all_completed(self) -> bool:
        """Return True if all tasks in the plan are COMPLETED or SKIPPED."""
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED) for t in self.tasks.values()
        )

    def to_summary_markdown(self) -> str:
        """Render markdown summary of plan status."""
        lines = [f"### Dynamic Plan (Re-plans: {self.replan_count}):"]
        for t in self.tasks.values():
            icon = {
                TaskStatus.COMPLETED: "✅",
                TaskStatus.RUNNING: "🔄",
                TaskStatus.READY: "⏳",
                TaskStatus.PENDING: "⚪",
                TaskStatus.FAILED: "❌",
                TaskStatus.BLOCKED: "🚫",
                TaskStatus.SKIPPED: "⏭️",
            }.get(t.status, "•")
            deps = f" (depends: {', '.join(t.depends_on)})" if t.depends_on else ""
            lines.append(
                f"- {icon} **[{t.task_id}]** ({t.role.value}) {t.title}{deps}: {t.status.value}"
            )
            if t.result_summary:
                lines.append(f"  Result: {t.result_summary}")
            if t.error:
                lines.append(f"  Error: {t.error}")
        return "\n".join(lines)
