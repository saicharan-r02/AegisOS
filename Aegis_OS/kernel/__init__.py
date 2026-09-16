"""
AegisOS Kernel: Control & State Plane
====================================
Owns global state, transactions, checkpointing, and event-driven coordination.
"""

from aegis_os.kernel.exceptions import (
    CheckpointNotFoundError,
    CycleDetectedError,
    InvalidTransitionError,
    KernelError,
    MaxStepsExceededError,
    StagnationError,
)
from aegis_os.kernel.state import (
    AgentRole,
    AgentState,
    DAGEdge,
    DAGNode,
    MissionDAG,
    MissionStatus,
    StepRecord,
    StepStatus,
)

__all__ = [
    "KernelError",
    "CycleDetectedError",
    "StagnationError",
    "MaxStepsExceededError",
    "InvalidTransitionError",
    "CheckpointNotFoundError",
    "MissionStatus",
    "StepStatus",
    "AgentRole",
    "StepRecord",
    "AgentState",
    "DAGNode",
    "DAGEdge",
    "MissionDAG",
]
