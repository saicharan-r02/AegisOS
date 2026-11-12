"""Bounded prompt construction and safe storage for large tool outputs."""

from __future__ import annotations

import math
import re
import tempfile
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from aegis_os.kernel.providers import estimate_tokens

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_-]?key|secret|password|access[_-]?token)\b(\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(
        r"\b(?:sk-[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})\b"
    ),
    re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        re.DOTALL,
    ),
)
_HIGH_ENTROPY_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9+/=_-]{32,}(?![A-Za-z0-9])")
_ARTIFACT_ID = re.compile(r"^[a-f0-9]{32}$")


def _shannon_entropy(value: str) -> float:
    length = len(value)
    counts = Counter(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def redact_sensitive_text(text: str) -> str:
    """Redact recognizable credentials and high-entropy token-like strings."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(
                lambda match: f"{match.group(0)[: match.start(2) - match.start(0)]}[REDACTED]",
                redacted,
            )
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return _HIGH_ENTROPY_TOKEN.sub(
        lambda match: "[REDACTED]" if _shannon_entropy(match.group(0)) >= 4.0 else match.group(0),
        redacted,
    )


def redact_sensitive_value(value: Any) -> Any:
    """Recursively redact sensitive strings in structured state and telemetry."""
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, dict):
        return {str(key): redact_sensitive_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_value(item) for item in value)
    return value


@dataclass(frozen=True)
class RoleContextBudget:
    window_tokens: int = 32_000
    compact_at_fraction: float = 0.7
    max_tool_output_tokens: int = 2_000


@dataclass(frozen=True)
class StoredOutput:
    excerpt: str
    reference: str
    original_tokens: int


class LargeOutputStore:
    """Store full redacted output outside the prompt and return a stable reference."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or Path(tempfile.gettempdir()) / "aegis-os" / "tool-output").resolve()

    def store(self, text: str, max_tokens: int = 2_000) -> StoredOutput:
        redacted = redact_sensitive_text(text)
        self.root.mkdir(parents=True, exist_ok=True)
        artifact_id = uuid.uuid4().hex
        output_path = self.root / f"{artifact_id}.txt"
        output_path.write_text(redacted, encoding="utf-8")
        max_chars = max(256, max_tokens * 4)
        half = max_chars // 2
        excerpt = f"{redacted[:half]}\n[... output shortened ...]\n{redacted[-half:]}"
        return StoredOutput(
            excerpt=excerpt, reference=artifact_id, original_tokens=estimate_tokens(redacted)
        )

    def read(self, artifact_id: str, start_line: int = 1, end_line: int | None = None) -> str:
        """Read a bounded line range by opaque artifact ID; path input is never accepted."""
        if not _ARTIFACT_ID.fullmatch(artifact_id):
            raise ValueError("Invalid output artifact ID.")
        if start_line < 1 or (end_line is not None and end_line < start_line):
            raise ValueError("Output line range must be 1-indexed and ordered.")
        path = (self.root / f"{artifact_id}.txt").resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Output artifact is outside the mission output store.")
        lines = path.read_text(encoding="utf-8").splitlines()
        start = start_line - 1
        stop = end_line if end_line is not None else min(len(lines), start + 500)
        return "\n".join(lines[start:stop])


class ContextManager:
    """Keep prompts within role-specific token limits while preserving pinned context."""

    def __init__(
        self,
        budgets: dict[str, RoleContextBudget] | None = None,
        output_store: LargeOutputStore | None = None,
    ) -> None:
        self.budgets = budgets or {}
        self.output_store = output_store or LargeOutputStore()

    def budget_for(self, role: str) -> RoleContextBudget:
        return self.budgets.get(role.upper(), RoleContextBudget())

    def store_or_truncate(self, text: str, role: str) -> str:
        safe_text = redact_sensitive_text(text)
        budget = self.budget_for(role)
        if estimate_tokens(safe_text) <= budget.max_tool_output_tokens:
            return safe_text
        stored = self.output_store.store(safe_text, max_tokens=budget.max_tool_output_tokens)
        return (
            f"{stored.excerpt}\n\n"
            f"[Full redacted output artifact_id={stored.reference}; {stored.original_tokens} tokens. "
            "Use read_output with that artifact_id and start_line/end_line to inspect more.]"
        )

    def compact(
        self,
        messages: Sequence[BaseMessage],
        role: str,
        pinned_context: str = "",
    ) -> list[BaseMessage]:
        budget = self.budget_for(role)
        threshold = int(budget.window_tokens * budget.compact_at_fraction)
        systems = [message for message in messages if isinstance(message, SystemMessage)]
        non_system = [message for message in messages if not isinstance(message, SystemMessage)]
        pinned = (
            [HumanMessage(content=f"Pinned mission context:\n{pinned_context}")]
            if pinned_context
            else []
        )
        if estimate_tokens(messages) <= threshold:
            return [*systems, *pinned, *non_system]

        newest = non_system[-1:] if non_system else []
        summary_reserve = estimate_tokens("Compacted older conversation messages.")
        available = max(
            0,
            threshold
            - estimate_tokens(systems)
            - estimate_tokens(pinned)
            - estimate_tokens(newest)
            - summary_reserve,
        )

        retained: list[BaseMessage] = []
        dropped = list(non_system[:-1] if newest else non_system)
        summary_text = ""
        if dropped:
            summary_budget_chars = max(128, min(2_000, threshold * 2))
            snippets = [
                f"- {message.type}: {redact_sensitive_text(str(message.content)).strip()[:240]}"
                for message in dropped
            ]
            summary_text = "Earlier conversation summary:\n" + "\n".join(snippets)
            summary_text = summary_text[:summary_budget_chars]
        summary = [HumanMessage(content=summary_text)] if summary_text else []
        available = max(0, available - estimate_tokens(summary))
        for message in reversed(dropped):
            candidate = [message, *retained]
            if estimate_tokens(candidate) > available:
                break
            retained = candidate

        dropped_count = len(dropped) - len(retained)
        if dropped_count == 0:
            summary = []
        elif summary:
            summary = [
                HumanMessage(content=f"Compacted {dropped_count} older messages:\n" + summary_text)
            ]
        return [*systems, *pinned, *summary, *retained, *newest]
