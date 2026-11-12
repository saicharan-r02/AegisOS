"""MissionTracer provides contextual span creation, SQLite trace storage, and JSONL export."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aegis_os.security.redactor import SecretRedactor
from aegis_os.tracing.models import MissionTrace, SpanRecord, SpanStatus, SpanType


class MissionTracer:
    """Manages execution spans with SQLite storage and secret redaction."""

    def __init__(
        self,
        mission_id: str,
        objective: str = "",
        db_path: Path | str = ":memory:",
        redactor: SecretRedactor | None = None,
    ) -> None:
        self.mission_id = mission_id
        self.objective = objective
        self.db_path = str(db_path)
        self.redactor = redactor or SecretRedactor()
        self._active_spans: list[SpanRecord] = []
        self._all_spans: list[SpanRecord] = []
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    mission_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_ms REAL,
                    total_tokens INTEGER,
                    total_cost_usd REAL,
                    status TEXT NOT NULL
                );
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS spans (
                    span_id TEXT PRIMARY KEY,
                    parent_span_id TEXT,
                    mission_id TEXT NOT NULL,
                    span_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_ms REAL,
                    status TEXT NOT NULL,
                    input_data TEXT,
                    output_data TEXT,
                    tokens_in INTEGER,
                    tokens_out INTEGER,
                    cost_usd REAL,
                    error TEXT,
                    FOREIGN KEY (mission_id) REFERENCES traces(mission_id) ON DELETE CASCADE
                );
            """)
            now_iso = datetime.now(UTC).isoformat()
            self._conn.execute(
                """
                INSERT OR IGNORE INTO traces (mission_id, objective, started_at, status)
                VALUES (?, ?, ?, 'RUNNING');
            """,
                (self.mission_id, self.objective, now_iso),
            )

    def _redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact secrets in dict keys and values."""
        redacted: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, str):
                redacted[k] = self.redactor.redact(v)
            elif isinstance(v, dict):
                redacted[k] = self._redact_dict(v)
            elif isinstance(v, list):
                redacted[k] = [
                    self.redactor.redact(item) if isinstance(item, str) else item for item in v
                ]
            else:
                redacted[k] = v
        return redacted

    @contextmanager
    def span(
        self,
        name: str,
        span_type: SpanType = SpanType.TOOL_CALL,
        role: str | None = None,
        input_data: dict[str, Any] | None = None,
    ) -> Generator[SpanRecord, None, None]:
        """Context manager to record a span with parent tracking."""
        parent_id = self._active_spans[-1].span_id if self._active_spans else None
        safe_input = self._redact_dict(input_data or {})
        record = SpanRecord(
            span_id=str(uuid.uuid4())[:8],
            parent_span_id=parent_id,
            mission_id=self.mission_id,
            span_type=span_type,
            name=name,
            role=role,
            input_data=safe_input,
        )
        self._active_spans.append(record)
        self._all_spans.append(record)
        try:
            yield record
            if record.status == SpanStatus.RUNNING:
                record.finish(status=SpanStatus.SUCCESS)
        except Exception as exc:
            record.finish(status=SpanStatus.FAILED, error=str(exc))
            raise
        finally:
            if self._active_spans and self._active_spans[-1].span_id == record.span_id:
                self._active_spans.pop()
            self._persist_span(record)

    def _persist_span(self, span: SpanRecord) -> None:
        """Save finished span to SQLite."""
        safe_output = self._redact_dict(span.output_data)
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO spans (
                    span_id, parent_span_id, mission_id, span_type, name, role,
                    started_at, ended_at, duration_ms, status, input_data, output_data,
                    tokens_in, tokens_out, cost_usd, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
                (
                    span.span_id,
                    span.parent_span_id,
                    span.mission_id,
                    span.span_type.value,
                    span.name,
                    span.role,
                    span.started_at.isoformat(),
                    span.ended_at.isoformat() if span.ended_at else None,
                    span.duration_ms,
                    span.status.value,
                    json.dumps(span.input_data),
                    json.dumps(safe_output),
                    span.tokens_in,
                    span.tokens_out,
                    span.cost_usd,
                    span.error,
                ),
            )

    def finish_mission(self, status: str = "COMPLETED") -> MissionTrace:
        """Conclude the mission trace and update aggregate statistics."""
        ended_at = datetime.now(UTC)
        trace = self.get_trace()
        trace.ended_at = ended_at
        trace.status = status
        trace.aggregate_metrics()

        with self._conn:
            self._conn.execute(
                """
                UPDATE traces
                SET ended_at = ?, duration_ms = ?, total_tokens = ?, total_cost_usd = ?, status = ?
                WHERE mission_id = ?;
            """,
                (
                    ended_at.isoformat(),
                    trace.duration_ms,
                    trace.total_tokens,
                    trace.total_cost_usd,
                    status,
                    self.mission_id,
                ),
            )
        return trace

    def get_trace(self) -> MissionTrace:
        """Assemble complete trace from database records."""
        cursor = self._conn.execute("SELECT * FROM traces WHERE mission_id = ?", (self.mission_id,))
        t_row = cursor.fetchone()
        obj = t_row["objective"] if t_row else self.objective
        status = t_row["status"] if t_row else "RUNNING"

        cursor = self._conn.execute(
            "SELECT * FROM spans WHERE mission_id = ? ORDER BY started_at ASC", (self.mission_id,)
        )
        spans: list[SpanRecord] = []
        for r in cursor.fetchall():
            inp = json.loads(r["input_data"] or "{}")
            outp = json.loads(r["output_data"] or "{}")
            spans.append(
                SpanRecord(
                    span_id=r["span_id"],
                    parent_span_id=r["parent_span_id"],
                    mission_id=r["mission_id"],
                    span_type=SpanType(r["span_type"]),
                    name=r["name"],
                    role=r["role"],
                    started_at=datetime.fromisoformat(r["started_at"]),
                    ended_at=datetime.fromisoformat(r["ended_at"]) if r["ended_at"] else None,
                    duration_ms=r["duration_ms"] or 0.0,
                    status=SpanStatus(r["status"]),
                    input_data=inp,
                    output_data=outp,
                    tokens_in=r["tokens_in"] or 0,
                    tokens_out=r["tokens_out"] or 0,
                    cost_usd=r["cost_usd"] or 0.0,
                    error=r["error"],
                )
            )

        trace = MissionTrace(
            mission_id=self.mission_id,
            objective=obj,
            spans=spans,
            status=status,
        )
        trace.aggregate_metrics()
        return trace

    def export_jsonl(self, output_path: Path | str) -> Path:
        """Export all spans as newline-delimited JSON."""
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        trace = self.get_trace()
        with open(out, "w", encoding="utf-8") as f:
            f.write(
                json.dumps({"type": "trace_header", "mission": trace.model_dump(mode="json")})
                + "\n"
            )
            for sp in trace.spans:
                f.write(json.dumps({"type": "span", "data": sp.model_dump(mode="json")}) + "\n")
        return out

    def close(self) -> None:
        self._conn.close()
