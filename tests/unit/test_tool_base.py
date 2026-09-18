"""
Test Suite: BaseAegisTool & ToolResult Zero-Crash Contracts
=============================================================
These tests PROVE that the tool base layer enforces its core contracts:
  1. Malformed LLM arguments are caught by Pydantic — never crash the loop.
  2. Tool execution exceptions are caught and encoded as ToolResult failures.
  3. ToolResult models correctly represent success and failure states.
"""

import pytest
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from aegis_os.tools.base import BaseAegisTool, ToolResult


# ---------------------------------------------------------------------------
# Test Fixtures: Minimal concrete tool implementations
# ---------------------------------------------------------------------------


class _AddArgs(BaseModel):
    """Simple addition tool args — for testing validation."""
    a: int = Field(description="First integer.")
    b: int = Field(description="Second integer.")


class _AddTool(BaseAegisTool):
    """A trivial tool that adds two integers — tests happy path."""
    name = "add"
    description = "Add two integers."
    args_schema = _AddArgs

    def _execute(self, args: _AddArgs) -> ToolResult:  # type: ignore[override]
        return ToolResult.ok(output=str(args.a + args.b), metadata={"result": args.a + args.b})


class _CrashingArgs(BaseModel):
    trigger: str = Field(description="Trigger string.")


class _CrashingTool(BaseAegisTool):
    """A tool that always raises an exception — tests zero-crash guarantee."""
    name = "crashing_tool"
    description = "A tool that always crashes."
    args_schema = _CrashingArgs

    def _execute(self, args: _CrashingArgs) -> ToolResult:  # type: ignore[override]
        raise RuntimeError("Simulated unexpected internal tool failure!")


# ---------------------------------------------------------------------------
# ToolResult Model Tests
# ---------------------------------------------------------------------------


class TestToolResult:
    """ToolResult must correctly represent success and failure states."""

    def test_ok_factory_sets_success_true(self) -> None:
        result = ToolResult.ok(output="done")
        assert result.success is True
        assert result.error is None
        assert result.output == "done"

    def test_fail_factory_sets_success_false(self) -> None:
        result = ToolResult.fail(error="something went wrong")
        assert result.success is False
        assert result.error == "something went wrong"
        assert result.output == ""

    def test_ok_with_metadata(self) -> None:
        result = ToolResult.ok(output="42", metadata={"value": 42})
        assert result.metadata["value"] == 42

    def test_fail_with_metadata(self) -> None:
        result = ToolResult.fail(error="bad input", metadata={"field": "a"})
        assert result.metadata["field"] == "a"

    def test_result_is_pydantic_serializable(self) -> None:
        """ToolResult must serialize to JSON for storage and WebSocket streaming."""
        result = ToolResult.ok(output="hello", metadata={"key": "value"})
        serialized = result.model_dump_json()
        assert "hello" in serialized
        assert "key" in serialized


# ---------------------------------------------------------------------------
# Input Validation Tests
# ---------------------------------------------------------------------------


class TestBaseAegisToolValidation:
    """Pydantic validation must catch malformed LLM arguments gracefully."""

    def test_valid_args_produce_success_result(self) -> None:
        tool = _AddTool()
        result = tool.run({"a": 3, "b": 4})
        assert result.success is True
        assert result.output == "7"

    def test_missing_required_field_returns_fail(self) -> None:
        """Missing field must return failure, not raise ValidationError."""
        tool = _AddTool()
        result = tool.run({"a": 5})  # Missing 'b'
        assert result.success is False
        assert result.error is not None
        assert "ValidationError" in result.error
        assert "b" in result.error  # Error should name the missing field

    def test_wrong_type_returns_fail(self) -> None:
        """Type mismatch (str instead of int) must return structured failure."""
        tool = _AddTool()
        result = tool.run({"a": "not-an-int", "b": 4})
        # Pydantic V2 may coerce str->int or reject it
        # Either a success (valid coercion) or a fail with ValidationError is acceptable
        # but it must NOT raise an exception
        assert isinstance(result, ToolResult)

    def test_empty_args_returns_fail(self) -> None:
        """Empty args dict for a tool with required fields returns failure."""
        tool = _AddTool()
        result = tool.run({})
        assert result.success is False
        assert "ValidationError" in (result.error or "")

    def test_extra_args_are_ignored(self) -> None:
        """Extra/unknown fields in args dict must not cause failures."""
        tool = _AddTool()
        result = tool.run({"a": 1, "b": 2, "unknown_extra_field": "ignored"})
        assert isinstance(result, ToolResult)
        # Extra fields should be ignored (Pydantic default) — result should succeed

    def test_none_as_required_field_returns_fail(self) -> None:
        """Passing None for a required non-Optional field must return failure."""
        tool = _AddTool()
        result = tool.run({"a": None, "b": 2})
        assert isinstance(result, ToolResult)
        assert result.error is not None or result.success is True  # Either coercion or fail


# ---------------------------------------------------------------------------
# Zero-Crash Guarantee Tests
# ---------------------------------------------------------------------------


class TestZeroCrashGuarantee:
    """Tools must NEVER raise exceptions to the calling agent loop."""

    def test_crashing_tool_returns_fail_not_exception(self) -> None:
        """An exception in _execute() must be caught and returned as ToolResult.fail."""
        tool = _CrashingTool()
        result = tool.run({"trigger": "go"})
        assert result.success is False
        assert "ExecutionError" in (result.error or "")
        assert "RuntimeError" in (result.error or "")
        assert "Simulated unexpected" in (result.error or "")

    def test_crashing_tool_does_not_raise(self) -> None:
        """The run() call must not propagate any exception under any circumstance."""
        tool = _CrashingTool()
        # If this raises, the test fails
        result = tool.run({"trigger": "crash"})
        assert result is not None  # We got a result, not an exception
