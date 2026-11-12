"""Structured failure ledger for tracking task/step errors and informing adaptive re-planning."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from aegis_os.kernel.state import AgentRole


class FailureEntry(BaseModel):
    """An immutable record of a failed task execution or verification attempt."""

    entry_id: str
    task_id: str
    role: AgentRole
    error_message: str
    attempted_action: str
    root_cause_analysis: str = ""
    avoidance_rule: str = ""
    timestamp: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FailureLedger(BaseModel):
    """Ledger accumulating failures, diagnostic root causes, and avoidance constraints."""

    entries: list[FailureEntry] = Field(default_factory=list)

    def record_failure(
        self,
        task_id: str,
        role: AgentRole,
        error_message: str,
        attempted_action: str,
        root_cause_analysis: str = "",
        avoidance_rule: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> FailureEntry:
        """Add a failure entry to the ledger."""
        entry = FailureEntry(
            entry_id=f"fail-{len(self.entries) + 1}",
            task_id=task_id,
            role=role,
            error_message=error_message,
            attempted_action=attempted_action,
            root_cause_analysis=root_cause_analysis or "Under investigation.",
            avoidance_rule=avoidance_rule
            or f"Do not repeat '{attempted_action}' without addressing '{error_message[:100]}'.",
            metadata=metadata or {},
        )
        self.entries.append(entry)
        return entry

    def failure_count_for_task(self, task_id: str) -> int:
        """Return total failures logged for a given task."""
        return sum(1 for e in self.entries if e.task_id == task_id)

    def get_avoidance_rules(self) -> list[str]:
        """Extract all avoidance rules generated so far."""
        return [e.avoidance_rule for e in self.entries if e.avoidance_rule]

    def format_guidance_for_planner(self) -> str:
        """Format ledger lessons into a system prompt guidance block to prevent repetition."""
        if not self.entries:
            return "No previous failures logged in ledger."

        lines = [
            "### Failure Ledger (Lessons Learned & Avoidance Rules):",
            "The following approaches have failed previously. You MUST NOT repeat these mistakes:",
        ]
        for e in self.entries[-8:]:  # Keep recent entries
            lines.append(
                f"- **[{e.task_id} / {e.role.value}]**: Failed during '{e.attempted_action}'."
            )
            lines.append(f"  Error: {e.error_message[:200]}")
            if e.root_cause_analysis:
                lines.append(f"  Root Cause: {e.root_cause_analysis}")
            if e.avoidance_rule:
                lines.append(f"  ⚡ Avoidance Rule: {e.avoidance_rule}")

        return "\n".join(lines)
