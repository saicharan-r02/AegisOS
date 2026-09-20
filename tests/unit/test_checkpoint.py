from pathlib import Path
import pytest
import sqlite3
from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.exceptions import CheckpointNotFoundError
from aegis_os.kernel.state import AgentRole, AgentState, MissionStatus
from aegis_os.tools.base import ToolResult


class TestCheckpointStore:
    """CheckpointStore persistence and rollback tests."""

    def test_database_initialization_and_wal_mode(self,tmp_workspace: Path) -> None:
        db_file=tmp_workspace / "state.db"
        store=CheckpointStore(db_path=db_file)

        cursor=store._conn.execute("PRAGMA journal_mode;")
        row=cursor.fetchone()
        assert row[0].lower()=="wal"
        store.close()

    def test_save_and_load_latest_state(self,tmp_workspace: Path) -> None:
        store=CheckpointStore(db_path=tmp_workspace / "state.db")
        state=AgentState(mission_goal="Build microservice")

        state.add_step(role=AgentRole.CTO,task_description="Decompose tasks")
        state.complete_current_step(tool_result=ToolResult.ok(output="Plan ready"))
        store.save_checkpoint(state)

        state.add_step(role=AgentRole.DEV,task_description="Implement API")
        state.complete_current_step(tool_result=ToolResult.ok(output="API code written"))
        store.save_checkpoint(state)
        loaded=store.load_latest_state(state.session_id)
        assert loaded is not None
        assert loaded.session_id==state.session_id
        assert loaded.current_step_index==2
        assert len(loaded.step_history)==2
        assert loaded.step_history[1].task_description=="Implement API"
        store.close()

    def test_rollback_to_earlier_step(self,tmp_workspace: Path) -> None:
        store=CheckpointStore(db_path=tmp_workspace/"state.db")
        state=AgentState(mission_goal="Rollback test")

        state.add_step(role=AgentRole.DEV,task_description="Step 1: Good change")
        state.complete_current_step(tool_result=ToolResult.ok(output="Pass"))
        store.save_checkpoint(state)

        state.add_step(role=AgentRole.DEV,task_description="Step 2: Broken change")
        state.complete_current_step(tool_result=ToolResult.fail(error="Crash"))
        store.save_checkpoint(state)

        state.add_step(role=AgentRole.DEV,task_description="Step 3: Bad patch")
        state.complete_current_step(tool_result=ToolResult.fail(error="Worse Crash"))
        store.save_checkpoint(state)

        assert state.current_step_index==3

        restored=store.rollback_to_step(state.session_id,target_step_index=1)
        assert restored.current_step_index==1
        assert len(restored.step_history)==1
        assert restored.step_history[0].task_description=="Step 1: Good change"

        remaining_steps=store.list_steps(state.session_id)
        assert len(remaining_steps)==1
        assert remaining_steps[0].step_index==1

        latest=store.load_latest_state(state.session_id)
        assert latest is not None
        assert latest.current_step_index==1
        store.close()

    def test_rollback_nonexistent_step_raises_error(self,tmp_workspace: Path) -> None:
        store=CheckpointStore(db_path=tmp_workspace/"state.db")
        state=AgentState(mission_goal="Test")
        store.save_checkpoint(state)

        with pytest.raises(CheckpointNotFoundError):
            store.rollback_to_step(state.session_id,target_step_index=99)
        store.close()

    def test_multi_mission_isolation(self,tmp_workspace: Path) -> None:
        store=CheckpointStore(db_path=tmp_workspace/"state.db")

        m1=AgentState(mission_goal="Mission 1")
        m1.add_step(role=AgentRole.DEV,task_description="M1 Step 1")
        m1.complete_current_step(tool_result=ToolResult.ok(output="M1 Done"))
        store.save_checkpoint(m1)

        m2=AgentState(mission_goal="Mission 2")
        m2.add_step(role=AgentRole.QA,task_description="M2 Step 1")
        m2.complete_current_step(tool_result=ToolResult.ok(output="M2 Done"))
        store.save_checkpoint(m2)

        missions=store.list_missions()
        assert len(missions)==2

        m1_steps=store.list_steps(m1.session_id)
        m2_steps=store.list_steps(m2.session_id)
        assert len(m1_steps)==1
        assert len(m2_steps)==1
        assert m1_steps[0].role==AgentRole.DEV
        assert m2_steps[0].role==AgentRole.QA
        store.close()