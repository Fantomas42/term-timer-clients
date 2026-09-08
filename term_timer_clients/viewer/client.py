"""Translation of the event stream into what the viewer shows."""
import logging
import time
from typing import TYPE_CHECKING
from typing import Any

from cubing_algs.constants import ORIENTATION_FACE_MOVES
from cubing_algs.display.gl import MoveClock
from cubing_algs.display.gl import OrientationTracker
from cubing_algs.display.gl import Viewer
from cubing_algs.exceptions import CubingAlgsError
from cubing_algs.parsing import parse_moves
from cubing_algs.transform.translate import translate_moves
from cubing_algs.vcube import VCube

from term_timer_clients.protocol import CUBE_PREFIX
from term_timer_clients.protocol import PROTOCOL_VERSION
from term_timer_clients.protocol import SESSION_END_TOPIC

if TYPE_CHECKING:
    from collections.abc import Callable

    from cubing_algs.algorithm import Algorithm

logger = logging.getLogger(__name__)

# Title of a window that has heard nothing yet, and the pieces the rest
# of it is assembled from as the cube introduces itself
WINDOW_TITLE = 'Cubecast'
WINDOW_SEPARATOR = ' · '
WINDOW_OFFLINE = 'offline'

# The one topic of the cube plane that is not the cube talking: it is
# published by term-timer about the cube, and says so even - and above
# all - when the cube says nothing at all any more.
LINK_TOPIC = 'cube.link'


class CubeCast:
    """
    What the event stream does to the viewer, topic by topic.

    The whole client is here, and none of it touches a socket or a
    window: an envelope comes in, and a cube is reposed, a move is
    queued or a quaternion is fed to the tracker. A move is pushed the
    very moment it is heard and never held back for the next frame, and
    it is pushed with the **age** it has already reached: a face is
    over by the time the window hears of it, so the turn is started
    where it would already stand rather than from zero. ``MoveClock``
    is what reads that age.

    The envelope is read before its payload: a session identifier that
    changes means term-timer restarted, and everything told before
    belongs to a cube that is no longer the one talking.
    """

    def __init__(
            self,
            viewer: Viewer,
            tracker: OrientationTracker | None = None,
            orientation: str = '',
            clock: MoveClock | None = None,
    ) -> None:
        """
        Bind a viewer to the stream that will feed it.

        Args:
            viewer: The viewer to drive.
            tracker: The tracker the gyroscope feeds, when the viewer is
                oriented by the cube itself.
            orientation: The two faces the cube is shown by, empty for
                the frame the hardware reports in.
            clock: What tells how old an arriving move already is. A
                plain one when nothing says otherwise, the command line
                being what argues with its lead.

        """
        self.viewer = viewer
        self.tracker = tracker
        self.orientation = orientation
        self.clock = clock if clock is not None else MoveClock()

        # The rotations that bring the cube to the faces it is shown
        # by, and nothing at all when it is shown as it is held
        self.orientation_moves: Algorithm = parse_moves(
            ORIENTATION_FACE_MOVES[orientation] if orientation else '',
        )
        self.translator = translate_moves(self.orientation_moves)

        self.session_id = ''
        self.hardware = ''
        self.battery = ''
        self.connected = False
        self.described = False
        # Starts on the version this viewer speaks, so that a foreign
        # stream is reported once and not on every message it sends
        self.version_seen: Any = PROTOCOL_VERSION

        self.handlers: dict[str, Callable[[dict[str, Any]], None]] = {
            'cube.facelets': self.show_facelets,
            'cube.move': self.play_move,
            'cube.history': self.play_move,
            'cube.gyro': self.turn_cube,
            'cube.hardware': self.name_cube,
            'cube.battery': self.charge_cube,
            LINK_TOPIC: self.link_cube,
            SESSION_END_TOPIC: self.end_session,
        }

    @property
    def present(self) -> bool:
        """
        Tell whether there is a cube to show, and what it looks like.

        Two conditions, and they are two because they answer two
        events: the link says there is a cube, the state says what it
        looks like, and the pieces are only ever drawn when both hold.
        Gathering on the link alone would pick a solved cube up and
        repaint it in mid air a moment later; gathering on a state
        alone would leave the colors of a cube nobody is connected to
        any more hanging in the window.

        The two arrive milliseconds apart when a cube really connects,
        so nothing is waited for that is not already on its way, and a
        session joined in the middle is read the same way as any other:
        moves playing on a cube that never said what it looks like are
        not a cube.

        Returns:
            True when a cube is there and worth drawing.

        """
        return self.connected and self.described

    @property
    def title(self) -> str:
        """
        Tell what the window is called, as the cube introduces itself.

        Returns:
            The title of the window, the plain name until a cube says
            anything about itself.

        """
        parts = [
            part
            for part in (self.hardware, self.battery)
            if part
        ]

        if not self.connected:
            parts.append(WINDOW_OFFLINE)

        return WINDOW_SEPARATOR.join([WINDOW_TITLE, *parts])

    def restart(self, session_id: str) -> None:
        """
        Forget the session that was being watched, and follow a new one.

        A publisher that restarted starts over from a cube nobody
        described yet, so the viewer goes back to a solved one and the
        tracker to no reference at all: keeping the old one would show
        the new cube turned by the drift of the last session.

        Args:
            session_id: Identifier of the session now talking.

        """
        if self.session_id:
            logger.info('Following a new session, starting over')

        self.session_id = session_id
        self.hardware = ''
        self.battery = ''
        self.connected = False
        self.described = False
        self.clock.reset()

        if self.tracker is not None:
            self.tracker.reset()

        self.viewer.cube = self.rebuild(VCube(size=self.viewer.cube.size))

    def rebuild(self, cube: VCube) -> VCube:
        """
        Turn a cube into the way it is looked at.

        Args:
            cube: The cube as the hardware reports it.

        Returns:
            The cube seen from the configured faces.

        """
        if not self.orientation:
            return cube

        return cube.oriented_copy(self.orientation, full=True)

    def dispatch(self, message: dict[str, Any]) -> None:
        """
        Act on one envelope of the stream.

        Args:
            message: The envelope, as the publisher wrote it.

        """
        version = message.get('v')
        if version != PROTOCOL_VERSION:
            if version != self.version_seen:
                logger.warning(
                    'Ignoring a stream speaking protocol %s, '
                    'this viewer speaks %s',
                    version, PROTOCOL_VERSION,
                )
                self.version_seen = version
            return

        session_id = str(message.get('sid', ''))
        if session_id != self.session_id:
            self.restart(session_id)

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

    def show_facelets(self, data: dict[str, Any]) -> None:
        """
        Repose the cube on the state the hardware just described.

        Assigning the cube is all it takes: the viewer notices at the
        next frame that it no longer holds the one its animation plays
        on, and reloads by itself.

        Args:
            data: Payload of a ``cube.facelets`` message.

        """
        facelets = data.get('facelets')
        if not isinstance(facelets, str):
            return

        try:
            # Read on the size of the window, which is built once and
            # never changes: a state of another size is one this window
            # cannot show, and it says so rather than guessing
            cube = VCube(facelets, size=self.viewer.cube.size)
        except CubingAlgsError as error:
            logger.debug('Cannot read a cube state: %s', error)
            return

        self.viewer.cube = self.rebuild(cube)
        self.described = True

    def play_move(self, data: dict[str, Any]) -> None:
        """
        Queue the move the cube just reported, as old as it truly is.

        **A move is over by the time it is heard of.** The cube reports
        a face once it has stopped turning, the report crosses a
        bluetooth link and a stream, and the hand is somewhere else
        entirely when the window finally hears about it. Playing it from
        zero at that point puts the whole of the turn behind the fingers
        rather than the part of it that is left, and that is the lag one
        feels; handed its age instead, the animation starts the turn
        where it would already stand and the cube lands with the hand.

        The age is read on the clock of the cube and not on the arrival:
        a bluetooth stack handing two moves over in one packet gives
        them the very same arrival, and the stamps the cube wrote are
        what puts them back where the fingers made them.

        Args:
            data: Payload of a ``cube.move`` or ``cube.history`` message.

        """
        move = data.get('move')
        if not isinstance(move, str) or not move:
            return

        self.viewer.push(self.translate(move), age=self.age(data))

    def age(self, data: dict[str, Any]) -> float:
        """
        Tell how long ago the move a payload carries truly happened.

        A cube that stamps nothing, or stamps something unreadable, is
        one this client can say nothing of beyond the lead every move
        gets: what is not understood is dropped rather than guessed at,
        a client ignoring what it does not know.

        Args:
            data: Payload of a ``cube.move`` or ``cube.history`` message.

        Returns:
            The age of the move, in seconds.

        """
        stamp = data.get('cube_timestamp')

        if not isinstance(stamp, int | float) or isinstance(stamp, bool):
            stamp = None

        return self.clock.age(stamp, time.monotonic())

    def translate(self, move: str) -> str:
        """
        Read a move in the frame the cube is looked at.

        The cube reports what it turns in its own frame, and the state
        it is shown in has been turned away from it: a move played as it
        arrives would turn the wrong face of the cube on the screen.

        Args:
            move: Notation of the move, in the frame of the hardware.

        Returns:
            The notation of the same move, seen from the display.

        """
        if not self.orientation_moves:
            return move

        try:
            return str(self.translator(parse_moves(move)))
        except CubingAlgsError as error:
            logger.debug('Cannot translate move %s: %s', move, error)
            return move

    def turn_cube(self, data: dict[str, Any]) -> None:
        """
        Feed the tracker the orientation the gyroscope reports.

        Nothing is drained and nothing is queued: the tracker holds one
        orientation, the loop reads it at every frame, and a quaternion
        that arrives between two frames is simply the one that is read.

        Args:
            data: Payload of a ``cube.gyro`` message.

        """
        tracker = self.tracker
        quaternion = data.get('quaternion')

        if tracker is None or not isinstance(quaternion, dict):
            return

        try:
            tracker.update(
                float(quaternion['w']),
                float(quaternion['x']),
                float(quaternion['y']),
                float(quaternion['z']),
            )
        except (KeyError, TypeError, ValueError) as error:
            logger.debug('Cannot read a quaternion: %s', error)

    def name_cube(self, data: dict[str, Any]) -> None:
        """
        Remember how the cube calls itself, for the title.

        Args:
            data: Payload of a ``cube.hardware`` message.

        """
        name = data.get('hardware_name')

        if isinstance(name, str) and name:
            self.hardware = name

    def charge_cube(self, data: dict[str, Any]) -> None:
        """
        Remember what the battery of the cube is at, for the title.

        Args:
            data: Payload of a ``cube.battery`` message.

        """
        level = data.get('level')

        if isinstance(level, int):
            self.battery = f'{ level }%'

    def link_cube(self, data: dict[str, Any]) -> None:
        """
        Follow the link with the cube, without ever closing the window.

        A cube that goes away takes its pieces down with it and leaves
        the core alone, the state it left in kept underneath: it is the
        very state the next connection starts from, and a window that
        closed itself would take the session with it.

        What is described goes with the link, and what a cube that
        comes back has to say again is what ``unlink()`` explains.

        Args:
            data: Payload of a ``cube.link`` message.

        """
        if data.get('connected', True):
            self.connected = True
            return

        self.unlink()

    def end_session(self, data: dict[str, Any]) -> None:
        """
        Take the cube down when the publisher says its last word.

        Nothing of the session follows this message, so the cube it
        was describing is gone whatever ended it: a stream that is over
        publishes no state and no move, and a cube nobody publishes any
        more is a cube nobody is connected to. It is the picture a link
        that drops already paints, and the reason is only ever logged -
        a session closed, interrupted or carried away by an error
        leaves the very same window behind.

        The window stays open all the same, as it does for a cube that
        left: closing it would take the session with it, and a
        publisher that comes back - `interrupted` and `crashed` are
        sessions that may well - finds somewhere to be shown again.

        Args:
            data: Payload of a ``session.end`` message.

        """
        reason = data.get('reason')

        logger.info('End of the session: %s', reason or 'no reason given')

        self.unlink()

    def unlink(self) -> None:
        """
        Let the cube go, and what it said of itself with it.

        A state belongs to the connection it was published in: a cube
        that comes back describes itself again, so its pieces wait for
        that state rather than gathering on the colors of a link that
        is no longer up. What it said of its name and its charge goes
        the same way, and for the same reason: the title is what a
        cube called itself over a link that is no longer up, and a
        cube coming back may not even be the one that left.

        The reading of its clock goes the same way, and for the same
        reason: the counter of a cube runs whether or not anybody
        listens, and the cube coming back may not even be the one that
        left.
        """
        self.connected = False
        self.described = False
        self.hardware = ''
        self.battery = ''
        self.clock.reset()
