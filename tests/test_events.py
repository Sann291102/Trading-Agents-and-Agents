import asyncio

import pytest

from aio.events.bus import EventBus, OrgEvent


def _event(**overrides) -> OrgEvent:
    defaults = dict(type="agent_started", message="test event")
    defaults.update(overrides)
    return OrgEvent(**defaults)


def test_publish_reaches_subscriber_queue_without_bound_loop():
    bus = EventBus()
    queue = bus.subscribe()

    bus.publish(_event(agent_role="Domain Expert"))

    received = queue.get_nowait()
    assert received.agent_role == "Domain Expert"
    assert received.type == "agent_started"


def test_publish_reaches_subscriber_queue_with_bound_loop():
    async def scenario():
        bus = EventBus()
        bus.bind_loop(asyncio.get_running_loop())
        queue = bus.subscribe()

        bus.publish(_event(message="hello"))

        received = await asyncio.wait_for(queue.get(), timeout=1)
        assert received.message == "hello"

    asyncio.run(scenario())


def test_unsubscribe_stops_further_delivery():
    bus = EventBus()
    queue = bus.subscribe()
    bus.unsubscribe(queue)

    bus.publish(_event())

    assert queue.empty()


def test_recent_returns_bounded_history_in_order():
    bus = EventBus(history_limit=3)
    for i in range(5):
        bus.publish(_event(message=f"event-{i}"))

    recent = bus.recent(10)

    assert [e.message for e in recent] == ["event-2", "event-3", "event-4"]


def test_recent_limit_caps_returned_count():
    bus = EventBus()
    for i in range(5):
        bus.publish(_event(message=f"event-{i}"))

    assert [e.message for e in bus.recent(2)] == ["event-3", "event-4"]


def test_multiple_subscribers_all_receive_the_same_event():
    bus = EventBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()

    bus.publish(_event(message="broadcast"))

    assert q1.get_nowait().message == "broadcast"
    assert q2.get_nowait().message == "broadcast"


def test_listener_is_invoked_synchronously_on_publish():
    bus = EventBus()
    seen = []
    bus.add_listener(seen.append)

    bus.publish(_event(message="listener test"))

    assert len(seen) == 1
    assert seen[0].message == "listener test"


def test_full_queue_drops_oldest_rather_than_raising():
    bus = EventBus()
    queue: asyncio.Queue = asyncio.Queue(maxsize=2)
    with bus._lock:
        bus._subscribers.add(queue)

    bus.publish(_event(message="first"))
    bus.publish(_event(message="second"))
    bus.publish(_event(message="third"))

    remaining = []
    while not queue.empty():
        remaining.append(queue.get_nowait().message)
    assert remaining == ["second", "third"]


def test_org_event_type_rejects_unknown_value():
    with pytest.raises(Exception):
        OrgEvent(type="not_a_real_event_type", message="bad")
