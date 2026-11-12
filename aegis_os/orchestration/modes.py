"""Autonomy mode definitions and approval dispatching."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum


class AutonomyMode(str, Enum):
    """Execution autonomy levels for AegisOS missions."""
    PLAN = "plan"              # Stop after CTO produces plan DAG; await human confirmation
    SUPERVISED = "supervised"  # Prompt human for risky/destructive actions
    AUTO = "auto"              # Fully autonomous bounded by in-code security policy


class ModeController:
    """Evaluates and enforces human-in-the-loop gates according to active mode."""

    def __init__(
        self,
        mode: AutonomyMode = AutonomyMode.AUTO,
        headless: bool = False,
        approval_prompt: Callable[[str, str], bool] | None = None,
    ) -> None:
        self.mode = mode
        self.headless = headless
        self.approval_prompt = approval_prompt or self._default_console_prompt

    @staticmethod
    def _default_console_prompt(action: str, reason: str) -> bool:
        """Interactive terminal prompt for human approval."""
        print(f"\n[APPROVAL REQUIRED] Action: {action}\nReason: {reason}")
        try:
            choice = input("Approve execution? [y/N]: ").strip().lower()
            return choice in {"y", "yes"}
        except (EOFError, KeyboardInterrupt):
            return False

    def should_halt_after_plan(self) -> bool:
        """Returns True if execution must pause immediately after CTO generates plan."""
        return self.mode == AutonomyMode.PLAN

    def request_approval(self, action: str, reason: str) -> bool:
        """
        Request human sign-off for a sensitive action.
        In AUTO mode, non-denied actions pass automatically.
        In headless mode without prompt, unapproved risky actions are rejected.
        """
        if self.mode == AutonomyMode.AUTO:
            return True
        if self.headless:
            return False  # Headless supervised mode cannot prompt stdin
        return self.approval_prompt(action, reason)
