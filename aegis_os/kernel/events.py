import asyncio
from datetime import datetime,timezone
import inspect
from typing import Any,Callable,Coroutine,Optional,Union
import uuid
from pydantic import BaseModel,ConfigDict,Field
from aegis_os.kernel.state import AgentRole,MissionStatus,StepRecord,StepStatus

class KernelEvent(BaseModel):
    """Base model for all kernel and telemetry events."""
    model_config=ConfigDict(extra="ignore")

    event_id: str=Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str=Field(description="Dotted event identifier,e.g.'mission.status_changed'")
    timestamp: datetime =Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: Optional[str]=None

class MissionStatusChangedEvent(KernelEvent):
    """Fired when overall mission status changes (e.g. PENDING -> RUNNING)."""
    event_type: str = "mission.status_changed"
    old_status: MissionStatus
    new_status: MissionStatus
    goal: str

class StateTransitionEvent(KernelEvent):
    """Fired when control shifts between agent roles or nodes."""
    event_type: str = "state.transition"
    from_role: Optional[AgentRole]
    to_role: AgentRole
    step_index: int

class StepStartedEvent(KernelEvent):
    """Fired when an agent begins execution of a new step."""
    event_type: str = "step.started"
    step: StepRecord

class StepCompletedEvent(KernelEvent):
    """Fired when an agent step concludes (success or failure)."""
    event_type: str = "step.completed"
    step: StepRecord

class ApprovalRequestedEvent(KernelEvent):
    """Fired when a high-risk action requires human authorization."""
    event_type: str = "approval.requested"
    step_id: str
    action_type: str
    command_or_file: str
    justification: str

# Type alias for event handlers (can be sync function or async coroutine)
EventHandler=Union[
    Callable[[KernelEvent],None],
    Callable[[KernelEvent],Coroutine[Any,Any,None]]
]

def _resolve_event_key(event_type: Union[type[KernelEvent], str]) -> str:
    """Extract string key from an event type class or string name."""
    if isinstance(event_type, str):
        return event_type
    if isinstance(event_type,type) and issubclass(event_type, BaseModel):
        field_info=event_type.model_fields.get("event_type")
        if field_info and field_info.default is not None:
            return str(field_info.default)
        return event_type.__name__
    return getattr(event_type,"event_type",getattr(event_type,"__name__",str(event_type)))


class EventBus:
    """
    Central event dispatcher for AegisOS.
    Supports synchronous and asynchronous subscribers with full exception isolation.
    """
    def __init__(self) -> None:
        self._subscribers: dict[str,list[EventHandler]] = {}
        self._history: list[KernelEvent] = []
        self._max_history: int = 1000

    def subscribe(self,event_type: Union[type[KernelEvent],str],handler: EventHandler) -> None:
        """Register a handler for a given event type or '*' for all events."""
        key=_resolve_event_key(event_type)
        if key not in self._subscribers:
            self._subscribers[key]=[]
        if handler not in self._subscribers[key]:
            self._subscribers[key].append(handler)

    def unsubscribe(self,event_type: Union[type[KernelEvent],str],handler: EventHandler) -> None:
        """Remove a previously registered handler."""
        key=_resolve_event_key(event_type)
        if key in self._subscribers and handler in self._subscribers[key]:
            self._subscribers[key].remove(handler)

    def clear(self) -> None:
        """Clear all subscribers and history."""
        self._subscribers.clear()
        self._history.clear()

    def get_history(self,limit: Optional[int] = None) -> list[KernelEvent]:
        """Return recorded event history, newest first."""
        history=list(reversed(self._history))
        return history[:limit] if limit else history

    def publish(self,event: KernelEvent) -> None:
        """
        Synchronously publish an event to all matching subscribers.
        Async coroutines are scheduled onto the active event loop if one is running.
        """
        self._record_event(event)
        handlers=self._get_handlers(event)

        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    try:
                        loop=asyncio.get_running_loop()
                        loop.create_task(handler(event))
                    except RuntimeError:
                        # No running event loop in current thread
                        asyncio.run(handler(event))
                else:
                    handler(event)
            except Exception as exc:  # noqa: BLE001
                # Exception isolation: one subscriber error must not crash the publisher
                print(f"[EventBus Error] Handler {handler} failed for {event.event_type}: {exc}")

    async def publish_async(self,event: KernelEvent) -> None:
        """Asynchronously publish an event, awaiting coroutine handlers directly."""
        self._record_event(event)
        handlers=self._get_handlers(event)

        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as exc:  # noqa: BLE001
                print(f"[EventBus Async Error] Handler {handler} failed for {event.event_type}: {exc}")

    def _record_event(self,event: KernelEvent) -> None:
        self._history.append(event)
        if len(self._history)>self._max_history:
            self._history.pop(0)

    def _get_handlers(self,event: KernelEvent) -> list[EventHandler]:
        specific_str=self._subscribers.get(event.event_type,[])
        specific_cls=self._subscribers.get(event.__class__.__name__,[])
        catchall=self._subscribers.get("*",[])

        # Deduplicate while preserving insertion order
        seen: set[EventHandler]=set()
        handlers: list[EventHandler]=[]
        for h in specific_str+specific_cls+catchall:
            if h not in seen:
                seen.add(h)
                handlers.append(h)
        return handlers