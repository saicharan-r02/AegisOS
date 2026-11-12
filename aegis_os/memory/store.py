"""SQLite-backed episodic memory store with BM25 semantic retrieval and convention learning."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from aegis_os.intelligence.bm25 import BM25Index
from aegis_os.memory.models import CodebaseConvention, EpisodicMemory


class MemoryStore:
    """Manages cross-mission episodic memory and learned conventions in SQLite."""

    def __init__(self, workspace_root: Path, db_path: Path | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.db_path = (db_path or (self.workspace_root / ".aegis" / "memory.db")).resolve()
        self.conventions_file = self.workspace_root / ".aegis" / "conventions.json"
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    episode_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    tasks_executed TEXT NOT NULL,
                    files_modified TEXT NOT NULL,
                    failure_modes TEXT NOT NULL,
                    successful_patterns TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conventions (
                    rule_id TEXT PRIMARY KEY,
                    pattern TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    success_count INTEGER NOT NULL,
                    last_updated REAL NOT NULL
                )
                """
            )
            conn.commit()

    def record_episode(self, episode: EpisodicMemory) -> None:
        """Persist mission memory snapshot."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO episodes (
                    episode_id, objective, success, tasks_executed, files_modified,
                    failure_modes, successful_patterns, timestamp, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode.episode_id,
                    episode.objective,
                    1 if episode.success else 0,
                    json.dumps(episode.tasks_executed),
                    json.dumps(episode.files_modified),
                    json.dumps(episode.failure_modes),
                    json.dumps(episode.successful_patterns),
                    episode.timestamp,
                    json.dumps(episode.metadata),
                ),
            )
            conn.commit()

    def get_all_episodes(self) -> list[EpisodicMemory]:
        """Fetch all stored mission memories."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT episode_id, objective, success, tasks_executed, files_modified,
                       failure_modes, successful_patterns, timestamp, metadata
                FROM episodes ORDER BY timestamp DESC
                """
            )
            rows = cursor.fetchall()

        episodes: list[EpisodicMemory] = []
        for r in rows:
            episodes.append(
                EpisodicMemory(
                    episode_id=r[0],
                    objective=r[1],
                    success=bool(r[2]),
                    tasks_executed=json.loads(r[3]),
                    files_modified=json.loads(r[4]),
                    failure_modes=json.loads(r[5]),
                    successful_patterns=json.loads(r[6]),
                    timestamp=r[7],
                    metadata=json.loads(r[8]),
                )
            )
        return episodes

    def query_episodes(self, query: str, top_k: int = 3) -> list[EpisodicMemory]:
        """Retrieve top_k most relevant past experiences using Okapi BM25."""
        all_eps = self.get_all_episodes()
        if not all_eps:
            return []

        doc_map: dict[str, str] = {}
        for ep in all_eps:
            text = f"{ep.objective} {' '.join(ep.failure_modes)} {' '.join(ep.successful_patterns)} {' '.join(ep.files_modified)}"
            doc_map[ep.episode_id] = text

        bm25 = BM25Index()
        bm25.add_documents(doc_map)
        scored = bm25.query(query, top_k=top_k)

        ep_by_id = {e.episode_id: e for e in all_eps}
        return [ep_by_id[doc_id] for doc_id, _ in scored if doc_id in ep_by_id]

    def record_convention(self, pattern: str, reason: str) -> CodebaseConvention:
        """Register or reinforce a learned codebase convention."""
        rule_id = f"rule-{hash(pattern) & 0xFFFFFFFF:08x}"
        now = time.time()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT success_count FROM conventions WHERE rule_id = ?", (rule_id,))
            row = cursor.fetchone()

            if row:
                count = row[0] + 1
                cursor.execute(
                    "UPDATE conventions SET success_count = ?, last_updated = ? WHERE rule_id = ?",
                    (count, now, rule_id),
                )
            else:
                count = 1
                cursor.execute(
                    "INSERT INTO conventions (rule_id, pattern, reason, success_count, last_updated) VALUES (?, ?, ?, ?, ?)",
                    (rule_id, pattern, reason, count, now),
                )
            conn.commit()

        convention = CodebaseConvention(
            rule_id=rule_id,
            pattern=pattern,
            reason=reason,
            success_count=count,
            last_updated=now,
        )
        self._sync_conventions_file()
        return convention

    def get_conventions(self) -> list[CodebaseConvention]:
        """Return all learned codebase conventions."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT rule_id, pattern, reason, success_count, last_updated FROM conventions ORDER BY success_count DESC"
            )
            rows = cursor.fetchall()

        return [
            CodebaseConvention(
                rule_id=r[0],
                pattern=r[1],
                reason=r[2],
                success_count=r[3],
                last_updated=r[4],
            )
            for r in rows
        ]
    def get_all_conventions(self) -> list[CodebaseConvention]:
        return self.get_conventions()

    def _sync_conventions_file(self) -> None:
        """Mirror conventions to .aegis/conventions.json for human inspection."""
        conventions = self.get_conventions()
        try:
            self.conventions_file.parent.mkdir(parents=True, exist_ok=True)
            self.conventions_file.write_text(
                json.dumps([c.model_dump() for c in conventions], indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def format_memory_for_planning(self, goal: str) -> str:
        """Format top relevant past experiences for the CTO planning prompt."""
        matches = self.query_episodes(goal, top_k=2)
        if not matches:
            return "No relevant past mission experiences found."

        lines = ["### Cross-Mission Memory (Learned from Prior Runs):"]
        for ep in matches:
            outcome = "✅ SUCCESS" if ep.success else "❌ FAILED"
            lines.append(f"- **[{ep.episode_id}]** Objective: '{ep.objective}' ({outcome})")
            if ep.successful_patterns:
                lines.append(f"  Working patterns: {'; '.join(ep.successful_patterns)}")
            if ep.failure_modes:
                lines.append(f"  Pitfalls encountered: {'; '.join(ep.failure_modes)}")
        return "\n".join(lines)

    def format_conventions_for_dev(self) -> str:
        """Format learned conventions into Developer system guidance."""
        conventions = self.get_conventions()
        if not conventions:
            return "No learned codebase conventions recorded yet."

        lines = ["### Learned Codebase Conventions:"]
        for c in conventions[:6]:
            lines.append(
                f"- **{c.pattern}**: {c.reason} (reinforced in {c.success_count} mission(s))"
            )
        return "\n".join(lines)
