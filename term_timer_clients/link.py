"""What the stream says of the cube, before anything shows it."""
import logging
from typing import TYPE_CHECKING
from typing import Any

from term_timer_clients.protocol import CUBE_PREFIX
from term_timer_clients.protocol import PROTOCOL_VERSION
from term_timer_clients.protocol import SESSION_END_TOPIC

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# What a cube says about itself, and what term-timer says about the
# cube. The first two are the cube introducing itself over a link that
# is up; the third is the only topic of the plane that is not the cube
# talking at all, and says so even - and above all - when the cube has
# fallen silent for good.
HARDWARE_TOPIC = 'cube.hardware'

BATTERY_TOPIC = 'cube.battery'

LINK_TOPIC = 'cube.link'


class CubeLink:
    """
    Whether there is a cube behind the stream, and what it calls itself.

    Every client showing a cube answers the same three questions before
    it shows anything: whether the stream is one it can read at all,
    whether it is still the same session talking, and whether there is
    a cube on the other end. The answers are the same for a window and
    for an icon in a bar, and they are here rather than in either
    because two copies of them would be two answers the day a topic is
    renamed - the very reason the captures of the suite are read in one
    place.

    **A cube announces its departure and never its arrival.**
    ``cube.link`` is published by term-timer rather than by a driver,
    and a client opened in the middle of a session has heard neither
    it nor the connection it announced. So the cube talking at all is
    what says it is there, and ``cube.link`` is the only topic that
    ever says it is gone - with ``session.end``, which says it of the
    publisher rather than of the cube and comes to the same thing: a
    cube nobody publishes any more is a cube nobody is connected to.

    Nothing is ever waited for, and a cube can also **go missing**: a
    process killed outright publishes no farewell at all, so silence is
    read as nothing whatever. It is what spares a client the wait
    rather than what a client is built on.

    Written to be subclassed: ``handlers`` is the dict a consumer adds
    its own topics to, and ``restart()`` and ``unlink()`` are what it
    extends to throw away what it holds of a cube that is gone.
    """

    def __init__(self) -> None:
        """Start on a stream that has said nothing yet."""
        self.session_id = ''
        self.source = ''
        self.hardware = ''
        self.battery = ''
        self.connected = False

        # Starts on the version this client speaks, so that a foreign
        # stream is reported once and not on every message it sends
        self.version_seen: Any = PROTOCOL_VERSION

        self.handlers: dict[str, Callable[[dict[str, Any]], None]] = {
            HARDWARE_TOPIC: self.name_cube,
            BATTERY_TOPIC: self.charge_cube,
            LINK_TOPIC: self.link_cube,
            SESSION_END_TOPIC: self.end_session,
        }

    @property
    def parts(self) -> list[str]:
        """
        Tell what the cube has said of itself, in the order it said it.

        What is made of them belongs to whoever shows them: a window
        writes them in its bar and an icon in its tooltip, and neither
        spelling is the business of the stream.

        Returns:
            The name and the charge of the cube, and only those it gave.

        """
        return [
            part
            for part in (self.hardware, self.battery)
            if part
        ]

    def dispatch(self, message: dict[str, Any]) -> None:
        """
        Act on one envelope of the stream.

        The envelope is read before its payload: a session identifier
        that changes means term-timer restarted, and everything told
        before belongs to a cube that is no longer the one talking.

        Args:
            message: The envelope, as the publisher wrote it.

        """
        version = message.get('v')
        if version != PROTOCOL_VERSION:
            if version != self.version_seen:
                logger.warning(
                    'Ignoring a stream speaking protocol %s, '
                    'this client speaks %s',
                    version, PROTOCOL_VERSION,
                )
                self.version_seen = version
            return

        session_id = str(message.get('sid', ''))
        if session_id != self.session_id:
            self.restart(session_id)

        self.source = str(message.get('src', ''))

        topic = str(message.get('topic', ''))

        # A cube announces its departure and never its arrival, and a
        # client opened in the middle of a session has heard neither:
        # the cube talking at all is what says it is there, and the
        # link topic is the only one that ever says it is gone.
        if topic.startswith(CUBE_PREFIX) and topic != LINK_TOPIC:
            self.connected = True

        handler = self.handlers.get(topic)
        if handler is None:
            return

        data = message.get('data')
        handler(data if isinstance(data, dict) else {})

    def restart(self, session_id: str) -> None:
        """
        Forget the session that was being followed, and follow a new one.

        A publisher that restarted starts over from a cube nobody has
        described yet: what was heard before belongs to a session that
        is over, and a cube coming back may not even be the one that
        left.

        Args:
            session_id: Identifier of the session now talking.

        """
        if self.session_id:
            logger.info('Following a new session, starting over')

        self.session_id = session_id
        self.unlink()

    def name_cube(self, data: dict[str, Any]) -> None:
        """
        Remember how the cube calls itself.

        Args:
            data: Payload of a ``cube.hardware`` message.

        """
        name = data.get('hardware_name')

        if isinstance(name, str) and name:
            self.hardware = name

    def charge_cube(self, data: dict[str, Any]) -> None:
        """
        Remember what the battery of the cube is at.

        Args:
            data: Payload of a ``cube.battery`` message.

        """
        level = data.get('level')

        if isinstance(level, int):
            self.battery = f'{ level }%'

    def link_cube(self, data: dict[str, Any]) -> None:
        """
        Follow the link with the cube, whatever it becomes.

        Args:
            data: Payload of a ``cube.link`` message.

        """
        if data.get('connected', True):
            self.connected = True
            return

        self.unlink()

    def end_session(self, data: dict[str, Any]) -> None:
        """
        Let the cube go when the publisher says its last word.

        Nothing of the session follows this message, so the cube it was
        describing is gone whatever ended it: a stream that is over
        publishes no state and no move, and a cube nobody publishes any
        more is a cube nobody is connected to. What ended it is only
        ever logged - a session closed, interrupted or carried away by
        an error leaves the very same silence behind.

        Args:
            data: Payload of a ``session.end`` message.

        """
        reason = data.get('reason')

        logger.info('End of the session: %s', reason or 'no reason given')

        self.unlink()

    def unlink(self) -> None:
        """
        Let the cube go, and what it said of itself with it.

        What a cube said of its name and its charge belongs to the
        connection it said it over: it is what a cube called itself
        over a link that is no longer up, and the cube coming back may
        not even be the one that left.
        """
        self.connected = False
        self.hardware = ''
        self.battery = ''
