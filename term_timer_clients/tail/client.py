"""The whole of ``tt-tail``, which reads and never interprets."""
import logging
from collections.abc import Callable
from typing import Any
from typing import Final

from term_timer_clients.protocol import PROTOCOL_VERSION
from term_timer_clients.protocol import SESSION_END_TOPIC
from term_timer_clients.protocol import Envelope
from term_timer_clients.tail.render import Renderer

logger = logging.getLogger(__name__)

Writer = Callable[[str], None]
Recorder = Callable[[Envelope], None]

# The gyroscope publishes tens of times a second, and a block each time
# is a window where nothing else can be seen. It is the one topic held
# back, and --all is what gives it up: everything else, known or not,
# goes through
QUIET_TOPICS: Final = frozenset({'cube.gyro'})

# What a gap of nothing looks like: no message came before, so there is
# no time between them to show
NO_GAP: Final = -1.0


class StreamTail:
    """
    A reader of the stream, and nothing more than a reader.

    No cube is rebuilt here, no state is derived, and nothing of
    cubing-algs is imported: what arrives is what is shown. The only
    state kept is what the gaps and the losses are counted from, which
    belongs to the reading rather than to the cube.

    Every topic is printed, the unknown ones included. Ignoring what it
    does not know is what a client owes the protocol, but a tail that
    hid a topic added tomorrow would be blind on the very message its
    reader opened it for.

    Reading and recording are two gestures and they are kept apart: the
    writer is handed what a reader is to see, the recorder is handed
    every envelope that arrived.
    """

    def __init__(
            self,
            renderer: Renderer,
            writer: Writer,
            recorder: Recorder | None = None,
            *,
            everything: bool = False,
    ) -> None:
        """
        Prepare a reader over a renderer and a place to write.

        Args:
            renderer: What turns an envelope into lines.
            writer: What the lines are handed to.
            recorder: What every envelope is handed to, none when
                nothing is being kept.
            everything: Whether the topics held back are shown too.

        """
        self.renderer = renderer
        self.writer = writer
        self.recorder = recorder
        self.everything = everything

        self.session_id = ''
        self.sequence = -1
        self.stamp = NO_GAP
        self.stamps: dict[str, float] = {}

        # Only ever reported once: a stream of another version says so
        # in every one of its messages. It holds whatever an envelope
        # wrote there, which is not always a version
        self.version_seen: Any = PROTOCOL_VERSION

    def write(self, *lines: str) -> None:
        """
        Hand a block over in one piece.

        Args:
            lines: What the block is made of.

        """
        self.writer('\n'.join(lines))

    def shown(self, topic: str) -> bool:
        """
        Say whether a topic is printed at all.

        Args:
            topic: The topic of the message.

        Returns:
            True when the message is one to show.

        """
        return self.everything or topic not in QUIET_TOPICS

    def restart(self, envelope: Envelope) -> None:
        """
        Follow a session, and forget what the one before was counted by.

        Args:
            envelope: The first message of the session.

        """
        self.session_id = str(envelope.get('sid', ''))
        self.sequence = -1
        self.stamp = NO_GAP
        self.stamps = {}

        self.write(self.renderer.session(envelope))

    def track(self, envelope: Envelope) -> None:
        """
        Report what was published between two messages read.

        The two prefixes cover everything the publisher emits, so a
        break in the sequence is a loss rather than a subscription
        looking away.

        Args:
            envelope: The message just read.

        """
        sequence = envelope.get('seq')

        if not isinstance(sequence, int):
            return

        missed = sequence - self.sequence - 1

        if self.sequence >= 0 and missed > 0:
            self.write(self.renderer.loss(missed))

        self.sequence = sequence

    def gaps(self, topic: str, stamp: float) -> tuple[float, float]:
        """
        Measure the time since the messages this one follows.

        Both are counted on what was printed rather than on what
        arrived: a gap counting gyroscope messages nobody sees would
        say nothing about the cadence the blocks are read at.

        Args:
            topic: The topic of the message.
            stamp: When it was published, in epoch seconds.

        Returns:
            The seconds since the block before, and the seconds since
            the block before of the same topic.

        """
        gap = stamp - self.stamp if self.stamp >= 0 else NO_GAP

        previous = self.stamps.get(topic)
        topic_gap = stamp - previous if previous is not None else NO_GAP

        self.stamp = stamp
        self.stamps[topic] = stamp

        return gap, topic_gap

    def dispatch(self, envelope: Envelope) -> None:
        """
        Read one message of the stream out loud.

        Args:
            envelope: The message, as the publisher wrote it.

        """
        # Kept before it is read at all: what a capture is worth is
        # being what passed on the wire rather than what this client
        # could make of it. A version it cannot speak, a topic it does
        # not know and a gyroscope nobody is shown are exactly what a
        # recording is opened for
        if self.recorder is not None:
            self.recorder(envelope)

        version = envelope.get('v')

        if version != PROTOCOL_VERSION:
            if version != self.version_seen:
                self.version_seen = version
                logger.warning(
                    'Ignoring a stream speaking version %s, '
                    'this client speaks version %s',
                    version, PROTOCOL_VERSION,
                )
            return

        session_id = str(envelope.get('sid', ''))

        if session_id != self.session_id:
            self.restart(envelope)

        # Counted before the filtering: a message held back was
        # published all the same, and a loss it hid would be a loss
        # blamed on the topic that comes next
        self.track(envelope)

        topic = str(envelope.get('topic', ''))

        if not self.shown(topic):
            return

        stamp = envelope.get('ts')
        gap, topic_gap = (
            self.gaps(topic, float(stamp))
            if isinstance(stamp, int | float)
            else (NO_GAP, NO_GAP)
        )

        self.write(*self.renderer.block(envelope, gap, topic_gap))

        if topic == SESSION_END_TOPIC:
            self.end_session(envelope)

    def end_session(self, envelope: Envelope) -> None:
        """
        Close the session, and go on reading the stream.

        Nothing of this session follows its farewell, but the reader is
        not done: a publisher binds the endpoint a subscriber is
        already connected to, so a tail that ended with the session
        would have to be started again for the next one - and what
        comes back is told apart by the identifier of its envelopes,
        which is what announces it in turn.

        Args:
            envelope: The ``session.end`` message, already printed.

        """
        self.write(self.renderer.farewell(envelope))
