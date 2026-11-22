"""Turn a finished mission into an episodic memory the dashboard (and future missions) can use."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aegis_os.kernel.context import redact_sensitive_text
from aegis_os.kernel.state import AgentState, MissionStatus
from aegis_os.memory.models import EpisodicMemory
from aegis_os.memory.store import MemoryStore
from aegis_os.verification.workspace_audit import changed_files


def build_episode(state: AgentState, error: str | None = None) -> EpisodicMemory:
    """Summarise a mission's final state. Pure function: easy to test, never touches disk."""
    cv: dict[str, Any] = state.context_variables
    plan = cv.get("mission_plan") if isinstance(cv.get("mission_plan"), dict) else {}
    tasks = [
        f"{t.get('task_id', '?')}: {t.get('title', '')}".strip()
        for t in (plan or {}).get("tasks", [])
        if isinstance(t, dict)
    ]
    failures: list[str] = []
    for item in cv.get("invariants", []) or []:
        if isinstance(item, dict) and not item.get("passed"):
            failures.append(f"{item.get('name')}: {item.get('details')}")
    for entry in cv.get("failure_ledger", []) or []:
        if isinstance(entry, dict) and entry.get("reason"):
            failures.append(str(entry["reason"]))
    if cv.get("failure_reason"):
        failures.append(str(cv["failure_reason"]))
    if error:
        failures.append(error)
    succeeded = state.status == MissionStatus.COMPLETED
    workspace = cv.get("workspace_root")
    files = changed_files(Path(workspace), cv.get("base_commit")) if workspace else []
    patterns = (
        [f"Completed with {len(files)} file(s) changed in {state.current_step_index} steps."]
        if succeeded
        else []
    )
    return EpisodicMemory(
        episode_id=state.session_id,
        objective=redact_sensitive_text(state.mission_goal),
        success=succeeded,
        tasks_executed=tasks,
        files_modified=files,
        failure_modes=[redact_sensitive_text(f)[:300] for f in dict.fromkeys(failures)][:10],
        successful_patterns=patterns,
        metadata={
            "status": state.status.value,
            "steps": state.current_step_index,
            "tokens_used": state.tokens_used,
        },
    )


def record_mission_episode(
    state: AgentState, memory_root: Path | None = None, error: str | None = None
) -> bool:
    """Persist the episode. Returns False (never raises) so memory can't break a mission."""
    try:
        MemoryStore(workspace_root=memory_root or Path.cwd()).record_episode(
            build_episode(state, error)
        )
        return True
    except Exception:
        return False
