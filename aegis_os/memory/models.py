"""Data models for multi-tier episodic memory and learned codebase conventions."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field


class EpisodicMemory(BaseModel):
    """Snapshot of a completed or failed mission capturing lessons, diffs, and fix patterns."""

    episode_id: str = Field(description="Unique session/episode identifier")
    objective: str = Field(description="Original engineering goal")
    success: bool = Field(description="True if mission achieved all invariants and succeeded")
    tasks_executed: list[str] = Field(
        default_factory=list, description="IDs and titles of tasks executed"
    )
    files_modified: list[str] = Field(default_factory=list, description="List of files touched")
    failure_modes: list[str] = Field(
        default_factory=list, description="Failures and errors encountered"
    )
    successful_patterns: list[str] = Field(
        default_factory=list, description="Fix patterns and architectural choices that worked"
    )
    timestamp: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodebaseConvention(BaseModel):
    """Learned rule or convention abstracted from past successful missions."""

    rule_id: str
    pattern: str = Field(description="Learned rule e.g. 'Use httpx instead of requests'")
    reason: str = Field(description="Explanation e.g. 'Codebase standard is async'")
    success_count: int = Field(default=1, ge=1)
    last_updated: float = Field(default_factory=time.time)
