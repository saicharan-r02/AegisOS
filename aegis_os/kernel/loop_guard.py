"""Detect repeated tool actions and short oscillations in ReAct loops."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LoopSignal:
    reason: str
    should_reflect: bool
    should_escalate: bool


class LoopGuard:
    """Detects repeated calls, A/B oscillation, and windows without progress."""

    def __init__(self, repeat_limit: int = 2, oscillation_window: int = 4, escalation_after: int = 2) -> None:
        self.repeat_limit = max(2, repeat_limit)
        self.oscillation_window = max(4, oscillation_window)
        self.escalation_after = max(1, escalation_after)
        self._calls: list[str] = []
        self._no_progress = 0
        self._signals = 0

    @staticmethod
    def signature(tool_name: str | None, arguments: dict[str, Any]) -> str:
        return json.dumps([tool_name, arguments], sort_keys=True, default=str, separators=(",", ":"))

    def observe(
        self,
        tool_name: str | None,
        arguments: dict[str, Any],
        *,
        made_progress: bool,
    ) -> LoopSignal | None:
        signature = self.signature(tool_name, arguments)
        self._calls.append(signature)
        self._calls = self._calls[-self.oscillation_window :]
        self._no_progress = 0 if made_progress else self._no_progress + 1

        reason: str | None = None
        if len(self._calls) >= self.repeat_limit and len(set(self._calls[-self.repeat_limit :])) == 1:
            reason = "Repeated the same tool call with identical arguments."
        elif self._is_oscillating():
            reason = "Alternated between the same two tool calls without progress."
        elif self._no_progress >= self.oscillation_window:
            reason = f"Made no progress for {self._no_progress} consecutive tool calls."

        if reason is None:
            return None
        self._signals += 1
        return LoopSignal(
            reason=reason,
            should_reflect=True,
            should_escalate=self._signals >= self.escalation_after,
        )

    def _is_oscillating(self) -> bool:
        if len(self._calls) < 4:
            return False
        recent = self._calls[-4:]
        return recent[0] == recent[2] and recent[1] == recent[3] and recent[0] != recent[1]
