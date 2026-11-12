"""Time-travel debugging controller coordinating SQLite state and filesystem rollback."""

from __future__ import annotations

from pathlib import Path

from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.state import AgentState
from aegis_os.timetravel.shadow import ShadowBranchManager


class TimeTravelController:
    """Coordinates agent state snapshots and filesystem git commits for true step-level rollback."""

    def __init__(
        self,
        workspace_root: Path,
        checkpoint_store: CheckpointStore | None = None,
        shadow_mgr: ShadowBranchManager | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.checkpoint_store = checkpoint_store or CheckpointStore(
            self.workspace_root / ".aegis" / "checkpoints.db"
        )
        self.shadow_mgr = shadow_mgr or ShadowBranchManager(self.workspace_root)

    def checkpoint(self, state: AgentState) -> int:
        """Capture dual checkpoint: SQLite agent state + filesystem git commit & tag."""
        cid = self.checkpoint_store.save_checkpoint(state)
        # Commit and tag filesystem state
        self.shadow_mgr.commit_step(
            session_id=state.session_id,
            step_index=state.current_step_index,
            message=f"Aegis step {state.current_step_index}: {state.active_role.value if state.active_role else 'INIT'}",
        )
        return cid

    def rollback(self, session_id: str, target_step_index: int) -> tuple[AgentState, str]:
        """Roll back both agent SQLite state and disk filesystem to exact target step."""
        restored_state = self.checkpoint_store.rollback_to_step(session_id, target_step_index)

        # On Windows the SQLite file stays locked while the connection is open.
        # Close the store so restore_step (git reset/clean or snapshot copy) can
        # safely manipulate any files inside the workspace directory.
        db_path = self.checkpoint_store.db_path
        self.checkpoint_store.close()

        try:
            fs_ok, fs_msg = self.shadow_mgr.restore_step(session_id, target_step_index)
        finally:
            # Reopen so the store is still usable after rollback
            self.checkpoint_store = CheckpointStore(db_path)

        summary = f"Agent state restored to step {target_step_index}. {fs_msg}"
        return restored_state, summary

    def rewind(
        self, target_step_index: int, session_id: str | None = None
    ) -> tuple[AgentState, str]:
        """Interactive rewind: look up active or most recent session and roll back state + files."""
        if not session_id:
            missions = self.checkpoint_store.list_missions()
            if not missions:
                raise RuntimeError("No recorded missions found in checkpoint store.")
            session_id = missions[0]["session_id"]

        return self.rollback(session_id, target_step_index)
