"""What a message of the stream looks like, for the tests."""
from typing import Any

from term_timer_clients.protocol import PROTOCOL_VERSION


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
