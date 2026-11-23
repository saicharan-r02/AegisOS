from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from aegis_os.kernel.state import MissionStatus, StepRecord


class MissionLaunchRequest(BaseModel):
    goal: str
    repo_url: str | None = None
    repo_branch: str | None = "main"
    issue_url: str | None = None
    failure_reason: str | None = None
    workspace: str = "."
    provider: Literal["nvidia"] = "nvidia"
    model: str | None = None
    max_repairs: int = 2
    max_steps: int = 60
    strategy: str = "adaptive"
    unsafe_local: bool = False


class MissionResponse(BaseModel):
    session_id: str
    goal: str
    status: MissionStatus
    current_step_index: int
    updated_at: str
    tokens_used: int = 0
    max_tokens: int = 0
    workspace: str | None = None
    repo_url: str | None = None
    strategy: str | None = None
    provider: str | None = None
    pr_url: str | None = None
    issue_url: str | None = None
    failure_reason: str | None = None


class MissionStatsResponse(BaseModel):
    total: int = 0
    completed: int = 0
    failed: int = 0
    aborted: int = 0
    running: int = 0
    paused: int = 0
    pending: int = 0
    total_steps: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    success_rate: float | None = None  # completed / finished missions; None until one finishes


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
    status: str = "PENDING"


class ApprovalActionRequest(BaseModel):
    action: str


class KernelEventSchema(BaseModel):
    event_type: str
    payload: dict[str, Any]


class MissionControlActionResponse(BaseModel):
    session_id: str
    action: str
    success: bool
    message: str
class PRPilotAnalyzeRequest(BaseModel):
    issue_url: str
    github_username: str | None = None
    issue_text: str = ""
    provider: Literal["nvidia"] = "nvidia"
    model: str | None = None


class PRPilotGuideStepSchema(BaseModel):
    step_number: int
    title: str
    description: str
    command: str


class PRPilotAnalyzeResponse(BaseModel):
    owner: str
    repo: str
    issue_number: int
    issue_url: str
    github_username: str
    analysis: dict[str, Any] | None = None
    guide: list[PRPilotGuideStepSchema] = Field(default_factory=list)
    branch: str
    commit: str
    pr_title: str
    pr_body: str
    ai_error: str = ""
    fetched_from_github: bool = False


class PRPilotExecuteRequest(BaseModel):
    issue_url: str
    github_username: str = ""
    branch: str = ""
    commit_message: str = ""
    pr_title: str = ""
    pr_body: str = ""
    patch: str = ""
    tests: str = ""
    summary: str = ""
    root_cause: str = ""
    affected_files: list[str] = Field(default_factory=list)


class PRPilotExecuteResponse(BaseModel):
    status: str
    workspace_path: str
    branch: str
    commit_sha: str = ""
    changed_files: list[str] = Field(default_factory=list)
    tests_output: str = ""
    pr_url: str | None = None
    message: str = ""
