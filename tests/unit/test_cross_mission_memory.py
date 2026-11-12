"""Unit tests and benchmark for Phase 6: Cross-Mission Memory and Continuous Learning."""

from __future__ import annotations

import json
from pathlib import Path

from aegis_os.memory.models import EpisodicMemory
from aegis_os.memory.store import MemoryStore


class TestMemoryStore:
    def test_record_and_retrieve_episodes(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path)

        ep1 = EpisodicMemory(
            episode_id="ep-101",
            objective="Add Stripe payment checkout webhook",
            success=True,
            tasks_executed=["T1", "T2"],
            files_modified=["payments/stripe.py", "tests/test_stripe.py"],
            failure_modes=["SignatureVerificationError on payload"],
            successful_patterns=["Read raw request body bytes before JSON decoding"],
        )
        ep2 = EpisodicMemory(
            episode_id="ep-102",
            objective="Fix database connection pool exhaustion in Celery tasks",
            success=True,
            tasks_executed=["T1"],
            files_modified=["tasks/worker.py"],
            failure_modes=["Too many connections error"],
            successful_patterns=["Use scoped_session and close session in finally block"],
        )

        store.record_episode(ep1)
        store.record_episode(ep2)

        # Query for payment webhook
        matches = store.query_episodes("stripe webhook payload verification", top_k=1)
        assert len(matches) == 1
        assert matches[0].episode_id == "ep-101"
        assert "raw request body" in matches[0].successful_patterns[0]

        # Query for celery database
        db_matches = store.query_episodes("celery pool connections", top_k=1)
        assert len(db_matches) == 1
        assert db_matches[0].episode_id == "ep-102"

    def test_conventions_reinforcement_and_file_sync(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path)

        # First reinforcement
        c1 = store.record_convention(
            pattern="Use pytest-asyncio for async endpoint tests",
            reason="Avoids unhandled coroutine warnings",
        )
        assert c1.success_count == 1

        # Second reinforcement of the same pattern
        c2 = store.record_convention(
            pattern="Use pytest-asyncio for async endpoint tests",
            reason="Avoids unhandled coroutine warnings",
        )
        assert c2.success_count == 2

        # Verify conventions.json mirror was created and contains the convention
        conv_file = tmp_path / ".aegis" / "conventions.json"
        assert conv_file.is_file()
        data = json.loads(conv_file.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["success_count"] == 2

    def test_planning_prompt_formatter(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path)
        store.record_episode(
            EpisodicMemory(
                episode_id="ep-201",
                objective="Add OAuth2 token refresh",
                success=True,
                failure_modes=["Expired token race condition"],
                successful_patterns=["Use atomic Redis lock during token refresh"],
            )
        )

        formatted = store.format_memory_for_planning("Implement OAuth2 authentication")
        assert "Cross-Mission Memory" in formatted
        assert "ep-201" in formatted
        assert "atomic Redis lock" in formatted


class TestPhase6BenchmarkContinuousLearning:
    """Benchmark Phase 6: Verify memory retrieval provides fix patterns on subsequent missions."""

    def test_subsequent_mission_leverages_past_fix_pattern(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path)

        # Mission 1 encountered a tricky codebase quirk (e.g. SQLite thread locking in FastAPI)
        mission_1 = EpisodicMemory(
            episode_id="mission-001",
            objective="Add user preferences endpoint",
            success=False,
            failure_modes=["sqlite3.OperationalError: database is locked in multithreaded test"],
            successful_patterns=["Pass check_same_thread=False to sqlite3.connect when using FastAPI background tasks"],
        )
        store.record_episode(mission_1)

        # Mission 2 is a similar task in the same codebase
        new_objective = "Add user notifications endpoint with sqlite"
        recalled_memories = store.query_episodes(new_objective, top_k=1)

        assert len(recalled_memories) == 1
        recalled = recalled_memories[0]
        assert recalled.episode_id == "mission-001"

        # The planning context receives the exact fix pattern
        planning_context = store.format_memory_for_planning(new_objective)
        assert "check_same_thread=False" in planning_context
        assert "database is locked" in planning_context
