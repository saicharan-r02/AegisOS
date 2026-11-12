from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from aegis_os.kernel.context import (
    ContextManager,
    LargeOutputStore,
    RoleContextBudget,
    redact_sensitive_text,
)
from aegis_os.kernel.providers import estimate_tokens


def test_two_hundred_thousand_character_output_is_saved_and_bounded(tmp_path: Path) -> None:
    full_output = "BEGIN\n" + ("ordinary output line\n" * 10_000) + "END"
    manager = ContextManager(
        budgets={"DEV": RoleContextBudget(window_tokens=32_000, max_tool_output_tokens=500)},
        output_store=LargeOutputStore(tmp_path),
    )

    excerpt = manager.store_or_truncate(full_output, "DEV")

    assert estimate_tokens(excerpt) < 1_000
    assert "Full redacted output artifact_id=" in excerpt
    reference = excerpt.split("Full redacted output artifact_id=", 1)[1].split(";", 1)[0]
    lines=full_output.splitlines()
    retrieved="\n".join(
        manager.output_store.read(reference,start_line=start,end_line=start+499)
        for start in range(1,len(lines)+1,500)
    )
    assert retrieved==full_output


def test_context_compaction_keeps_pinned_goal_and_newest_objective() -> None:
    manager = ContextManager(
        budgets={"DEV": RoleContextBudget(window_tokens=100, compact_at_fraction=0.7)}
    )
    messages = [
        SystemMessage(content="system rules"),
        *[HumanMessage(content=f"old observation {index} " + "x" * 300) for index in range(5)],
        HumanMessage(content="Current Objective: preserve this latest request."),
    ]

    compacted = manager.compact(messages, "DEV", pinned_context='{"goal":"pinned goal"}')
    content = "\n".join(str(message.content) for message in compacted)

    assert "system rules" in content
    assert "pinned goal" in content
    assert "preserve this latest request" in content
    assert "Earlier conversation summary" in content
    assert estimate_tokens(compacted) <= 70


def test_sensitive_output_is_redacted_before_storage_and_prompting(tmp_path: Path) -> None:
    manager = ContextManager(output_store=LargeOutputStore(tmp_path))
    secret_output = "API_KEY=plain-secret-value\n" + ("normal text\n" * 1_000)

    excerpt = manager.store_or_truncate(secret_output, "DEV")

    assert "plain-secret-value" not in excerpt
    reference = excerpt.split("Full redacted output artifact_id=", 1)[1].split(";", 1)[0]
    assert "plain-secret-value" not in manager.output_store.read(reference)
    assert "API_KEY=[REDACTED]" in redact_sensitive_text("API_KEY=plain-secret-value")
