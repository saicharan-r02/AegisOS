"""Unit tests and benchmark for Phase 7: True Rollback and Time-Travel Debugging."""

from __future__ import annotations

import subprocess
from pathlib import Path

from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.state import AgentRole, AgentState, MissionStatus
from aegis_os.timetravel.controller import TimeTravelController
from aegis_os.timetravel.shadow import ShadowBranchManager


class TestShadowBranchManager:
    def test_directory_fallback_snapshot_and_restore(self, tmp_path: Path) -> None:
        mgr = ShadowBranchManager(tmp_path)
        session_id = "sess-alpha-001"

        file1 = tmp_path / "service.py"
        file1.write_text("VERSION = 1\n", encoding="utf-8")
        snap1 = mgr.commit_step(session_id, step_index=1)
        assert Path(snap1).is_dir()

        file1.write_text("VERSION = 2\n", encoding="utf-8")
        file2 = tmp_path / "new_module.py"
        file2.write_text("def new_func(): pass\n", encoding="utf-8")
        mgr.commit_step(session_id, step_index=2)

        assert file1.read_text(encoding="utf-8") == "VERSION = 2\n"
        assert file2.exists()

        ok, msg = mgr.restore_step(session_id, step_index=1)
        assert ok
        assert file1.read_text(encoding="utf-8") == "VERSION = 1\n"
        assert not file2.exists()

    def test_git_shadow_branch_and_tags(self, tmp_path: Path) -> None:
        # Initialize a real git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "aegis@test.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "AegisAgent"], cwd=tmp_path, check=True)

        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True)

        mgr = ShadowBranchManager(tmp_path)
        assert mgr.is_git_repo()

        session_id = "git-sess-001"
        branch = mgr.create_shadow_branch(session_id)
        assert branch == f"aegis/mission/{session_id}"

        (tmp_path / "code.py").write_text("x = 10\n", encoding="utf-8")
        mgr.commit_step(session_id, step_index=1)

        (tmp_path / "code.py").write_text("x = BROKEN_SYNTAX(\n", encoding="utf-8")
        (tmp_path / "unwanted.py").write_text("garbage\n", encoding="utf-8")
        mgr.commit_step(session_id, step_index=2)

        assert (tmp_path / "code.py").read_text(encoding="utf-8") == "x = BROKEN_SYNTAX(\n"

        ok, msg = mgr.restore_step(session_id, step_index=1)
        assert ok
        assert (tmp_path / "code.py").read_text(encoding="utf-8") == "x = 10\n"
        assert not (tmp_path / "unwanted.py").exists()


class TestTimeTravelController:
    def test_dual_checkpoint_and_rollback(self, tmp_path: Path) -> None:
        db_path = tmp_path / "checkpoints.db"
        store = CheckpointStore(db_path=db_path)
        tt = TimeTravelController(tmp_path, checkpoint_store=store)

        session_id = "tt-sess-001"
        state = AgentState(
            session_id=session_id,
            mission_goal="Build API",
            status=MissionStatus.RUNNING,
            active_role=AgentRole.DEV,
        )

        # Step 1
        (tmp_path / "api.py").write_text("def get_api(): return 'v1'\n", encoding="utf-8")
        state.add_step(role=AgentRole.DEV, task_description="Write v1 API")
        state.complete_current_step()
        tt.checkpoint(state)

        # Step 2: Introduce bug
        (tmp_path / "api.py").write_text("def get_api(): return 1/0\n", encoding="utf-8")
        state.add_step(role=AgentRole.DEV, task_description="Introduce bug")
        state.complete_current_step()
        tt.checkpoint(state)

        assert state.current_step_index == 2
        assert "1/0" in (tmp_path / "api.py").read_text(encoding="utf-8")

        # Roll back to Step 1
        restored_state, msg = tt.rollback(session_id, target_step_index=1)

        # 1. Agent state restored
        assert restored_state.current_step_index == 1
        assert len(restored_state.step_history) == 1
        # 2. Filesystem on disk restored
        assert "return 'v1'" in (tmp_path / "api.py").read_text(encoding="utf-8")


class TestPhase7BenchmarkTrueRollback:
    """Benchmark Phase 7: Dev introduces breaking change, trigger rollback, verify clean state & resume."""

    def test_benchmark_breaking_change_rollback_and_resume(self, tmp_path: Path) -> None:
        db_path = tmp_path / "checkpoints.db"
        store = CheckpointStore(db_path=db_path)
        tt = TimeTravelController(tmp_path, checkpoint_store=store)

        session_id = "bench-p7-001"
        state = AgentState(
            session_id=session_id,
            mission_goal="Build robust math module",
            status=MissionStatus.RUNNING,
            active_role=AgentRole.DEV,
        )

        # Step 1: Initial working code
        calc_file = tmp_path / "calculator.py"
        calc_file.write_text("def add(a, b): return a + b\n", encoding="utf-8")
        state.add_step(role=AgentRole.DEV, task_description="Implement add")
        state.complete_current_step()
        tt.checkpoint(state)

        # Step 2: Dev breaks the module with syntax error
        calc_file.write_text("def divide(a, b): def broken((\n", encoding="utf-8")
        state.add_step(role=AgentRole.DEV, task_description="Broken divide attempt")
        state.complete_current_step()
        tt.checkpoint(state)

        # QA fails on Step 2
        assert calc_file.read_text(encoding="utf-8") == "def divide(a, b): def broken((\n"

        # Time-travel rollback to Step 1
        restored_state, log_msg = tt.rollback(session_id, target_step_index=1)

        # Benchmark Assertion 1: Filesystem matches Step 1 exactly (broken code gone)
        assert calc_file.read_text(encoding="utf-8") == "def add(a, b): return a + b\n"

        # Benchmark Assertion 2: Agent state matches Step 1
        assert restored_state.current_step_index == 1
        assert len(restored_state.step_history) == 1

        # Benchmark Assertion 3: Mission resumes from clean state to success
        calc_file.write_text(
            "def add(a, b): return a + b\n\ndef divide(a, b):\n    if b == 0: raise ValueError('zero')\n    return a / b\n",
            encoding="utf-8",
        )
        restored_state.add_step(role=AgentRole.DEV, task_description="Implement clean divide")
        restored_state.complete_current_step()
        tt.checkpoint(restored_state)

        assert restored_state.current_step_index == 2
        assert "raise ValueError" in calc_file.read_text(encoding="utf-8")
