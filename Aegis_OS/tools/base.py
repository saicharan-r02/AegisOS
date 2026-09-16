"""
Tool Contracts: BaseAegisTool & ToolResult
==========================================
This is the foundational safety contract for every tool in AegisOS.

The Core Principle:
    An LLM can hallucinate incorrect arguments. A tool can encounter unexpected
    filesystem states or network failures. In a multi-agent loop, ANY unhandled
    exception will crash the entire mission.

    Therefore, the law is:
        A tool MUST NEVER raise an exception to the calling agent loop.
        Failures are encoded as ToolResult(success=False, error=...).
        The agent loop OBSERVES the failure and decides how to respond.

Design Decisions:
    - `ToolResult` is a Pydantic model so its JSON serialization is automatic.
      This allows tool results to be stored in the state DB, streamed over
      WebSockets, and injected back into LLM context without any conversion.

    - `BaseAegisTool.run()` is the ONLY entry point for all tools. It handles:
        1. Pydantic V2 input validation (raises ValidationError → ToolResult failure)
        2. Calling the subclass `_execute()` method
        3. Catching ALL exceptions from `_execute()` → ToolResult failure

    - Subclasses implement `_execute()` which ONLY needs to handle the happy path.
      Error handling is delegated to the base class contract.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError


class ToolResult(BaseModel):
    """
    The structured, immutable result of any AegisOS tool execution.

    Both success and failure states are represented here — never via exceptions.
    The agent loop inspects `success` to decide its next action.
    """

    success: bool = Field(description="True if the tool completed its intended action.")
    output: str = Field(
        default="",
        description="Human-readable output for the agent to reason about.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Structured error message if success=False. None if success=True.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured data (line counts, file sizes, exit codes, etc.).",
    )

    @classmethod
    def ok(cls, output: str, metadata: Optional[dict[str, Any]] = None) -> "ToolResult":
        """Convenience constructor for successful results."""
        return cls(success=True, output=output, metadata=metadata or {})

    @classmethod
    def fail(cls, error: str, metadata: Optional[dict[str, Any]] = None) -> "ToolResult":
        """Convenience constructor for failure results."""
        return cls(success=False, output="", error=error, metadata=metadata or {})


class BaseAegisTool(ABC):
    """
    Abstract base class for all AegisOS tools.

    Subclasses MUST define:
        - `name: str`                — Machine-readable unique tool name.
        - `description: str`         — Human-readable description for LLM tool selection.
        - `args_schema: type[BaseModel]` — Pydantic model class for argument validation.
        - `_execute(args) -> ToolResult` — The core implementation logic.

    Subclasses MUST NOT:
        - Raise exceptions from `_execute()`.
        - Call `_execute()` directly — always go through `run()`.
    """

    name: str
    description: str
    args_schema: type[BaseModel]

    def run(self, raw_args: dict[str, Any]) -> ToolResult:
        """
        Safe entry point: validate inputs, execute, and catch all errors.

        This method is the gatekeeper. The calling agent loop should call
        only this method — never `_execute()` directly.

        Args:
            raw_args: Dictionary of arguments (typically parsed from LLM JSON output).

        Returns:
            ToolResult — always. Never raises.
        """
        # Step 1: Runtime input validation via Pydantic
        try:
            validated_args = self.args_schema.model_validate(raw_args)
        except ValidationError as exc:
            # Format Pydantic validation errors into actionable agent feedback
            error_details = "; ".join(
                f"Field '{'.'.join(str(l) for l in e['loc'])}': {e['msg']}"
                for e in exc.errors()
            )
            return ToolResult.fail(
                error=(
                    f"[ValidationError] Tool '{self.name}' received invalid arguments. "
                    f"Errors: {error_details}. "
                    f"Please correct the arguments and retry."
                ),
                metadata={"validation_errors": exc.errors()},
            )

        # Step 2: Execute with full exception containment
        try:
            return self._execute(validated_args)
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(
                error=(
                    f"[ExecutionError] Tool '{self.name}' encountered an unexpected error: "
                    f"{type(exc).__name__}: {exc}"
                )
            )

    @abstractmethod
    def _execute(self, args: BaseModel) -> ToolResult:
        """
        Core implementation logic. Called only through `run()`.

        Args:
            args: A fully validated Pydantic model instance.

        Returns:
            ToolResult — success or structured failure. Must not raise.
        """
        ...
