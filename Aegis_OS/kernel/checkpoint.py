"""
Kernel Checkpoint: SQLite WAL-Mode Working Memory & Rollback Engine
===================================================================
Provides transactional, crash-resilient persistence of mission states,
step logs, and state snapshots with point-in-time rollback capabilities.
"""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Optional

from aegis_os.kernel.exceptions import CheckpointNotFoundError
from aegis_os.kernel.state import AgentState, StepRecord


class CheckpointStore:
    """
    SQLite-backed transactional state store.
    Enforces Write-Ahead Logging (WAL) mode for concurrent readers and writers.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema and set WAL pragma."""
        with self._conn:
            # WAL mode enables concurrent reading while writing (ignored for :memory:)
            if self.db_path != ":memory:":
                self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA busy_timeout = 5000;")
            self._conn.execute("PRAGMA foreign_keys = ON;")

            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS missions (
                    session_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_step_index INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    state_json TEXT NOT NULL
                );
            """)

            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS steps (
                    step_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES missions(session_id) ON DELETE CASCADE
                );
            """)

            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    state_snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, step_index),
                    FOREIGN KEY (session_id) REFERENCES missions(session_id) ON DELETE CASCADE
                );
            """)

    def save_checkpoint(self, state: AgentState) -> int:
        """
        Persist mission state, step history, and a point-in-time snapshot.
        Returns the checkpoint ID.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        state_json = state.model_dump_json()

        with self._conn:
            # 1. Upsert mission record
            self._conn.execute(
                """
                INSERT INTO missions (session_id, goal, status, current_step_index, created_at, updated_at, state_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    status=excluded.status,
                    current_step_index=excluded.current_step_index,
                    updated_at=excluded.updated_at,
                    state_json=excluded.state_json;
                """,
                (
                    state.session_id,
                    state.mission_goal,
                    state.status.value,
                    state.current_step_index,
                    now_str,
                    now_str,
                    state_json,
                ),
            )

            # 2. Upsert step records
            for step in state.step_history:
                step_json = step.model_dump_json()
                self._conn.execute(
                    """
                    INSERT INTO steps (step_id, session_id, step_index, role, status, record_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(step_id) DO UPDATE SET
                        status=excluded.status,
                        record_json=excluded.record_json;
                    """,
                    (
                        step.step_id,
                        state.session_id,
                        step.step_index,
                        step.role.value,
                        step.status.value,
                        step_json,
                        step.started_at.isoformat(),
                    ),
                )

            # 3. Insert or update point-in-time checkpoint
            cursor = self._conn.execute(
                """
                INSERT INTO checkpoints (session_id, step_index, state_snapshot_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, step_index) DO UPDATE SET
                    state_snapshot_json=excluded.state_snapshot_json,
                    created_at=excluded.created_at;
                """,
                (state.session_id, state.current_step_index, state_json, now_str),
            )
            return cursor.lastrowid or 0

    def load_latest_state(self, session_id: str) -> Optional[AgentState]:
        """Load the most recently saved state for a session."""
        cursor = self._conn.execute(
            "SELECT state_json FROM missions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return AgentState.model_validate_json(row["state_json"])

    def rollback_to_step(self, session_id: str, target_step_index: int) -> AgentState:
        """
        Revert mission state to the exact snapshot taken at target_step_index.
        Truncates later steps from the store to preserve causal consistency.
        """
        cursor = self._conn.execute(
            """
            SELECT state_snapshot_json FROM checkpoints
            WHERE session_id = ? AND step_index = ?
            """,
            (session_id, target_step_index),
        )
        row = cursor.fetchone()
        if not row:
            raise CheckpointNotFoundError(session_id=session_id, step_index=target_step_index)

        restored_state = AgentState.model_validate_json(row["state_snapshot_json"])

        with self._conn:
            # Clean up later steps and checkpoints
            self._conn.execute(
                "DELETE FROM steps WHERE session_id = ? AND step_index > ?",
                (session_id, target_step_index),
            )
            self._conn.execute(
                "DELETE FROM checkpoints WHERE session_id = ? AND step_index > ?",
                (session_id, target_step_index),
            )

            # Update mission record
            now_str = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                """
                UPDATE missions
                SET current_step_index = ?, status = ?, state_json = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (
                    restored_state.current_step_index,
                    restored_state.status.value,
                    restored_state.model_dump_json(),
                    now_str,
                    session_id,
                ),
            )

        return restored_state

    def list_missions(self) -> list[dict[str, Any]]:
        """Return all tracked missions for audit and dashboard view."""
        cursor = self._conn.execute(
            "SELECT session_id, goal, status, current_step_index, created_at, updated_at FROM missions ORDER BY updated_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def list_steps(self, session_id: str) -> list[StepRecord]:
        """Return the complete step history for a session ordered by step_index."""
        cursor = self._conn.execute(
            "SELECT record_json FROM steps WHERE session_id = ? ORDER BY step_index ASC",
            (session_id,),
        )
        return [StepRecord.model_validate_json(row["record_json"]) for row in cursor.fetchall()]

    def close(self) -> None:
        """Close SQLite database connection."""
        self._conn.close()
