"""Data models for mission tracing, execution spans, and replay."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class SpanType(str, Enum):
    """Categorization of an execution span."""
    MISSION = "MISSION"
    AGENT_STEP = "AGENT_STEP"
    LLM_CALL = "LLM_CALL"
    TOOL_CALL = "TOOL_CALL"
    SECURITY_CHECK = "SECURITY_CHECK"
    VERIFICATION = "VERIFICATION"
    REPLAN = "REPLAN"


class SpanStatus(str, Enum):
    """Execution status of a span."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class SpanRecord(BaseModel):
    """Individual trace span capturing latency, tokens, cost, and redacted I/O."""
    span_id: str
    parent_span_id: str | None = None
    mission_id: str
    span_type: SpanType
    name: str
    role: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    duration_ms: float = 0.0
    status: SpanStatus = SpanStatus.RUNNING
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    error: str | None = None

    def finish(
        self,
        status: SpanStatus = SpanStatus.SUCCESS,
        output_data: dict[str, Any] | None = None,
        error: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Mark span as finished and compute duration."""
        self.ended_at = datetime.now(UTC)
        self.duration_ms = max(0.0, (self.ended_at - self.started_at).total_seconds() * 1000.0)
        self.status = status
        if output_data is not None:
            self.output_data = output_data
        if error:
            self.error = error
        if tokens_in:
            self.tokens_in = tokens_in
        if tokens_out:
            self.tokens_out = tokens_out
        if cost_usd:
            self.cost_usd = cost_usd


class MissionTrace(BaseModel):
    """Complete structured trace of a mission containing all nested spans."""
    mission_id: str
    objective: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    duration_ms: float = 0.0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    spans: list[SpanRecord] = Field(default_factory=list)
    status: str = "COMPLETED"

    def aggregate_metrics(self) -> None:
        """Compute aggregate metrics across all recorded spans."""
        self.total_tokens = sum(s.tokens_in + s.tokens_out for s in self.spans)
        self.total_cost_usd = sum(s.cost_usd for s in self.spans)
        if self.ended_at:
            self.duration_ms = max(0.0, (self.ended_at - self.started_at).total_seconds() * 1000.0)
