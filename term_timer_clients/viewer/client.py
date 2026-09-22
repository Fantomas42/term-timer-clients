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

from term_timer_clients.link import CubeLink
from term_timer_clients.protocol import SESSION_STATE_TOPIC
from term_timer_clients.protocol import SESSION_TRAIN_TOPIC
from term_timer_clients.viewer.flare import FAILED_WORD
from term_timer_clients.viewer.flare import SCRAMBLED_WORD
from term_timer_clients.viewer.flare import SOLVED_WORD
from term_timer_clients.viewer.flare import TRAINED_WORD

if TYPE_CHECKING:
    from cubing_algs.algorithm import Algorithm

logger = logging.getLogger(__name__)

# Title of a window that has heard nothing yet, and the pieces the rest
# of it is assembled from as the cube introduces itself
WINDOW_TITLE = 'Cubecast'
WINDOW_SEPARATOR = ' · '
WINDOW_OFFLINE = 'offline'

# The topic the cube reports its own state on, a literal like the
# other ones of the hardware plane this client adds: what a window
# does with a move is its business, and so is what it does with a cube
# that has just seen itself solved.
SOLVED_TOPIC = 'cube.solved'

# The state a session is in when the scramble is laid on the cube, and
# the one the window has anything to say about: the other eight are
# read for what they say about a cube reporting itself solved.
SCRAMBLED_STATE = 'scrambled'

# The states where a cube saying it is solved is a cube that was being
# solved. **The three and not `solving` alone**: nothing orders the
# `stop` term-timer publishes against the `solved` the cube publishes
# - one crosses a bluetooth link and the other does not - so both
# orders have to land on the same window, and a solve saved a moment
# later is still the very same solve.
#
# Everything else is a cube being fiddled with. A GAN republishes
# `cube.solved` every time it happens to be solved, scrambling and
# idle handling included - nine times in one session, as PROTOCOL.md
# puts it - so the topic is read *through* the session rather than
# on its own, or the window would announce a solve nobody made.
SOLVING_STATES = frozenset({'solving', 'stop', 'saving'})

# What the source of an envelope says when a training session is the
# one talking. It is read on the envelope rather than on a state: a
# training session walks through the very same states a timed one
# does, and what tells the two apart is who is publishing them.
TRAINING_SOURCE = 'train'


class CubeCast(CubeLink):
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

    What is read before the payload - the version of the protocol, the
    session talking, and whether there is a cube at all - is the
    ``CubeLink`` every client showing a cube is built on: this one adds
    the topics a window has a use for, and what a cube that goes away
    takes down with it.
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
        super().__init__()

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

        self.described = False

        # Added to the topics the link already answers rather than
        # written next to them: what says there is a cube is the same
        # question in every client, and what is done with a move is the
        # business of the one holding a viewer.
        self.handlers.update({
            'cube.facelets': self.show_facelets,
            'cube.move': self.play_move,
            'cube.history': self.play_move,
            'cube.gyro': self.turn_cube,
            SOLVED_TOPIC: self.celebrate,
            SESSION_STATE_TOPIC: self.follow_state,
            SESSION_TRAIN_TOPIC: self.rehearse,
        })

        # What the session says it is doing, empty for as long as
        # nothing has said anything. It is read for one thing alone:
        # whether a cube reporting itself solved is a solve landing or
        # a cube being handled.
        self.state = ''

        # The news the window is to tell at its next frame, and
        # nothing the rest of the time. Written on the stream thread
        # and read on the one that owns the window, which is the very
        # arrangement the title travels by and the one the orders of a
        # managed window travel by: the stream only ever writes down
        # what happened.
        self.wanted_flare = ''

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
        parts = self.parts

        if not self.connected:
            parts.append(WINDOW_OFFLINE)

        return WINDOW_SEPARATOR.join([WINDOW_TITLE, *parts])

    def take_flare(self) -> str:
        """
        Read the news waiting to be told, and leave nothing behind.

        Read from the thread that owns the window and written from the
        one reading the stream: it is handed over and cleared in one
        gesture, so a flare is played exactly once however many frames
        go by before the next one arrives.

        Returns:
            What is to be announced, empty when there is nothing.

        """
        wanted, self.wanted_flare = self.wanted_flare, ''

        return wanted

    def follow_state(self, data: dict[str, Any]) -> None:
        """
        Remember what the session says it is doing, and greet a scramble.

        The state is kept for the sake of the cube reporting itself
        solved, which says nothing at all about *why* it is solved: a
        cube is solved while it is being scrambled too, and what tells
        the two apart is the only thing term-timer knows and the cube
        does not.

        A state this client has never heard of is simply remembered:
        the nine of the protocol may grow, and a window refusing what
        it does not know would stop answering the day one is added.

        Args:
            data: Payload of a ``session.state`` message.

        """
        state = data.get('state')

        if not isinstance(state, str) or not state:
            return

        self.state = state

        if state == SCRAMBLED_STATE:
            self.wanted_flare = SCRAMBLED_WORD

    def celebrate(self, _data: dict[str, Any]) -> None:
        """
        Answer the cube saying it sees itself solved, when it means it.

        Read **through the session**: a GAN republishes this topic
        every time the cube happens to come back to the solved state,
        scrambling and idle fiddling included, so honoring all of them
        would have the window celebrate nine times a session. What the
        session says it is doing is the only thing telling a solve
        landing from a cube being handled.

        A session that has **never said anything at all** is honored
        all the same, and that is a decision rather than an oversight:
        it is what a client ignoring what it does not know comes to on
        this side of the question, and it is what keeps the window
        answering under a publisher of the cube plane alone - a
        ``bt-info``, a rehearsal - which is exactly where the effect
        is looked at while it is being settled.

        A **training session says it another way**, and this topic
        says nothing there: a case is drilled on a cube that always
        ends up solved, so the news is not that it came back solved
        but which attempt it was and whether it was worth anything,
        which ``session.train`` alone knows. Two breaths for one
        attempt would be the window stuttering. The source is read off
        the envelope carrying this very ``cube.solved``, the link
        writing it down before the handler is called.

        Args:
            _data: Payload of a ``cube.solved`` message. Nothing is
                read of it: the topic *is* the news, and the stamp it
                carries belongs to the move that got the cube there.

        """
        if self.source == TRAINING_SOURCE:
            return

        if self.state and self.state not in SOLVING_STATES:
            return

        self.wanted_flare = SOLVED_WORD

    def rehearse(self, data: dict[str, Any]) -> None:
        """
        Answer an attempt on a trained case, whichever way it went.

        The topic publishes every attempt that was executed, a DNF and
        a free play run included, and the two ends of it are two
        flavours rather than one told twice: a case that came out and
        a case that did not are two versions of the same thing, which
        is exactly what ``FLARES`` is shaped to say.

        Nothing else of the payload is read. What the rating, the
        state, the due date and the free play flag say is what the
        training file keeps of the attempt, and a window has no
        business with any of it.

        A ``dnf`` that is absent or unreadable is read as **not** a
        DNF, which is the permissive side and the one ``celebrate()``
        is already written on: the news is that the exercise took
        place.

        Args:
            data: Payload of a ``session.train`` message.

        """
        self.wanted_flare = (
            FAILED_WORD if data.get('dnf') is True else TRAINED_WORD
        )

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
        super().restart(session_id)

        # What a session said it was doing belongs to that session: a
        # publisher that restarted has said nothing yet, and a state
        # kept across would read the first `cube.solved` of the new
        # one through the last word of the old one.
        self.state = ''

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

    def unlink(self) -> None:
        """
        Let the cube go, and what a window held of it with it.

        A state belongs to the connection it was published in: a cube
        that comes back describes itself again, so its pieces wait for
        that state rather than gathering on the colors of a link that
        is no longer up. What it said of its name and its charge goes
        the same way, and for the same reason, which is why the link
        lets them go on its own.

        The reading of its clock goes with them: the counter of a cube
        runs whether or not anybody listens, and the cube coming back
        may not even be the one that left.
        """
        super().unlink()

        self.described = False
        self.clock.reset()

        # A piece of news nobody is left to tell it about: the window
        # is about to blow the cube apart, and a breath played on the
        # pieces already on their way out would announce a solve on a
        # cube that is no longer there.
        self.wanted_flare = ''
