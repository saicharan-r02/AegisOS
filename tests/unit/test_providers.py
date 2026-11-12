from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage

from aegis_os.kernel.providers import (
    LangChainProvider,
    LLMCallResult,
    LLMStreamEvent,
    LLMUsage,
    ModelPricing,
    ProviderCapabilities,
    ProviderRouter,
    ProviderUnavailableError,
)


class _ProviderFailureError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"provider returned {status_code}")
        self.status_code = status_code


class _FakeProvider:
    def __init__(self, name: str, outcomes: list[Any]) -> None:
        self.provider_name = name
        self.model_name = f"{name}-model"
        self.capabilities = ProviderCapabilities()
        self.outcomes = outcomes
        self.calls = 0

    def complete(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> LLMCallResult:
        self.calls += 1
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def stream(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> Iterator[LLMStreamEvent]:
        yield LLMStreamEvent(kind="text", text="streamed")

    def count_tokens(self, messages: Sequence[BaseMessage]) -> int:
        return 10


def _result(provider: str = "backup") -> LLMCallResult:
    return LLMCallResult(
        message=AIMessage(content="ok"),
        usage=LLMUsage(
            input_tokens=20,
            output_tokens=5,
            total_tokens=25,
            latency_ms=3.0,
            cost_usd=None,
            provider=provider,
            model=f"{provider}-model",
        ),
    )


def test_router_retries_429_with_bounded_exponential_backoff() -> None:
    provider = _FakeProvider("first", [_ProviderFailureError(429)])
    delays: list[float] = []
    router = ProviderRouter(
        [provider],
        max_retries=2,
        retry_base_seconds=0.5,
        retry_max_seconds=2.0,
        sleep=delays.append,
        random_value=lambda: 0.0,
    )

    with pytest.raises(ProviderUnavailableError) as exc_info:
        router.complete([])

    assert "ProviderRateLimitError" in str(exc_info.value)
    assert provider.calls == 3
    assert delays == [0.5, 1.0]
    with pytest.raises(ProviderUnavailableError,match="circuit open"):
        router.complete([])
    assert provider.calls == 3


def test_router_retries_timeout_then_falls_back() -> None:
    first=_FakeProvider("first",[TimeoutError("request timed out")])
    backup=_FakeProvider("backup",[_result()])
    router=ProviderRouter([first,backup],max_retries=1,sleep=lambda _:None)

    result=router.complete([])

    assert result.message.content=="ok"
    assert first.calls==2
    assert backup.calls==1


def test_router_falls_back_and_caches_the_working_provider() -> None:
    missing_model = _ProviderFailureError(404)
    first = _FakeProvider("first", [missing_model])
    backup = _FakeProvider("backup", [_result()])
    router = ProviderRouter([first, backup], max_retries=2, sleep=lambda _: None)

    assert router.complete([]).message.content == "ok"
    assert router.complete([]).message.content == "ok"
    assert first.calls == 1
    assert backup.calls == 2


def test_router_applies_configured_cost_when_provider_usage_omits_it() -> None:
    provider = _FakeProvider("backup", [_result()])
    router = ProviderRouter(
        [provider],
        pricing={"backup/backup-model": ModelPricing(input_per_million=1.0, output_per_million=2.0)},
    )

    result = router.complete([])

    assert result.usage.cost_usd == pytest.approx(0.00003)


def test_router_streams_provider_events() -> None:
    router = ProviderRouter([_FakeProvider("first", [_result()])])

    assert list(router.stream([])) == [LLMStreamEvent(kind="text", text="streamed")]


def test_completion_streams_chunks_through_event_callback() -> None:
    model=MagicMock()
    model.stream.return_value=[AIMessageChunk(content="Hello "),AIMessageChunk(content="world")]
    provider=LangChainProvider("fake","fake-model",model)
    router=ProviderRouter([provider])
    events: list[LLMStreamEvent]=[]

    result=router.complete([HumanMessage(content="greet")],on_event=events.append)

    assert result.message.content=="Hello world"
    assert [event.text for event in events]==["Hello ","world"]


def test_stream_aggregation_preserves_native_tool_calls() -> None:
    model=MagicMock()
    model.stream.return_value=[
        AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name":"add","args":'{"a":2,"b":3}',"id":"call-1","index":0}
            ],
        )
    ]
    model.bind_tools.return_value=model
    provider=LangChainProvider("fake","fake-model",model)
    events: list[LLMStreamEvent]=[]

    result=provider.complete([HumanMessage(content="add 2 and 3")],tools=[{"type":"function"}],on_event=events.append)

    assert result.message.tool_calls==[
        {"name":"add","args":{"a":2,"b":3},"id":"call-1","type":"tool_call"}
    ]
    assert events[0].kind=="tool_call"
