"""Provider-neutral interfaces and bounded fallback routing for chat models."""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from langchain_core.messages import AIMessage, BaseMessage


@dataclass(frozen=True)
class ProviderCapabilities:
    native_tool_calling: bool = True
    streaming: bool = True
    token_counting: bool = False
    prompt_caching: bool = False


@dataclass(frozen=True)
class ModelPricing:
    input_per_million: float | None = None
    output_per_million: float | None = None


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float
    cost_usd: float | None
    provider: str
    model: str


@dataclass(frozen=True)
class LLMCallResult:
    message: AIMessage
    usage: LLMUsage


@dataclass(frozen=True)
class LLMStreamEvent:
    kind: str
    text: str = ""
    tool_call: dict[str, Any] | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Common completion, streaming, token-counting, and capability contract."""

    provider_name: str
    model_name: str
    capabilities: ProviderCapabilities

    def complete(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[dict[str, Any]] | None = None,
        on_event: Callable[[LLMStreamEvent], None] | None = None,
    ) -> LLMCallResult: ...

    def stream(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> Iterator[LLMStreamEvent]: ...

    def count_tokens(self, messages: Sequence[BaseMessage]) -> int: ...


class ProviderCallError(RuntimeError):
    """Base class for normalized provider failures."""


class ProviderTimeoutError(ProviderCallError):
    """A provider request exceeded its configured timeout."""


class ProviderRateLimitError(ProviderCallError):
    """A provider rejected a request because of a rate or quota limit."""


class ProviderServerError(ProviderCallError):
    """A provider returned a transient server-side failure."""


class ModelUnavailableError(ProviderCallError):
    """A configured model ID is unknown or unavailable at the provider."""


class ProviderAuthenticationError(ProviderCallError):
    """Provider credentials were missing, expired, or unauthorized."""


class ProviderUnavailableError(ProviderCallError):
    """All configured providers failed after bounded retries and fallback."""


def estimate_tokens(messages: Sequence[BaseMessage] | str) -> int:
    """Conservative dependency-free token estimate used when an SDK has no counter."""
    if isinstance(messages, str):
        content = messages
    else:
        parts: list[str] = []
        for message in messages:
            parts.append(str(message.content))
        content = "\n".join(parts)
    return max(1, (len(content) + 3) // 4)


def response_usage(message: AIMessage) -> tuple[int | None, int | None]:
    usage: Any = message.usage_metadata
    if not usage:
        usage = message.response_metadata.get("token_usage", {})
    if not isinstance(usage, dict):
        return None, None
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    if not isinstance(input_tokens,(int,str)) or not isinstance(output_tokens,(int,str)):
        return None,None
    try:
        return int(input_tokens),int(output_tokens)
    except ValueError:
        return None,None


class LangChainProvider:
    """Adapt a LangChain chat model to the provider-neutral interface."""

    def __init__(
        self,
        provider_name: str,
        model_name: str,
        model: Any,
        pricing: ModelPricing | None = None,
        capabilities: ProviderCapabilities | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        self.model = model
        self.pricing = pricing or ModelPricing()
        self.capabilities = capabilities or ProviderCapabilities()

    def _bind_tools(self, tools: Sequence[dict[str, Any]] | None) -> Any:
        if not tools or not self.capabilities.native_tool_calling:
            return self.model
        binder = getattr(self.model, "bind_tools", None)
        if not callable(binder):
            return self.model
        try:
            return binder(list(tools), parallel_tool_calls=False)
        except (NotImplementedError, TypeError):
            try:
                return binder(list(tools))
            except NotImplementedError:
                return self.model

    def complete(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[dict[str, Any]] | None = None,
        on_event: Callable[[LLMStreamEvent], None] | None = None,
    ) -> LLMCallResult:
        started = time.perf_counter()
        if on_event is None:
            response = self._bind_tools(tools).invoke(list(messages))
        else:
            response = self._stream_message(messages, tools, on_event)
        if not isinstance(response, AIMessage):
            response = AIMessage(content=str(getattr(response, "content", response)))

        input_tokens, output_tokens = response_usage(response)
        if input_tokens is None:
            input_tokens = self.count_tokens(messages)
            if tools:  # tool schemas are sent with every request and cost real tokens
                input_tokens += estimate_tokens(json.dumps(list(tools), default=str))
        if output_tokens is None:
            # A tool call has an empty text body but its arguments are still generated tokens.
            produced = str(response.content) + json.dumps(list(response.tool_calls or []), default=str)
            output_tokens = estimate_tokens(produced)
        latency_ms = (time.perf_counter() - started) * 1000.0
        cost = None
        if self.pricing.input_per_million is not None and self.pricing.output_per_million is not None:
            cost = (
                input_tokens * self.pricing.input_per_million
                + output_tokens * self.pricing.output_per_million
            ) / 1_000_000
        return LLMCallResult(
            message=response,
            usage=LLMUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                latency_ms=latency_ms,
                cost_usd=cost,
                provider=self.provider_name,
                model=self.model_name,
            ),
        )

    def _stream_message(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[dict[str, Any]] | None,
        on_event: Callable[[LLMStreamEvent], None],
    ) -> AIMessage:
        model = self._bind_tools(tools)
        aggregate: Any = None
        text_parts: list[str] = []
        streamed_tool_chunks: list[dict[str,Any]]=[]
        for chunk in model.stream(list(messages)):
            content = getattr(chunk, "content", "")
            if isinstance(content, str) and content:
                text_parts.append(content)
                on_event(LLMStreamEvent(kind="text", text=content))
            for call in getattr(chunk, "tool_call_chunks", None) or []:
                call_data=dict(call)
                streamed_tool_chunks.append(call_data)
                on_event(LLMStreamEvent(kind="tool_call", tool_call=call_data))
            aggregate = chunk if aggregate is None else aggregate + chunk
        result: AIMessage | None=None
        if aggregate is not None:
            to_message = getattr(aggregate, "to_message", None)
            if callable(to_message):
                converted = to_message()
                if isinstance(converted, AIMessage):
                    result=converted
        if result is None:
            result=AIMessage(content="".join(text_parts))
        if not result.tool_calls and streamed_tool_chunks:
            merged: dict[int,dict[str,Any]]={}
            for position,call in enumerate(streamed_tool_chunks):
                call_index=call.get("index")
                key=call_index if isinstance(call_index,int) else position
                current=merged.setdefault(key,{"name":"","args":"","id":None})
                if call.get("name"):
                    current["name"]+=str(call["name"])
                if call.get("args"):
                    current["args"]+=str(call["args"])
                if call.get("id"):
                    current["id"]=call["id"]
            tool_calls=[]
            for call in merged.values():
                try:
                    arguments=json.loads(call["args"] or "{}")
                except json.JSONDecodeError:
                    arguments={}
                if call["name"]:
                    tool_calls.append({"name":call["name"],"args":arguments,"id":call["id"]})
            if tool_calls:
                result=AIMessage(content=result.content,tool_calls=tool_calls)
        return result

    def stream(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> Iterator[LLMStreamEvent]:
        if not self.capabilities.streaming:
            raise ProviderCallError(f"Streaming is not supported by {self.provider_name}.")
        model = self._bind_tools(tools)
        for chunk in model.stream(list(messages)):
            content = getattr(chunk, "content", "")
            if isinstance(content, str) and content:
                yield LLMStreamEvent(kind="text", text=content)
            for call in getattr(chunk, "tool_call_chunks", None) or []:
                yield LLMStreamEvent(kind="tool_call", tool_call=dict(call))

    def count_tokens(self, messages: Sequence[BaseMessage]) -> int:
        counter = getattr(self.model, "get_num_tokens_from_messages", None)
        if callable(counter):
            try:
                return int(counter(list(messages)))
            except Exception:
                pass
        return estimate_tokens(messages)


@dataclass
class _Circuit:
    failures: int = 0
    open_until: float = 0.0

    def is_open(self, now: float) -> bool:
        return self.open_until > now

    def fail(self, now: float, cooldown_seconds: float) -> None:
        self.failures += 1
        self.open_until = now + cooldown_seconds

    def succeed(self) -> None:
        self.failures = 0
        self.open_until = 0.0


def _status_code(error: Exception) -> int | None:
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _is_retryable(error: Exception) -> bool:
    status = _status_code(error)
    if status is not None:
        return status == 429 or status >= 500
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True
    message = str(error).lower()
    return any(token in message for token in ("timeout", "temporarily unavailable", "connection reset"))


def _classify_error(error: Exception) -> ProviderCallError:
    status=_status_code(error)
    if status==429:
        return ProviderRateLimitError(str(error))
    if status is not None and status>=500:
        return ProviderServerError(str(error))
    if status==404:
        return ModelUnavailableError(str(error))
    if status in (401,403):
        return ProviderAuthenticationError(str(error))
    if isinstance(error,(TimeoutError,ConnectionError)) or "timeout" in str(error).lower():
        return ProviderTimeoutError(str(error))
    return ProviderCallError(str(error))


class ProviderRouter:
    """Retry and fail over across providers while caching the last working model."""

    def __init__(
        self,
        providers: Sequence[LLMProvider],
        *,
        max_retries: int = 2,
        retry_base_seconds: float = 0.25,
        retry_max_seconds: float = 4.0,
        circuit_cooldown_seconds: float = 30.0,
        pricing: dict[str, ModelPricing] | None = None,
        context_tokens: int = 32_000,
        max_tool_output_tokens: int = 2_000,
        max_completion_tokens: int = 2_048,
        sleep: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        if not providers:
            raise ValueError("ProviderRouter requires at least one configured provider.")
        self.providers = list(providers)
        self.max_retries = max(0, max_retries)
        self.retry_base_seconds = max(0.0, retry_base_seconds)
        self.retry_max_seconds = max(self.retry_base_seconds, retry_max_seconds)
        self.circuit_cooldown_seconds = max(0.0, circuit_cooldown_seconds)
        self.pricing = pricing or {}
        self.context_tokens = max(1, context_tokens)
        self.max_tool_output_tokens = max(256, max_tool_output_tokens)
        self.max_completion_tokens = max(1, max_completion_tokens)
        self._sleep = sleep
        self._random_value = random_value
        self._active_index = 0
        self._circuits = [_Circuit() for _ in self.providers]

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self.providers[self._active_index].capabilities

    @property
    def provider_name(self) -> str:
        return self.providers[self._active_index].provider_name

    @property
    def model_name(self) -> str:
        return self.providers[self._active_index].model_name

    def count_tokens(self, messages: Sequence[BaseMessage]) -> int:
        return self.providers[self._active_index].count_tokens(messages)

    def _provider_order(self) -> list[int]:
        return [self._active_index] + [i for i in range(len(self.providers)) if i != self._active_index]

    def _delay(self, retry_index: int) -> float:
        exponential = min(self.retry_base_seconds * (2**retry_index), self.retry_max_seconds)
        return exponential + (self._random_value() * exponential)

    def complete(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[dict[str, Any]] | None = None,
        on_event: Callable[[LLMStreamEvent], None] | None = None,
    ) -> LLMCallResult:
        errors: list[str] = []
        for index in self._provider_order():
            provider = self.providers[index]
            circuit = self._circuits[index]
            if circuit.is_open(time.monotonic()):
                errors.append(f"{provider.provider_name}/{provider.model_name}: circuit open")
                continue

            for attempt in range(self.max_retries + 1):
                try:
                    if on_event is not None and isinstance(provider, LangChainProvider):
                        result = provider.complete(messages, tools=tools, on_event=on_event)
                    else:
                        result = provider.complete(messages, tools=tools)
                except Exception as exc:
                    retryable = _is_retryable(exc)
                    classified=_classify_error(exc)
                    errors.append(
                        f"{provider.provider_name}/{provider.model_name}: "
                        f"{type(classified).__name__}: {classified}"
                    )
                    if retryable and attempt < self.max_retries:
                        self._sleep(self._delay(attempt))
                        continue
                    circuit.fail(time.monotonic(), self.circuit_cooldown_seconds)
                    break

                circuit.succeed()
                self._active_index = index
                usage = result.usage
                price = self.pricing.get(f"{provider.provider_name}/{provider.model_name}")
                cost = usage.cost_usd
                if cost is None and price is not None:
                    cost = (
                        usage.input_tokens * (price.input_per_million or 0.0)
                        + usage.output_tokens * (price.output_per_million or 0.0)
                    ) / 1_000_000
                return LLMCallResult(
                    message=result.message,
                    usage=LLMUsage(
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        total_tokens=usage.total_tokens,
                        latency_ms=usage.latency_ms,
                        cost_usd=cost,
                        provider=usage.provider,
                        model=usage.model,
                    ),
                )

        summary = "; ".join(errors) or "No provider was available."
        raise ProviderUnavailableError(f"All configured LLM providers failed: {summary}")

    def invoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        """Compatibility adapter used by existing agent callers."""
        return self.complete(messages).message

    def bind_tools(self, tools: Sequence[dict[str, Any]], **_: Any) -> BoundProviderRouter:
        return BoundProviderRouter(self, tools)

    def stream(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> Iterator[LLMStreamEvent]:
        errors: list[str] = []
        for index in self._provider_order():
            provider = self.providers[index]
            if self._circuits[index].is_open(time.monotonic()):
                continue
            try:
                yield from provider.stream(messages, tools=tools)
            except Exception as exc:
                errors.append(f"{provider.provider_name}/{provider.model_name}: {exc}")
                self._circuits[index].fail(time.monotonic(), self.circuit_cooldown_seconds)
                continue
            self._circuits[index].succeed()
            self._active_index = index
            return
        raise ProviderUnavailableError("Streaming failed for all configured providers: " + "; ".join(errors))


class BoundProviderRouter:
    """Small LangChain-compatible adapter for legacy `.bind_tools(...).invoke()` code."""

    def __init__(self, router: ProviderRouter, tools: Sequence[dict[str, Any]]) -> None:
        self.router = router
        self.tools = list(tools)

    def invoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        return self.router.complete(messages, tools=self.tools).message
