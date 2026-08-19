"""What a message of the stream looks like, for the tests."""
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from term_timer_clients.protocol import PROTOCOL_VERSION

REPLAYS = Path(__file__).parent / 'replays' / 'gan_gen2'

# Topic of every driver event a capture holds. Kept here rather than in
# the suite of one client: two copies of it would be two answers to
# what a capture means the day a topic is renamed
TOPICS = {
    'facelets': 'cube.facelets',
    'move': 'cube.move',
    'move_history': 'cube.history',
    'gyro': 'cube.gyro',
    'hardware': 'cube.hardware',
    'battery': 'cube.battery',
}


def envelope(
        topic: str,
        data: dict[str, Any] | None = None,
        session_id: str = 'a3f1c8d2',
        version: int = PROTOCOL_VERSION,
) -> dict[str, Any]:
    """
    Build an envelope as the publisher writes it.

    Args:
        topic: Topic of the message.
        data: Payload of the message.
        session_id: Identifier of the emitting session.
        version: Version of the protocol spoken.

    Returns:
        The envelope, ready to be dispatched.

    """
    return {
        'v': version,
        'seq': 0,
        'ts': 1755500000.0,
        'src': 'solve',
        'sid': session_id,
        'topic': topic,
        'data': data if data is not None else {},
    }


def capture(name: str) -> list[dict[str, Any]]:
    """
    Read a recorded stream of driver events.

    Args:
        name: Name of the capture file.

    Returns:
        The events, as the driver produced them.

    """
    events: list[dict[str, Any]] = json.loads(
        (REPLAYS / name).read_text(),
    )

    return events


def envelopes(name: str) -> Iterator[dict[str, Any]]:
    """
    Turn a capture into the messages the publisher would have written.

    The event names its own type, which the topic already says, so it
    is what is taken out of the payload.

    Args:
        name: Name of the capture file.

    Yields:
        The envelopes, in the order the driver produced them.

    """
    for event in capture(name):
        topic = TOPICS.get(event['event'])

        if topic is None:
            continue

        yield envelope(
            topic,
            {
                key: value
                for key, value in event.items()
                if key != 'event'
            },
        )
