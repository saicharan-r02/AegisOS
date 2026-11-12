from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from aegis_os.kernel.state import MissionStatus, StepRecord


class MissionLaunchRequest(BaseModel):
    goal: str
    workspace: str = "."
    provider: Literal["nvidia"] = "nvidia"
    model: str | None = None
    max_repairs: int = 3
    strategy: str = "adaptive"
    unsafe_local: bool = False


class MissionResponse(BaseModel):
    session_id: str
    goal: str
    status: MissionStatus
    current_step_index: int
    updated_at: str


class MissionListResponse(BaseModel):
    missions: list[MissionResponse]


class MissionStepsResponse(BaseModel):
    session_id: str
    steps: list[StepRecord]


class MissionDiffResponse(BaseModel):
    session_id: str
    diff: str
    files_changed: list[str] = Field(default_factory=list)


class AcceptanceItem(BaseModel):
    id: str
    description: str
    passed: bool
    evidence: str = ""


class AcceptanceCriteriaResponse(BaseModel):
    session_id: str
    criteria: list[AcceptanceItem] = Field(default_factory=list)


class ApprovalItem(BaseModel):
    approval_id: str
    session_id: str
    command: str
    reason: str
    timestamp: str
    status: str = "PENDING"  # PENDING, APPROVED, DENIED


class ApprovalActionRequest(BaseModel):
    action: str  # "approve" or "deny"


class KernelEventSchema(BaseModel):
    event_type: str
    payload: dict[str, Any]


class MissionControlActionResponse(BaseModel):
    session_id: str
    action: str
    success: bool
    message: str
