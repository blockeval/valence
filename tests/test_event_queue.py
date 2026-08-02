from valence.engine import EventQueue, EventType


def test_event_queue_uses_sequence_for_equal_times():
    queue = EventQueue()
    queue.push(10, EventType.SLOT_START, "first")
    queue.push(10, EventType.ATTESTATION_TIME, "second")
    queue.push(5, EventType.MESSAGE_ARRIVAL, "earlier")
    assert [queue.pop().payload, queue.pop().payload, queue.pop().payload] == [
        "earlier",
        "first",
        "second",
    ]
