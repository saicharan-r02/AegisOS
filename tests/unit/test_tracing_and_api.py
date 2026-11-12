"""Unit tests for Phase 8: Mission tracing, secret redaction, replay engine, and API endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aegis_os.api import app, init_app
from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.state import AgentRole, AgentState, MissionStatus, StepRecord
from aegis_os.security.redactor import SecretRedactor
from aegis_os.tracing.models import SpanStatus, SpanType
from aegis_os.tracing.replay import ReplayEngine
from aegis_os.tracing.tracer import MissionTracer


class TestSecretRedactor:
    """Validate regex and Shannon entropy secret detection."""

    def test_redacts_openai_and_anthropic_keys(self):
        redactor = SecretRedactor()
        sample = "Here is my key: sk-proj-1234567890abcdefghijklmnop and anthropic: sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
        redacted = redactor.redact(sample)
        assert "sk-proj-1234567890" not in redacted
        assert "sk-ant-api03-" not in redacted
        assert "[REDACTED_SECRET]" in redacted

    def test_redacts_groq_and_bearer_tokens(self):
        redactor = SecretRedactor()
        sample = "export GROQ_API_KEY=gsk_9876543210abcdefghijklmnop and Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token"
        redacted = redactor.redact(sample)
        assert "gsk_9876543210" not in redacted
        assert "[REDACTED_SECRET]" in redacted

    def test_redacts_high_entropy_strings(self):
        redactor = SecretRedactor(entropy_threshold=3.8, min_length=24)
        # Random high-entropy token
        high_ent = "7fA9bK2mZ8qX5vN1wP4tL6yR3jH0"
        sample = f"Configuration token={high_ent} saved"
        redacted = redactor.redact(sample)
        assert high_ent not in redacted


class TestMissionTracer:
    """Validate structured span tracking, nesting, and JSONL export."""

    def test_span_lifecycle_and_nesting(self, tmp_path: Path):
        db_path = tmp_path / "traces.db"
        tracer = MissionTracer(mission_id="sess-001", objective="Build auth module", db_path=db_path)

        with tracer.span(name="step_1_planning", span_type=SpanType.AGENT_STEP, role="CTO") as step_span:
            step_span.tokens_in = 150
            step_span.tokens_out = 75
            step_span.cost_usd = 0.002

            with tracer.span(name="tool_call_ast", span_type=SpanType.TOOL_CALL, role="CTO") as tool_span:
                tool_span.output_data = {"symbols": ["User", "login"]}
                tool_span.finish(status=SpanStatus.SUCCESS)

        finished_trace = tracer.finish_mission(status="COMPLETED")
        assert len(finished_trace.spans) == 2
        assert finished_trace.total_tokens == 225
        assert finished_trace.total_cost_usd == pytest.approx(0.002)

        # Check nesting
        spans = finished_trace.spans
        assert spans[1].parent_span_id == spans[0].span_id
        tracer.close()

    def test_redaction_inside_span_data(self, tmp_path: Path):
        db_path = tmp_path / "traces.db"
        tracer = MissionTracer(mission_id="sess-sec", objective="Redact secrets", db_path=db_path)

        with tracer.span(name="call_llm", span_type=SpanType.LLM_CALL, input_data={"api_key": "sk-1234567890abcdefghijklmnop"}) as sp:
            sp.output_data = {"token": "gsk_abcdefghijklmnop12345678"}

        trace = tracer.get_trace()
        assert len(trace.spans) == 1
        assert "sk-1234567890" not in json.dumps(trace.spans[0].input_data)
        assert "gsk_abcdef" not in json.dumps(trace.spans[0].output_data)
        tracer.close()

    def test_export_jsonl(self, tmp_path: Path):
        db_path = tmp_path / "traces.db"
        jsonl_path = tmp_path / "trace.jsonl"
        tracer = MissionTracer(mission_id="sess-jsonl", objective="Export trace", db_path=db_path)

        with tracer.span(name="span_a", span_type=SpanType.TOOL_CALL):
            pass

        tracer.export_jsonl(jsonl_path)
        assert jsonl_path.exists()
        lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2  # header + 1 span
        assert json.loads(lines[0])["type"] == "trace_header"
        tracer.close()


class TestReplayEngine:
    """Validate zero-LLM deterministic replay of past mission steps."""

    def test_replay_terminal_steps(self, tmp_path: Path):
        db_path = tmp_path / "checkpoints.db"
        store = CheckpointStore(db_path)

        # Record a dummy mission with steps
        state = AgentState(
            session_id="replay-test",
            mission_goal="Build calculator",
            status=MissionStatus.COMPLETED,
        )
        s1 = state.add_step(role=AgentRole.CTO, task_description="Plan architecture")
        s1.complete()
        s2 = state.add_step(role=AgentRole.DEV, task_description="Implement add function")
        s2.complete()
        store.save_checkpoint(state)

        replay = ReplayEngine(checkpoint_store=store)
        replayed_steps: list[int] = []

        def callback(idx: int, step: StepRecord):
            replayed_steps.append(idx)

        count = replay.replay_terminal("replay-test", delay_sec=0.0, step_callback=callback)
        assert count == 2
        assert replayed_steps == [1, 2]
        store.close()


class TestAPIPhase8Endpoints:
    """Validate FastAPI mission controls, diffs, approvals, and security."""

    @pytest.fixture
    def client(self, tmp_path: Path):
        db_path = tmp_path / "api_test.db"
        init_app(db_path)
        return TestClient(app)

    def test_mission_launch_and_list(self, client: TestClient):
        res = client.post("/api/missions", json={
            "goal": "Test API launch",
            "workspace": ".",
            "strategy": "adaptive"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["session_id"].startswith("mission-")

    def test_pause_resume_cancel_controls(self, client: TestClient):
        sess = "ctrl-sess"
        # Pause
        r_pause = client.post(f"/api/missions/{sess}/pause")
        assert r_pause.status_code == 200
        assert r_pause.json()["action"] == "pause"

        # Resume
        r_res = client.post(f"/api/missions/{sess}/resume")
        assert r_res.status_code == 200
        assert r_res.json()["action"] == "resume"

        # Cancel
        r_can = client.post(f"/api/missions/{sess}/cancel")
        assert r_can.status_code == 200
        assert r_can.json()["action"] == "cancel"

    def test_approvals_inbox_and_action(self, client: TestClient):
        from aegis_os.api import _pending_approvals
        from aegis_os.api_models import ApprovalItem

        _pending_approvals["appr-1"] = ApprovalItem(
            approval_id="appr-1",
            session_id="sess-appr",
            command="pip install dangerous-package",
            reason="Unapproved package install",
            timestamp="2026-10-21T00:00:00Z",
            status="PENDING",
        )

        # List approvals
        res = client.get("/api/approvals")
        assert res.status_code == 200
        items = res.json()
        assert len(items) >= 1
        assert items[0]["approval_id"] == "appr-1"

        # Act on approval
        act_res = client.post("/api/approvals/appr-1/action", json={"action": "approve"})
        assert act_res.status_code == 200
        assert act_res.json()["status"] == "APPROVED"

    def test_get_acceptance_criteria(self, client: TestClient):
        res = client.get("/api/missions/sess-demo/acceptance")
        assert res.status_code == 200
        data = res.json()
        assert "criteria" in data
        assert len(data["criteria"]) >= 1
