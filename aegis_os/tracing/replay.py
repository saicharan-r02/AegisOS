"""ReplayEngine allows replaying an entire historical mission step-by-step without making LLM calls."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.state import StepRecord
from aegis_os.tracing.models import MissionTrace, SpanRecord
from aegis_os.tracing.tracer import MissionTracer


class ReplayEngine:
    """Renders or steps through historical mission execution with zero LLM invocation."""

    def __init__(
        self,
        checkpoint_store: CheckpointStore | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        if checkpoint_store:
            self.store = checkpoint_store
        elif db_path:
            self.store = CheckpointStore(db_path)
        else:
            self.store = CheckpointStore(Path(".aegis/checkpoints.db"))

    def get_mission_steps(self, session_id: str) -> list[StepRecord]:
        """Fetch chronological list of recorded steps for mission."""
        return self.store.list_steps(session_id)

    def replay_terminal(
        self,
        session_id: str,
        delay_sec: float = 0.5,
        step_callback: Callable[[int, StepRecord], None] | None = None,
    ) -> int:
        """
        Play back all steps for a mission, invoking callback for each step.
        Returns total count of replayed steps.
        """
        steps = self.get_mission_steps(session_id)
        if not steps:
            return 0

        for i, step in enumerate(steps, start=1):
            if step_callback:
                step_callback(i, step)
            if delay_sec > 0 and i < len(steps):
                time.sleep(delay_sec)

        return len(steps)

    def replay_from_trace(
        self,
        mission_id: str,
        trace_db_path: Path | str,
        span_callback: Callable[[int, SpanRecord], None] | None = None,
        delay_sec: float = 0.1,
    ) -> MissionTrace:
        """Replay mission using recorded spans from MissionTracer database."""
        tracer = MissionTracer(mission_id=mission_id, db_path=trace_db_path)
        try:
            trace = tracer.get_trace()
            for idx, span in enumerate(trace.spans, start=1):
                if span_callback:
                    span_callback(idx, span)
                if delay_sec > 0:
                    time.sleep(delay_sec)
            return trace
        finally:
            tracer.close()
