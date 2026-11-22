"""The War Room backend really runs, controls, records and honestly reports missions."""
from __future__ import annotations

import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import aegis_os.api as api
from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.exceptions import MissionAbortedError
from aegis_os.kernel.state import AgentRole, AgentState, MissionStatus, StepStatus
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.base import ToolResult

REPO_ROOT = Path(__file__).resolve().parents[2]


def wait_for(predicate, timeout: float = 10.0, interval: float = 0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("condition not met in time")


def _status(session_id: str) -> str | None:
    store = CheckpointStore(api._db_path)
    try:
        state = store.load_latest_state(session_id)
        return state.status.value if state else None
    finally:
        store.close()


class FakeOrchestrator:
    """Stands in for the LLM-driven orchestrator but uses the REAL state machine."""

    behaviour = staticmethod(lambda sm: None)

    def __init__(self, **kwargs):
        self.machine: StateMachine = kwargs["state_machine"]
        self.kwargs = kwargs

    def execute_mission(self, goal):
        sm = self.machine
        sm.start_mission()
        try:
            type(self).behaviour(sm)
            sm.complete_mission("done")
        except MissionAbortedError:
            pass  # the state machine already marked it ABORTED
        except RuntimeError as exc:
            if str(exc) == "crash":
                raise
            sm.fail_mission(str(exc))


def two_steps(sm: StateMachine) -> None:
    for name in ("write", "test"):
        sm.begin_step(name, role=AgentRole.DEV)
        sm.end_step(tool_result=ToolResult.ok(output=name))


def endless_steps(sm: StateMachine) -> None:
    for _ in range(500):
        sm.begin_step("work", role=AgentRole.DEV)
        sm.end_step(tool_result=ToolResult.ok(output="x"))
        time.sleep(0.03)


def crash(sm: StateMachine) -> None:
    sm.begin_step("boom", role=AgentRole.DEV)
    raise RuntimeError("crash")


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    shutil.copy(REPO_ROOT / "aegis.toml", tmp_path / "aegis.toml")
    api._mission_controls.clear()
    api._event_buffer.clear()
    api._event_counter = 0
    api._clients.clear()
    api.init_app(tmp_path / "api.db")
    monkeypatch.setattr(api, "_build_orchestrator", lambda **kw: FakeOrchestrator(**kw))
    with TestClient(api.app) as test_client:
        yield test_client
    for ctrl in api._mission_controls.values():
        ctrl["status"] = "CANCELLED"


def launch(client: TestClient, tmp_path: Path, goal: str = "Build a thing", **extra) -> str:
    res = client.post(
        "/api/missions", json={"goal": goal, "workspace": str(tmp_path / "ws"), **extra}
    )
    assert res.status_code == 200, res.text
    assert res.json()["success"] is True
    return res.json()["session_id"]


# ------------------------------------------------------------------ launching really runs
def test_launch_runs_the_orchestrator_and_persists_the_mission(client, tmp_path):
    FakeOrchestrator.behaviour = staticmethod(two_steps)
    session_id = launch(client, tmp_path)
    wait_for(lambda: _status(session_id) == "COMPLETED")

    missions = client.get("/api/missions").json()["missions"]
    assert [m["session_id"] for m in missions] == [session_id]
    assert missions[0]["status"] == "COMPLETED"
    assert len(client.get(f"/api/missions/{session_id}/steps").json()["steps"]) == 2


def test_launch_creates_a_git_workspace_with_a_baseline_commit(client, tmp_path):
    FakeOrchestrator.behaviour = staticmethod(lambda sm: None)
    launch(client, tmp_path)
    ws = tmp_path / "ws"
    assert (ws / ".git").is_dir()
    log = subprocess.run(["git", "log", "--oneline"], cwd=ws, capture_output=True, text=True)
    assert "AegisOS baseline" in log.stdout


def test_launch_rejects_an_empty_goal(client, tmp_path):
    res = client.post("/api/missions", json={"goal": "   ", "workspace": str(tmp_path / "ws")})
    assert res.status_code == 422


def test_blank_or_dot_workspace_gets_its_own_folder_and_never_the_aegis_source_tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    expected = (tmp_path / "workspaces" / "mission-1").resolve()
    assert api.resolve_workspace(".", "mission-1") == expected
    assert api.resolve_workspace("", "mission-1") == expected
    assert api.resolve_workspace(str(Path(api.__file__).parent), "mission-1") == expected
    assert api.resolve_workspace(str(tmp_path / "mine"), "mission-1") == (tmp_path / "mine").resolve()


def test_two_missions_never_share_a_folder(client, tmp_path):
    FakeOrchestrator.behaviour = staticmethod(lambda sm: None)
    ids = []
    for goal in ("first", "second"):
        res = client.post("/api/missions", json={"goal": goal, "workspace": "."})
        assert res.status_code == 200, res.text
        ids.append(res.json()["session_id"])
        wait_for(lambda sid=ids[-1]: _status(sid) == "COMPLETED")
    assert (tmp_path / "workspaces" / ids[0] / ".git").is_dir()
    assert (tmp_path / "workspaces" / ids[1] / ".git").is_dir()
    assert ids[0] != ids[1]


def test_streamed_llm_tokens_never_reach_the_feed(client):
    from aegis_os.kernel.events import LLMTokenEvent
    from aegis_os.kernel.state import AgentRole

    api.global_bus.publish(LLMTokenEvent(role=AgentRole.DEV, kind="text", content="x"))
    assert [e for e in api._event_buffer if e["event_type"] == "LLMTokenEvent"] == []


# ------------------------------------------------------------------ download the finished project
def test_download_returns_the_project_without_secrets_or_git(client, tmp_path):
    ws = tmp_path / "workspaces" / "dl-mission-1"
    (ws / ".git").mkdir(parents=True)
    (ws / ".git" / "config").write_text("x")
    (ws / "app.py").write_text("print('hi')\n")
    (ws / ".env").write_text("NVIDIA_API_KEY=secret\n")
    (ws / "pkg").mkdir()
    (ws / "pkg" / "mod.py").write_text("x = 1\n")
    res = client.get("/api/missions/dl-mission-1/download")
    assert res.status_code == 200 and res.headers["content-type"] == "application/zip"
    import io
    import zipfile as zf

    names = zf.ZipFile(io.BytesIO(res.content)).namelist()
    assert "app.py" in names and any(n.replace("\\", "/") == "pkg/mod.py" for n in names)
    assert not any(n.startswith(".git") or n.startswith(".env") for n in names)


def test_download_rejects_path_tricks_and_unknown_missions(client):
    assert client.get("/api/missions/%2e%2e/download").status_code in {400, 404}
    assert client.get("/api/missions/..%2f..%2fetc/download").status_code in {400, 404}
    assert client.get("/api/missions/does-not-exist/download").status_code == 404


# ------------------------------------------------------------------ live events
def test_events_from_the_worker_thread_reach_websocket_clients(client, tmp_path):
    FakeOrchestrator.behaviour = staticmethod(two_steps)
    session_id = launch(client, tmp_path)
    wait_for(lambda: _status(session_id) == "COMPLETED")
    with client.websocket_connect("/api/events?last_event_id=0") as ws:
        seen = set()
        for _ in range(40):
            seen.add(ws.receive_json()["event_type"])
            if {"MissionStatusChangedEvent", "StepCompletedEvent"} <= seen:
                break
    assert {"MissionStatusChangedEvent", "StepCompletedEvent"} <= seen


def test_event_ids_are_unique_even_with_several_clients(client, tmp_path):
    FakeOrchestrator.behaviour = staticmethod(two_steps)
    with client.websocket_connect("/api/events"), client.websocket_connect("/api/events"):
        session_id = launch(client, tmp_path)
        wait_for(lambda: _status(session_id) == "COMPLETED")
    ids = [e["event_id"] for e in api._event_buffer]
    assert ids == sorted(set(ids))  # no duplicates (the old code appended once per client)


# ------------------------------------------------------------------ controls are real
def test_cancel_really_stops_the_mission(client, tmp_path):
    FakeOrchestrator.behaviour = staticmethod(endless_steps)
    session_id = launch(client, tmp_path)
    wait_for(lambda: _status(session_id) == "RUNNING")
    res = client.post(f"/api/missions/{session_id}/cancel").json()
    assert res["success"] is True
    wait_for(lambda: _status(session_id) == "ABORTED")


def test_pause_freezes_progress_and_resume_continues(client, tmp_path):
    FakeOrchestrator.behaviour = staticmethod(endless_steps)
    session_id = launch(client, tmp_path)
    wait_for(lambda: _status(session_id) == "RUNNING")
    assert client.post(f"/api/missions/{session_id}/pause").json()["success"] is True
    wait_for(lambda: _status(session_id) == "PAUSED")
    frozen = len(client.get(f"/api/missions/{session_id}/steps").json()["steps"])
    time.sleep(0.4)
    assert len(client.get(f"/api/missions/{session_id}/steps").json()["steps"]) == frozen
    assert client.post(f"/api/missions/{session_id}/resume").json()["success"] is True
    wait_for(lambda: _status(session_id) == "RUNNING")
    wait_for(lambda: len(client.get(f"/api/missions/{session_id}/steps").json()["steps"]) > frozen)
    client.post(f"/api/missions/{session_id}/cancel")
    wait_for(lambda: _status(session_id) == "ABORTED")


def test_resume_persisted_paused_mission_after_server_restart(client, tmp_path):
    """If server restarts while a mission is paused, resuming restarts execution from DB."""
    FakeOrchestrator.behaviour = staticmethod(endless_steps)
    session_id = launch(client, tmp_path)
    wait_for(lambda: _status(session_id) == "RUNNING")
    assert client.post(f"/api/missions/{session_id}/pause").json()["success"] is True
    wait_for(lambda: _status(session_id) == "PAUSED")
    # Simulate server restart by clearing in-memory controls
    api._mission_controls.clear()
    assert session_id not in api._mission_controls

    res = client.post(f"/api/missions/{session_id}/resume").json()
    assert res["success"] is True
    assert "resumed from checkpoint" in res["message"]
    wait_for(lambda: _status(session_id) == "RUNNING")
    client.post(f"/api/missions/{session_id}/cancel")
    wait_for(lambda: _status(session_id) == "ABORTED")



def test_resume_budget_is_not_implicitly_extended():
    state = AgentState(
        mission_goal="budget test",
        status=MissionStatus.PAUSED,
        current_step_index=3,
        max_steps=60,
        max_tokens=800_000,
        tokens_used=799_999,
    )

    assert api._resume_budget_block_reason(state) is None
    assert state.max_tokens == 800_000
    assert state.max_steps == 60

    state.tokens_used = 800_000
    reason = api._resume_budget_block_reason(state)
    assert reason is not None
    assert "Token budget exhausted" in reason
    assert state.max_tokens == 800_000
    assert state.max_steps == 60


def test_controls_on_unknown_missions_report_failure_instead_of_pretending(client):
    res = client.post("/api/missions/not-running/pause").json()
    assert res["success"] is False


def test_a_crashing_orchestrator_marks_the_mission_failed_not_running(client, tmp_path):
    FakeOrchestrator.behaviour = staticmethod(crash)
    session_id = launch(client, tmp_path)
    wait_for(lambda: _status(session_id) == "FAILED")
    store = CheckpointStore(api._db_path)
    try:
        state = store.load_latest_state(session_id)
        assert "crash" in state.context_variables["failure_reason"]
        assert state.step_history[-1].status != StepStatus.RUNNING
    finally:
        store.close()


# ------------------------------------------------------------------ memory + stats are real
def test_finished_missions_are_recorded_in_memory(client, tmp_path):
    FakeOrchestrator.behaviour = staticmethod(two_steps)
    session_id = launch(client, tmp_path, goal="Remember me")
    wait_for(lambda: _status(session_id) == "COMPLETED")
    episodes = wait_for(lambda: client.get("/api/memory").json()["episodes"])
    assert episodes[0]["objective"] == "Remember me" and episodes[0]["success"] is True


def test_stats_come_from_the_database_and_have_no_fake_defaults(client, tmp_path):
    empty = client.get("/api/stats").json()
    assert empty["total"] == 0 and empty["success_rate"] is None and empty["total_tokens"] == 0

    FakeOrchestrator.behaviour = staticmethod(two_steps)
    ok_id = launch(client, tmp_path, goal="ok")
    wait_for(lambda: _status(ok_id) == "COMPLETED")
    FakeOrchestrator.behaviour = staticmethod(crash)
    bad_id = launch(client, tmp_path, goal="bad")
    wait_for(lambda: _status(bad_id) == "FAILED")

    stats = client.get("/api/stats").json()
    assert stats["total"] == 2 and stats["completed"] == 1 and stats["failed"] == 1
    assert stats["success_rate"] == 0.5
    assert stats["total_steps"] >= 3


def test_mission_list_is_newest_first(client, tmp_path):
    FakeOrchestrator.behaviour = staticmethod(two_steps)
    first = launch(client, tmp_path, goal="first")
    wait_for(lambda: _status(first) == "COMPLETED")
    time.sleep(0.02)
    second = launch(client, tmp_path, goal="second")
    wait_for(lambda: _status(second) == "COMPLETED")
    assert client.get("/api/missions").json()["missions"][0]["session_id"] == second


# ------------------------------------------------------------------ zombie cleanup
def _persist_state(status: MissionStatus, *, minutes_old: float) -> str:
    store = CheckpointStore(api._db_path)
    state = AgentState(mission_goal="zombie", status=status)
    machine = StateMachine(state=state, checkpoint_store=store)
    machine.begin_step("stuck", role=AgentRole.DEV)  # leaves a RUNNING step behind
    old = (datetime.now(UTC) - timedelta(minutes=minutes_old)).isoformat()
    with store._conn:
        store._conn.execute(
            "UPDATE missions SET updated_at = ? WHERE session_id = ?", (old, state.session_id)
        )
    store.close()
    return state.session_id


def test_reaper_fails_stale_running_missions_but_not_fresh_ones(client):
    stale = _persist_state(MissionStatus.RUNNING, minutes_old=60)
    fresh = _persist_state(MissionStatus.RUNNING, minutes_old=1)
    assert api.reap_interrupted_missions(api.global_store) == 1
    assert _status(stale) == "FAILED"
    assert _status(fresh) == "RUNNING"
    store = CheckpointStore(api._db_path)
    try:
        assert store.load_latest_state(stale).step_history[-1].status != StepStatus.RUNNING
    finally:
        store.close()


# ------------------------------------------------------------------ honest diff + acceptance
def test_diff_shows_only_what_the_mission_changed(client, tmp_path):
    def write_a_file(sm: StateMachine) -> None:
        (tmp_path / "ws" / "hello.py").write_text("print('hi')\n")
        two_steps(sm)

    FakeOrchestrator.behaviour = staticmethod(write_a_file)
    orig_execute = FakeOrchestrator.execute_mission

    def execute_with_context(self, goal):
        from aegis_os.verification.workspace_audit import current_commit

        ws = Path(self.kwargs["workspace_root"])
        self.machine.state.context_variables["workspace_root"] = str(ws)
        self.machine.state.context_variables["base_commit"] = current_commit(ws)
        orig_execute(self, goal)

    FakeOrchestrator.execute_mission = execute_with_context
    try:
        session_id = launch(client, tmp_path)
        wait_for(lambda: _status(session_id) == "COMPLETED")
    finally:
        FakeOrchestrator.execute_mission = orig_execute
    data = client.get(f"/api/missions/{session_id}/diff").json()
    assert data["files_changed"] == ["hello.py"]
    assert "+print('hi')" in data["diff"]


def test_diff_for_a_mission_without_records_does_not_show_the_repos_last_commit(client, tmp_path):
    FakeOrchestrator.behaviour = staticmethod(two_steps)
    session_id = launch(client, tmp_path)
    wait_for(lambda: _status(session_id) == "COMPLETED")
    data = client.get(f"/api/missions/{session_id}/diff").json()
    assert data["files_changed"] == [] and "No diff recorded" in data["diff"]


def test_acceptance_never_reports_a_pass_for_a_failed_mission(client, tmp_path):
    FakeOrchestrator.behaviour = staticmethod(crash)
    session_id = launch(client, tmp_path)
    wait_for(lambda: _status(session_id) == "FAILED")
    items = client.get(f"/api/missions/{session_id}/acceptance").json()["criteria"]
    assert items and not any(item["passed"] for item in items)
