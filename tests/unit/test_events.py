"""
Test Suite: Kernel EventBus Pub/Sub
====================================
Tests proving:
  1. Synchronous and asynchronous event dispatch.
  2. Targeted event type filtering and wildcard subscription.
  3. Exception isolation between independent subscribers.
  4. Event history tracking and replay buffers.
"""

import pytest

from aegis_os.kernel.events import (
    EventBus,
    KernelEvent,
    MissionStatusChangedEvent,
    StateTransitionEvent,
)
from aegis_os.kernel.state import AgentRole, MissionStatus


class TestEventBus:
    """EventBus pub/sub dispatch and safety tests."""

    def test_sync_event_subscription(self) -> None:
        bus = EventBus()
        received = []

        def handler(evt: KernelEvent) -> None:
            received.append(evt)

        bus.subscribe(MissionStatusChangedEvent, handler)

        event = MissionStatusChangedEvent(
            old_status=MissionStatus.PENDING,
            new_status=MissionStatus.RUNNING,
            goal="Test event bus",
        )
        bus.publish(event)

        assert len(received) == 1
        assert received[0] == event

    def test_wildcard_subscription_receives_all_events(self) -> None:
        bus = EventBus()
        all_events = []

        bus.subscribe("*", lambda evt: all_events.append(evt))

        evt1 = MissionStatusChangedEvent(
            old_status=MissionStatus.PENDING,
            new_status=MissionStatus.RUNNING,
            goal="Goal",
        )
        evt2 = StateTransitionEvent(
            from_role=None,
            to_role=AgentRole.CTO,
            step_index=1,
        )

        bus.publish(evt1)
        bus.publish(evt2)

        assert len(all_events) == 2

    def test_unsubscribe(self) -> None:
        bus = EventBus()
        received = []

        def handler(evt: KernelEvent) -> None:
            received.append(evt)

        bus.subscribe(MissionStatusChangedEvent, handler)
        bus.unsubscribe(MissionStatusChangedEvent, handler)

        bus.publish(
            MissionStatusChangedEvent(
                old_status=MissionStatus.PENDING,
                new_status=MissionStatus.RUNNING,
                goal="Goal",
            )
        )
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_async_event_subscription(self) -> None:
        bus = EventBus()
        received = []

        async def async_handler(evt: KernelEvent) -> None:
            received.append(evt)

        bus.subscribe(StateTransitionEvent, async_handler)

        event = StateTransitionEvent(
            from_role=AgentRole.CTO,
            to_role=AgentRole.DEV,
            step_index=2,
        )
        await bus.publish_async(event)

        assert len(received) == 1
        assert received[0] == event

    def test_exception_isolation_between_subscribers(self) -> None:
        bus = EventBus()
        successful_received = []

        def broken_handler(evt: KernelEvent) -> None:
            raise RuntimeError("Subscriber explosion!")

        def healthy_handler(evt: KernelEvent) -> None:
            successful_received.append(evt)

        bus.subscribe(MissionStatusChangedEvent, broken_handler)
        bus.subscribe(MissionStatusChangedEvent, healthy_handler)

        event = MissionStatusChangedEvent(
            old_status=MissionStatus.PENDING,
            new_status=MissionStatus.RUNNING,
            goal="Goal",
        )

        # Publishing must not raise despite broken_handler failure
        bus.publish(event)

        assert len(successful_received) == 1

    def test_history_buffer(self) -> None:
        bus = EventBus()
        for i in range(5):
            bus.publish(
                StateTransitionEvent(
                    from_role=None,
                    to_role=AgentRole.DEV,
                    step_index=i + 1,
                )
            )

        history = bus.get_history()
        assert len(history) == 5
        # Most recent first
        assert history[0].step_index == 5
        assert history[-1].step_index == 1
