"""
Kernel State: AgentState, StepRecord, and MissionDAG
====================================================
Defines the core data contracts for the AegisOS Control and State Plane.
All state transitions are deterministic, validated by Pydantic V2, and fully serializable.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from aegis_os.kernel.exceptions import CycleDetectedError
from aegis_os.tools.base import ToolResult


class MissionStatus(str, Enum):
    """Lifecycle status of a complete engineering mission."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class StepStatus(str, Enum):
    """Lifecycle status of an individual execution step."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    BLOCKED = "BLOCKED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class AgentRole(str, Enum):
    """Specialized autonomous engineering roles."""
    CTO = "CTO"
    DEV = "DEV"
    QA = "QA"
    SEC = "SEC"
    OPS = "OPS"


class StepRecord(BaseModel):
    """
    Immutable audit record of a single action step attempted by an agent.
    Captures intent, arguments, execution results, timing, and errors.
    """
    model_config = ConfigDict(extra="ignore")

    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_index: int = Field(ge=1, description="1-indexed sequence number of this step.")
    role: AgentRole = Field(description="Role of the agent that executed this step.")
    task_description: str = Field(description="Human-readable explanation of intent.")
    tool_name: Optional[str] = Field(default=None, description="Tool called during this step, if any.")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Raw arguments passed to the tool.")
    tool_result: Optional[ToolResult] = Field(default=None, description="Result returned by the tool, if called.")
    status: StepStatus = Field(default=StepStatus.PENDING)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def complete(
        self,
        tool_result: Optional[ToolResult] = None,
        error: Optional[str] = None,
        status: Optional[StepStatus] = None,
    ) -> None:
        """Mark this step as completed and calculate elapsed duration."""
        self.finished_at = datetime.now(timezone.utc)
        if self.started_at:
            delta = self.finished_at - self.started_at
            self.duration_ms = round(delta.total_seconds() * 1000.0, 2)

        if tool_result is not None:
            self.tool_result = tool_result
            if status is None:
                self.status = StepStatus.SUCCESS if tool_result.success else StepStatus.FAILURE
        elif status is not None:
            self.status = status
        elif error is not None:
            self.status = StepStatus.FAILURE
        else:
            self.status = StepStatus.SUCCESS

        if error:
            self.error = error
        elif tool_result and tool_result.error:
            self.error = tool_result.error


class AgentState(BaseModel):
    """
    Global working memory and execution state for a mission session.
    Owns step history, context variables, execution budgets, and failure counters.
    """
    model_config = ConfigDict(extra="ignore")

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mission_goal: str = Field(description="Primary objective defined for this mission.")
    status: MissionStatus = Field(default=MissionStatus.PENDING)
    current_step_index: int = Field(default=0, ge=0)
    active_role: Optional[AgentRole] = None
    step_history: list[StepRecord] = Field(default_factory=list)
    context_variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Shared epistemic memory across agents (e.g. file lists, test reports)."
    )
    max_steps: int = Field(default=50, ge=1, description="Hard limit on total execution steps.")
    consecutive_failures: int = Field(default=0, ge=0, description="Consecutive failed steps.")
    stagnation_threshold: int = Field(default=3, ge=1, description="Max consecutive failures before halt.")

    @property
    def is_terminal(self) -> bool:
        """True if the mission has reached an end state."""
        return self.status in (MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.ABORTED)

    def add_step(
        self,
        role: AgentRole,
        task_description: str,
        tool_name: Optional[str] = None,
        tool_args: Optional[dict[str, Any]] = None,
    ) -> StepRecord:
        """Create, append, and return a new active step record."""
        self.current_step_index += 1
        self.active_role = role
        step = StepRecord(
            step_index=self.current_step_index,
            role=role,
            task_description=task_description,
            tool_name=tool_name,
            tool_args=tool_args or {},
            status=StepStatus.RUNNING,
        )
        self.step_history.append(step)
        return step

    def complete_current_step(
        self,
        tool_result: Optional[ToolResult] = None,
        error: Optional[str] = None,
        status: Optional[StepStatus] = None,
    ) -> StepRecord:
        """Complete the most recent active step and update failure counters."""
        last_step = self.get_last_step()
        if not last_step:
            raise ValueError("No active step in progress to complete.")

        last_step.complete(tool_result=tool_result, error=error, status=status)

        if last_step.status == StepStatus.SUCCESS:
            self.consecutive_failures = 0
        elif last_step.status == StepStatus.FAILURE:
            self.consecutive_failures += 1

        return last_step

    def get_last_step(self) -> Optional[StepRecord]:
        """Return the most recent step, or None if no steps have executed."""
        return self.step_history[-1] if self.step_history else None

    def get_last_successful_step(self) -> Optional[StepRecord]:
        """Return the most recent successful step, if any."""
        for step in reversed(self.step_history):
            if step.status == StepStatus.SUCCESS:
                return step
        return None

    def clone(self) -> "AgentState":
        """Return a deep copy of the current state snapshot."""
        return AgentState.model_validate(self.model_dump())


# ---------------------------------------------------------------------------
# DAG Graph Models for Mission Planning
# ---------------------------------------------------------------------------


class DAGNode(BaseModel):
    """A planned task node in a mission workflow."""
    model_config = ConfigDict(extra="ignore")

    node_id: str
    role: AgentRole
    task: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DAGEdge(BaseModel):
    """Directed transition edge between planned task nodes."""
    model_config = ConfigDict(extra="ignore")

    from_node: str
    to_node: str
    condition: str = Field(default="on_success", description="Trigger condition: on_success, on_failure, always.")


class MissionDAG(BaseModel):
    """
    Directed Acyclic Graph defining an autonomous multi-agent plan.
    Enforces strict cycle detection and topological ordering.
    """
    model_config = ConfigDict(extra="ignore")

    nodes: dict[str, DAGNode] = Field(default_factory=dict)
    edges: list[DAGEdge] = Field(default_factory=list)

    def add_node(self, node: DAGNode) -> None:
        """Register a node in the graph."""
        self.nodes[node.node_id] = node

    def add_edge(self, from_node: str, to_node: str, condition: str = "on_success") -> None:
        """Add a directed transition edge and validate acyclicity."""
        if from_node not in self.nodes:
            raise KeyError(f"Source node '{from_node}' does not exist in graph.")
        if to_node not in self.nodes:
            raise KeyError(f"Target node '{to_node}' does not exist in graph.")

        self.edges.append(DAGEdge(from_node=from_node, to_node=to_node, condition=condition))
        self.validate_acyclic()

    def validate_acyclic(self) -> None:
        """
        Verify that the graph contains no cycles using DFS cycle detection.
        Raises CycleDetectedError if a circular dependency is detected.
        """
        adj: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            adj[edge.from_node].append(edge.to_node)

        visited: set[str] = set()
        recursion_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            recursion_stack.add(node)
            path.append(node)

            for neighbor in adj[node]:
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in recursion_stack:
                    cycle = path[path.index(neighbor):] + [neighbor]
                    raise CycleDetectedError(cycle_path=cycle)

            recursion_stack.remove(node)
            path.pop()

        for node_id in self.nodes:
            if node_id not in visited:
                dfs(node_id)

    def get_entry_nodes(self) -> list[DAGNode]:
        """Return nodes that have no incoming edges."""
        target_nodes = {edge.to_node for edge in self.edges}
        return [node for nid, node in self.nodes.items() if nid not in target_nodes]

    def get_next_nodes(self, node_id: str, condition: str = "on_success") -> list[DAGNode]:
        """Find next nodes matching the execution condition."""
        next_ids = [
            edge.to_node
            for edge in self.edges
            if edge.from_node == node_id and (edge.condition == condition or edge.condition == "always")
        ]
        return [self.nodes[nid] for nid in next_ids if nid in self.nodes]
