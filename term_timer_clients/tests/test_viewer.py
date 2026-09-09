"""
Tests for the ``cube-cast`` client.

Nothing here opens a window: the client only translates a stream into
calls on a viewer, so a mocked one - or a real one, which needs no GPU
until a stage is attached to it - is enough. The captures of
``tests/replays/gan_gen2/`` play the part of the cube.
"""
import math
import sys
import unittest
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import create_autospec
from unittest.mock import patch

from cubing_algs.display.constants import ROTATION
from cubing_algs.display.gl import Look
from cubing_algs.display.gl import MoveClock
from cubing_algs.display.gl import OrientationTracker
from cubing_algs.display.gl import Viewer
from cubing_algs.display.gl import orientation_basis
from cubing_algs.display.gl.camera import parse_rotation
from cubing_algs.display.gl.constants import CORE_COLOR
from cubing_algs.display.gl.constants import DEFAULT_LOOK
from cubing_algs.display.gl.constants import HELP_CLOSE
from cubing_algs.display.gl.constants import MOVE_LEAD
from cubing_algs.display.gl.constants import VIEWER_BACKGROUND
from cubing_algs.display.gl.constants import VIEWER_HELP
from cubing_algs.display.gl.constants import viewer_help
from cubing_algs.display.gl.context import GLContextError
from cubing_algs.display.gl.host import GlfwHost
from cubing_algs.display.gl.scene import CubieInstance
from cubing_algs.display.gl.scene import Scene
from cubing_algs.display.gl.transforms import ORIGIN
from cubing_algs.display.gl.transforms import Quat
from cubing_algs.display.gl.transforms import Vec3
from cubing_algs.vcube import VCube

from term_timer_clients.orders import CLOSE_ORDER
from term_timer_clients.orders import HIDE_ORDER
from term_timer_clients.orders import SHOW_ORDER
from term_timer_clients.protocol import SESSION_END_TOPIC
from term_timer_clients.protocol import SESSION_PREFIX
from term_timer_clients.tests.fixtures import envelope
from term_timer_clients.tests.fixtures import envelopes
from term_timer_clients.viewer import main as entry
from term_timer_clients.viewer.assembly import CORE_DURATION
from term_timer_clients.viewer.assembly import DORMANT_CORE
from term_timer_clients.viewer.assembly import EXPLOSION_DURATION
from term_timer_clients.viewer.assembly import IMPLOSION_DURATION
from term_timer_clients.viewer.assembly import PULSE_CORE
from term_timer_clients.viewer.assembly import PULSE_PERIOD
from term_timer_clients.viewer.assembly import SPIN_PERIOD
from term_timer_clients.viewer.assembly import Assembly
from term_timer_clients.viewer.assembly import Flight
from term_timer_clients.viewer.assembly import breath
from term_timer_clients.viewer.assembly import tumble_axis
from term_timer_clients.viewer.assembly import waiting_core
from term_timer_clients.viewer.client import WINDOW_OFFLINE
from term_timer_clients.viewer.client import WINDOW_TITLE
from term_timer_clients.viewer.client import CubeCast
from term_timer_clients.viewer.framing import DEMO_VIEW
from term_timer_clients.viewer.framing import USER_ROTATION
from term_timer_clients.viewer.framing import USER_VIEW
from term_timer_clients.viewer.framing import Framing
from term_timer_clients.viewer.framing import flipped
from term_timer_clients.viewer.host import MANAGED_SHORTCUTS
from term_timer_clients.viewer.host import VIEWER_SHORTCUTS
from term_timer_clients.viewer.host import CubeCastHost

ENDPOINT = 'tcp://127.0.0.1:5333'

# A configuration as term-timer writes it, cut down to what a client
# of the stream reads in it
CONFIG = {
    'publisher': {
        'active': True,
        'endpoints': [ENDPOINT],
    },
    'cube': {
        'orientation': 'DF',
        'palette': 'dracula',
    },
}

# A cube describing itself, which is what a client waits for before it
# shows one at all
FACELETS = VCube().state

# The glfw code of backspace, glfw never being imported here
BACKSPACE = 259

# The glfw codes of the mouse, named here for the same reason
LEFT_BUTTON = 0
RIGHT_BUTTON = 1
RELEASE = 0
PRESS = 1
CONTROL = 2


def mouse_glfw() -> MagicMock:
    """
    Build the glfw the mouse handlers read their codes from.

    Returns:
        A mock naming the buttons, the actions and the modifier, and
        answering a cursor position the anchor can be read from.

    """
    glfw = MagicMock()
    glfw.PRESS = PRESS
    glfw.MOUSE_BUTTON_LEFT = LEFT_BUTTON
    glfw.MOD_CONTROL = CONTROL
    glfw.get_cursor_pos.return_value = (5.0, 7.0)

    return glfw


def replay(view: CubeCast, name: str) -> None:
    """
    Play a capture through the client, event by event.

    Args:
        view: The client the capture is played into.
        name: Name of the capture file.

    """
    for message in envelopes(name):
        view.dispatch(message)


def solved_scene() -> Scene:
    """
    Build the scene of a solved cube, without a GPU anywhere near it.

    A viewer builds its geometry and its scene when it is created, and
    only asks for a context once a stage is attached to it: what comes
    out of here is the very picture a window would be handed.

    Returns:
        The scene of a solved 3x3x3.

    """
    return Viewer(cube=VCube()).scene


def run_main(
        host: MagicMock,
        stream: MagicMock,
        extra: Sequence[str] = (),
) -> int:
    """
    Run the entry point on a mocked window and a mocked stream.

    Args:
        host: The host standing in for the window.
        stream: The object standing in for the subscription.
        extra: What is typed on top of the endpoint.

    Returns:
        The exit code of the entry point.

    """
    argv = ['cube-cast', '-e', ENDPOINT, *extra]

    # The configuration of a machine running the tests is never read:
    # what the client is given here is its command line and nothing else
    with (
        patch.object(sys, 'argv', argv),
        patch.object(entry, 'load_config', return_value={}),
        patch.object(entry, 'build_host', return_value=host),
        patch.object(entry, 'EventStream', return_value=stream),
    ):
        return entry.main()


class ClientTestCase(unittest.TestCase):
    """Base case wiring a client on a mocked viewer."""

    def setUp(self) -> None:
        """Wire a client on a viewer holding a solved 3x3x3."""
        self.viewer = create_autospec(Viewer, instance=True)
        self.viewer.cube = VCube()
        self.tracker = OrientationTracker()
        self.view = CubeCast(self.viewer, self.tracker)


class EnvelopeTestCase(ClientTestCase):
    """What the client reads before the payload of a message."""

    def test_unknown_protocol_is_ignored(self) -> None:
        """A message of another protocol version does nothing."""
        self.view.dispatch(envelope('cube.move', {'move': 'R'}, version=2))

        self.viewer.push.assert_not_called()

    def test_unknown_topic_is_ignored(self) -> None:
        """A topic the client knows nothing about does nothing."""
        self.view.dispatch(envelope('session.record', {'kind': 'single'}))

        self.viewer.push.assert_not_called()

    def test_session_is_followed(self) -> None:
        """The session identifier of the stream is remembered."""
        self.view.dispatch(envelope('cube.move', {'move': 'R'}))

        self.assertEqual(self.view.session_id, 'a3f1c8d2')

    def test_new_session_starts_over(self) -> None:
        """A publisher that restarted resets the cube and the tracker."""
        self.view.dispatch(envelope('cube.battery', {'level': 80}))
        self.tracker.update(1.0, 0.0, 0.0, 0.0)

        self.view.dispatch(
            envelope('cube.move', {'move': 'R'}, session_id='ffffffff'),
        )

        self.assertEqual(self.view.session_id, 'ffffffff')
        self.assertEqual(self.view.battery, '')
        self.assertIsNone(self.tracker.reference)
        self.assertEqual(self.viewer.cube.state, VCube().state)

    def test_data_that_is_not_an_object_is_ignored(self) -> None:
        """A payload that is not an object is handed over as an empty one."""
        message = envelope('cube.move')
        message['data'] = ['R']

        self.view.dispatch(message)

        self.viewer.push.assert_not_called()


class CubeStateTestCase(ClientTestCase):
    """What the client does with the state the hardware describes."""

    def test_facelets_repose_the_cube(self) -> None:
        """A described state becomes the cube the viewer holds."""
        cube = VCube()
        cube.rotate("R U R' U'")

        self.view.dispatch(
            envelope('cube.facelets', {'facelets': cube.state}),
        )

        self.assertEqual(self.viewer.cube.state, cube.state)

    def test_facelets_are_oriented(self) -> None:
        """A described state is turned the way the cube is looked at."""
        view = CubeCast(self.viewer, self.tracker, 'DF')
        cube = VCube()
        cube.rotate("R U R' U'")

        view.dispatch(envelope('cube.facelets', {'facelets': cube.state}))

        self.assertEqual(
            self.viewer.cube.state,
            cube.oriented_copy('DF').state,
        )

    def test_facelets_without_state_are_ignored(self) -> None:
        """A message carrying no state leaves the cube alone."""
        self.view.dispatch(envelope('cube.facelets', {'serial': 1}))

        self.assertEqual(self.viewer.cube.state, VCube().state)

    def test_broken_facelets_are_ignored(self) -> None:
        """A state no cube can be built from leaves the cube alone."""
        self.view.dispatch(envelope('cube.facelets', {'facelets': 'UUU'}))

        self.assertEqual(self.viewer.cube.state, VCube().state)

    def test_another_cube_size_is_ignored(self) -> None:
        """A state of another size is not one this window can show."""
        self.view.dispatch(
            envelope('cube.facelets', {'facelets': VCube(size=2).state}),
        )

        self.assertEqual(self.viewer.cube.size, 3)
        self.assertEqual(self.viewer.cube.state, VCube().state)


class CubeMoveTestCase(ClientTestCase):
    """What the client does with the moves the cube reports."""

    def test_move_is_pushed_as_it_arrives(self) -> None:
        """A move reaches the viewer the moment it is heard."""
        self.view.dispatch(envelope('cube.move', {'move': "R'"}))

        self.viewer.push.assert_called_once_with("R'", age=MOVE_LEAD)

    def test_history_is_pushed_too(self) -> None:
        """A move caught up on is played like any other."""
        self.view.dispatch(envelope('cube.history', {'move': 'U2'}))

        self.viewer.push.assert_called_once_with('U2', age=MOVE_LEAD)

    def test_move_is_read_in_the_display_frame(self) -> None:
        """A move is turned the way the cube is looked at."""
        view = CubeCast(self.viewer, self.tracker, 'DF')

        view.dispatch(envelope('cube.move', {'move': 'L'}))

        self.viewer.push.assert_called_once_with('R', age=MOVE_LEAD)

    def test_empty_move_is_ignored(self) -> None:
        """A message carrying no move plays nothing."""
        self.view.dispatch(envelope('cube.move', {'move': ''}))
        self.view.dispatch(envelope('cube.move', {'serial': 3}))

        self.viewer.push.assert_not_called()

    def test_untranslatable_move_is_pushed_as_it_is(self) -> None:
        """A notation nothing can read is handed over untouched."""
        view = CubeCast(self.viewer, self.tracker, 'DF')

        view.dispatch(envelope('cube.move', {'move': '[R,'}))

        self.viewer.push.assert_called_once_with('[R,', age=MOVE_LEAD)


class CubeMoveAgeTestCase(ClientTestCase):
    """How old a move is by the time the viewer is handed it."""

    def test_a_move_is_pushed_as_old_as_it_is(self) -> None:
        """The age the clock reads is the age the viewer plays from."""
        view = CubeCast(self.viewer, self.tracker, clock=MoveClock(lead=0.02))

        view.dispatch(envelope('cube.move', {'move': 'R'}))

        self.viewer.push.assert_called_once_with('R', age=0.02)

    def test_an_unreadable_stamp_is_dropped_rather_than_guessed(self) -> None:
        """A cube stamping nonsense is one nothing can be read from."""
        view = CubeCast(self.viewer, self.tracker, clock=MoveClock(lead=0.02))

        view.dispatch(
            envelope('cube.move', {'move': 'R', 'cube_timestamp': 'soon'}),
        )
        view.dispatch(
            envelope('cube.move', {'move': 'U', 'cube_timestamp': True}),
        )

        for call in self.viewer.push.call_args_list:
            self.assertEqual(call.kwargs['age'], 0.02)

    def test_a_new_session_starts_the_clock_over(self) -> None:
        """A publisher that restarted may not even be the same cube."""
        self.view.dispatch(envelope('cube.move', {'move': 'R'}))
        self.view.clock.age(1000.0, 10.0)

        self.view.dispatch(
            envelope('cube.move', {'move': 'U'}, session_id='b7e2'),
        )

        self.assertEqual(len(self.view.clock.delays), 0)

    def test_a_link_that_drops_starts_the_clock_over(self) -> None:
        """The counter of a cube runs whether or not anybody listens."""
        self.view.clock.age(1000.0, 10.0)

        self.view.dispatch(envelope('cube.link', {'connected': False}))

        self.assertEqual(len(self.view.clock.delays), 0)


class CubeSensorTestCase(ClientTestCase):
    """The gyroscope, and what the cube says about itself."""

    def test_gyro_feeds_the_tracker(self) -> None:
        """A quaternion reaches the tracker the viewer reads."""
        self.view.dispatch(
            envelope(
                'cube.gyro',
                {'quaternion': {'w': 1.0, 'x': 0.0, 'y': 0.0, 'z': 0.0}},
            ),
        )

        self.assertIsNotNone(self.tracker.reference)

    def test_broken_gyro_is_ignored(self) -> None:
        """An incomplete quaternion leaves the tracker alone."""
        self.view.dispatch(envelope('cube.gyro', {'quaternion': {'w': 1.0}}))
        self.view.dispatch(envelope('cube.gyro', {'velocity': {}}))

        self.assertIsNone(self.tracker.reference)

    def test_gyro_without_tracker_is_ignored(self) -> None:
        """A client with no tracker simply drops the quaternions."""
        view = CubeCast(self.viewer)

        view.dispatch(
            envelope(
                'cube.gyro',
                {'quaternion': {'w': 1.0, 'x': 0.0, 'y': 0.0, 'z': 0.0}},
            ),
        )

        self.assertIsNone(view.tracker)

    def test_title_opens_offline(self) -> None:
        """A stream that has said nothing yet has no cube behind it."""
        self.assertEqual(self.view.title, f'{ WINDOW_TITLE } · offline')

    def test_title_names_the_cube(self) -> None:
        """The hardware and the battery are written in the title."""
        self.view.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}),
        )
        self.view.dispatch(envelope('cube.battery', {'level': 80}))

        self.assertEqual(self.view.title, f'{ WINDOW_TITLE } · GANi3 · 80%')

    def test_title_says_the_cube_left(self) -> None:
        """A link that drops is told in the title, and told back."""
        self.view.dispatch(
            envelope('cube.link', {'connected': False, 'reason': 'lost'}),
        )

        self.assertEqual(self.view.title, f'{ WINDOW_TITLE } · offline')

        self.view.dispatch(
            envelope('cube.link', {'connected': True, 'reason': 'opened'}),
        )

        self.assertEqual(self.view.title, WINDOW_TITLE)

    def test_title_drops_what_a_gone_cube_said_of_itself(self) -> None:
        """A cube gone takes its name and its charge with it."""
        self.view.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}),
        )
        self.view.dispatch(envelope('cube.battery', {'level': 80}))

        self.view.dispatch(
            envelope('cube.link', {'connected': False, 'reason': 'lost'}),
        )

        self.assertEqual(self.view.title, f'{ WINDOW_TITLE } · offline')

    def test_nameless_hardware_is_ignored(self) -> None:
        """What says nothing about the cube leaves the title alone."""
        self.view.dispatch(envelope('cube.hardware', {'hardware_name': ''}))
        self.view.dispatch(envelope('cube.battery', {'level': 'high'}))

        self.assertEqual(self.view.title, WINDOW_TITLE)


class CubeLinkTestCase(ClientTestCase):
    """Whether there is a cube to show at all, and what it looks like."""

    def test_a_stream_that_said_nothing_has_no_cube(self) -> None:
        """A client that has heard nothing yet shows nothing."""
        self.assertFalse(self.view.present)

    def test_a_link_alone_shows_no_cube(self) -> None:
        """A cube that has not described itself is not shown."""
        self.view.dispatch(
            envelope('cube.link', {'connected': True, 'reason': 'opened'}),
        )

        self.assertFalse(self.view.present)

    def test_a_described_cube_is_shown(self) -> None:
        """A cube that said what it looks like is a cube to show."""
        self.view.dispatch(
            envelope('cube.link', {'connected': True, 'reason': 'opened'}),
        )
        self.view.dispatch(envelope('cube.facelets', {'facelets': FACELETS}))

        self.assertTrue(self.view.present)

    def test_a_cube_talking_is_a_cube_that_is_there(self) -> None:
        """A client opened mid session hears no arrival, and shows the cube."""
        self.view.dispatch(envelope('cube.facelets', {'facelets': FACELETS}))

        self.assertTrue(self.view.present)

    def test_a_move_heard_alone_shows_no_cube(self) -> None:
        """A cube turning is a cube there, and not a cube described."""
        self.view.dispatch(envelope('cube.move', {'move': 'R'}))

        self.assertTrue(self.view.connected)
        self.assertFalse(self.view.described)
        self.assertFalse(self.view.present)

    def test_a_link_is_waited_on_for_the_colors(self) -> None:
        """A cube that just connected says what it looks like in a moment."""
        self.view.dispatch(
            envelope('cube.link', {'connected': True, 'reason': 'opened'}),
        )
        self.view.dispatch(envelope('cube.move', {'move': 'R'}))

        self.assertFalse(self.view.present)

        self.view.dispatch(envelope('cube.facelets', {'facelets': FACELETS}))

        self.assertTrue(self.view.present)

    def test_a_new_session_starts_over_from_no_colors(self) -> None:
        """A publisher that restarted describes its cube to this window."""
        self.view.dispatch(
            envelope('cube.link', {'connected': True, 'reason': 'opened'}),
        )
        self.view.dispatch(envelope('cube.facelets', {'facelets': FACELETS}))

        self.view.dispatch(
            envelope('cube.move', {'move': 'R'}, session_id='ffffffff'),
        )

        self.assertFalse(self.view.present)

        self.view.dispatch(
            envelope(
                'cube.facelets', {'facelets': FACELETS},
                session_id='ffffffff',
            ),
        )

        self.assertTrue(self.view.present)

    def test_the_session_plane_says_nothing_of_the_cube(self) -> None:
        """What term-timer knows alone is no proof a cube is there."""
        self.view.dispatch(envelope('session.record', {'kind': 'single'}))

        self.assertFalse(self.view.connected)

    def test_a_cube_that_left_is_not_shown_any_more(self) -> None:
        """A link that drops takes the cube off the window."""
        self.view.dispatch(envelope('cube.facelets', {'facelets': FACELETS}))
        self.view.dispatch(
            envelope('cube.link', {'connected': False, 'reason': 'lost'}),
        )

        self.assertFalse(self.view.present)

    def test_a_link_that_comes_back_waits_for_the_colors_again(self) -> None:
        """A cube that left describes itself again before it is shown."""
        self.view.dispatch(envelope('cube.facelets', {'facelets': FACELETS}))
        self.view.dispatch(
            envelope('cube.link', {'connected': False, 'reason': 'lost'}),
        )
        self.view.dispatch(
            envelope('cube.link', {'connected': True, 'reason': 'opened'}),
        )

        self.assertFalse(self.view.described)
        self.assertFalse(self.view.present)

        self.view.dispatch(envelope('cube.facelets', {'facelets': FACELETS}))

        self.assertTrue(self.view.present)

    def test_a_link_that_drops_lets_the_colors_go(self) -> None:
        """A state belongs to the connection it was published in."""
        self.view.dispatch(envelope('cube.facelets', {'facelets': FACELETS}))
        self.view.dispatch(
            envelope('cube.link', {'connected': False, 'reason': 'lost'}),
        )

        self.assertFalse(self.view.described)

    def test_a_new_session_throws_the_old_cube_away(self) -> None:
        """A publisher that restarted describes its cube again."""
        self.view.dispatch(envelope('cube.facelets', {'facelets': FACELETS}))

        self.view.dispatch(
            envelope('cube.gyro', {}, session_id='ffffffff'),
        )

        self.assertFalse(self.view.described)
        self.assertTrue(self.viewer.cube.is_solved)


class SessionEndTestCase(ClientTestCase):
    """The farewell of a publisher, and what is left in the window."""

    def test_a_session_that_ends_takes_the_cube_with_it(self) -> None:
        """A stream that is over describes no cube any more."""
        self.view.dispatch(envelope('cube.facelets', {'facelets': FACELETS}))

        self.assertTrue(self.view.present)

        self.view.dispatch(
            envelope(SESSION_END_TOPIC, {'reason': 'closed'}),
        )

        self.assertFalse(self.view.connected)
        self.assertFalse(self.view.described)
        self.assertFalse(self.view.present)

    def test_every_reason_ends_the_same_window(self) -> None:
        """What ended a session says nothing about what is drawn."""
        for reason in ('closed', 'interrupted', 'crashed', ''):
            with self.subTest(reason=reason):
                view = CubeCast(self.viewer, self.tracker)
                view.dispatch(
                    envelope('cube.facelets', {'facelets': FACELETS}),
                )
                view.dispatch(envelope(SESSION_END_TOPIC, {'reason': reason}))

                self.assertFalse(view.present)

    def test_a_session_that_ends_says_so_in_the_title(self) -> None:
        """The window that stays open says what it is showing."""
        self.view.dispatch(envelope('cube.hardware', {'hardware_name': 'GAN'}))
        self.view.dispatch(envelope(SESSION_END_TOPIC, {'reason': 'closed'}))

        self.assertIn(WINDOW_OFFLINE, self.view.title)

    def test_a_cube_comes_back_with_the_next_session(self) -> None:
        """A publisher that comes back finds somewhere to be shown."""
        self.view.dispatch(envelope('cube.facelets', {'facelets': FACELETS}))
        self.view.dispatch(
            envelope(SESSION_END_TOPIC, {'reason': 'interrupted'}),
        )

        self.view.dispatch(
            envelope(
                'cube.facelets', {'facelets': FACELETS},
                session_id='ffffffff',
            ),
        )

        self.assertTrue(self.view.present)


def cube_place(instance: CubieInstance) -> Vec3:
    """
    Tell where a piece stands, wherever the blast has taken it.

    Args:
        instance: The piece to locate.

    Returns:
        The center of the piece, in the frame of the cube.

    """
    return instance.model.transform_point(ORIGIN)


class AssemblyTestCase(unittest.TestCase):
    """The cube imploding around its core, and exploding away from it."""

    def test_a_cube_gathers_in_a_bounded_time(self) -> None:
        """A cube that arrives is whole once the implosion is done."""
        assembly = Assembly()

        assembly.settle(
            present=True, linked=True, delta=IMPLOSION_DURATION / 2,
        )

        self.assertAlmostEqual(assembly.progress, 0.5)

        assembly.settle(present=True, linked=True, delta=IMPLOSION_DURATION)

        self.assertEqual(assembly.progress, 1.0)

    def test_a_cube_that_left_is_blown_all_the_way_out(self) -> None:
        """A cube that explodes is never half thrown out for good."""
        assembly = Assembly(progress=1.0)

        assembly.settle(
            present=False, linked=False, delta=EXPLOSION_DURATION * 2,
        )

        self.assertEqual(assembly.progress, 0.0)

    def test_a_frame_going_backwards_moves_nothing(self) -> None:
        """A clock that went back leaves the assembly where it was."""
        assembly = Assembly(progress=0.5, glow=0.5)

        assembly.settle(present=True, linked=True, delta=-1.0)

        self.assertEqual(assembly.progress, 0.5)
        self.assertEqual(assembly.glow, 0.5)

    def test_a_whole_cube_is_handed_back_untouched(self) -> None:
        """A cube that is all there costs the effect nothing at all."""
        scene = solved_scene()

        self.assertIs(Assembly(progress=1.0).apply(scene), scene)

    def test_a_cube_that_is_not_there_has_no_piece(self) -> None:
        """A disconnected cube leaves the ball core alone in the window."""
        scene = solved_scene()
        assembly = Assembly()

        empty = assembly.apply(scene)

        self.assertEqual(empty.instances, ())
        self.assertIs(assembly.apply(scene), empty)

    def test_every_piece_is_still_drawn_in_flight(self) -> None:
        """A cube on its way keeps all of its pieces."""
        scene = solved_scene()

        flying = Assembly(progress=0.5).apply(scene)

        self.assertEqual(len(flying.instances), len(scene.instances))

    def test_a_piece_only_ever_travels_its_own_ray(self) -> None:
        """A blast leaves the core, and nothing crosses the middle."""
        scene = solved_scene()

        flying = Assembly(progress=0.5).apply(scene)

        for resting, flown in zip(
                scene.instances, flying.instances, strict=True,
        ):
            place = cube_place(resting)
            flight = cube_place(flown)

            # Still on the ray it belongs to: the cross product of the
            # two is nothing at all, and the dot product is positive
            self.assertAlmostEqual(place.cross(flight).length(), 0.0)
            self.assertGreater(place.dot(flight), 0.0)
            self.assertGreater(flight.length(), place.length())

    def test_a_piece_goes_out_as_it_goes_away(self) -> None:
        """One ray points at the camera: nothing may loom over the core."""
        scene = solved_scene()

        flying = Assembly(progress=0.5).apply(scene)

        for flown in flying.instances:
            self.assertLess(
                flown.model.transform_direction(
                    Vec3(1.0, 0.0, 0.0),
                ).length(),
                1.0,
            )

    def test_no_piece_is_ever_driven_into_another(self) -> None:
        """The shells keep their order, so nothing goes through anything."""
        scene = solved_scene()

        for progress in (0.1, 0.3, 0.5, 0.7, 0.9):
            flying = Assembly(progress=progress).apply(scene)

            shells: dict[float, set[float]] = {}

            for resting, flown in zip(
                    scene.instances, flying.instances, strict=True,
            ):
                shells.setdefault(
                    round(cube_place(resting).length(), 6), set(),
                ).add(round(cube_place(flown).length(), 6))

            thrown = []

            for _radius, shell in sorted(shells.items()):
                # A shell leaves in one piece: what a piece is handed
                # is read off its distance to the core alone
                self.assertEqual(len(shell), 1)

                thrown.append(shell.pop())

            # An outer shell is never less thrown out than the one it
            # covers, at any moment of the blast
            self.assertEqual(thrown, sorted(thrown))
            self.assertEqual(len(set(thrown)), len(thrown))

    def test_the_innermost_pieces_are_the_first_to_gather(self) -> None:
        """A blast runs through the cube rather than moving it in one block."""
        flight = Flight(reach=1.0, progress=0.5)

        self.assertGreater(flight.phase(0.5), flight.phase(1.0))

    def test_a_cube_blows_apart_the_same_way_twice(self) -> None:
        """What a piece is turned by in flight is drawn from itself."""
        scene = solved_scene()

        self.assertEqual(
            Assembly(progress=0.5).apply(scene).instances,
            Assembly(progress=0.5).apply(scene).instances,
        )

    def test_two_pieces_do_not_turn_alike(self) -> None:
        """No two neighbours tumble on the same axis."""
        cubies = [instance.cubie for instance in solved_scene().instances]

        self.assertNotEqual(tumble_axis(cubies[0]), tumble_axis(cubies[1]))

    def test_the_blast_reaches_as_far_as_the_geometry_says(self) -> None:
        """What the pieces are ranked by is read off the cube itself."""
        scene = solved_scene()

        self.assertAlmostEqual(
            scene.geometry.reach,
            max(
                instance.cubie.center.length()
                for instance in scene.instances
            ),
        )

    def test_time_passes_before_the_picture_is_drawn(self) -> None:
        """One call lets the time pass and hands the picture over."""
        scene = solved_scene()
        assembly = Assembly()

        drawn = assembly.advance(
            scene,
            present=True, linked=True, delta=IMPLOSION_DURATION,
        )

        self.assertEqual(assembly.progress, 1.0)
        self.assertIs(drawn, scene)


class DormantGroundTestCase(unittest.TestCase):
    """What the ground of cubing-algs owes a core left on its own."""

    def test_the_ground_stays_above_the_dormant_core(self) -> None:
        """
        Test that the window is never cleared darker than the ball.

        The ground belongs to cubing-algs and the graphite belongs
        here: this client is the one dimming the core while nothing
        drives the cube, so it is the one that has to notice the day
        the window is cleared with something darker than the only
        thing it is left showing.
        """
        for channel, dormant in zip(
                VIEWER_BACKGROUND[:3], DORMANT_CORE, strict=True,
        ):
            self.assertGreater(channel, dormant)


class CoreTintTestCase(unittest.TestCase):
    """The ball core, painted for the cube standing around it."""

    def test_a_core_with_no_cube_around_it_is_graphite(self) -> None:
        """The one thing left in the window says there is nothing behind."""
        self.assertEqual(
            Assembly().tint(DEFAULT_LOOK).core_color, DORMANT_CORE,
        )

    def test_a_lit_core_keeps_the_look_it_was_handed(self) -> None:
        """A connected viewer draws the picture cubing-algs describes."""
        self.assertIs(
            Assembly(progress=1.0, glow=1.0).tint(DEFAULT_LOOK),
            DEFAULT_LOOK,
        )

    def test_the_core_lights_up_along_the_link(self) -> None:
        """The color travels on the link, not on a switch of its own."""
        mixed = Assembly(glow=0.5).tint(DEFAULT_LOOK).core_color

        for dormant, channel, live in zip(
                DORMANT_CORE, mixed, CORE_COLOR, strict=True,
        ):
            self.assertGreater(channel, min(dormant, live))
            self.assertLess(channel, max(dormant, live))

    def test_a_waiting_core_breathes(self) -> None:
        """A still picture would not say whether the viewer is alive."""
        self.assertNotEqual(
            Assembly(elapsed=PULSE_PERIOD / 2).tint(DEFAULT_LOOK).core_color,
            Assembly().tint(DEFAULT_LOOK).core_color,
        )

    def test_the_breath_starts_and_ends_on_the_graphite(self) -> None:
        """A swell with no corner is what keeps a wait from blinking."""
        self.assertEqual(waiting_core(0.0), DORMANT_CORE)
        self.assertEqual(waiting_core(PULSE_PERIOD), DORMANT_CORE)

    def test_the_breath_peaks_on_the_standby_core(self) -> None:
        """Half a period in, the ball is the color it breathes to."""
        for channel, standby in zip(
                waiting_core(PULSE_PERIOD / 2), PULSE_CORE, strict=True,
        ):
            self.assertAlmostEqual(channel, standby)

    def test_the_breath_wears_the_hue_of_a_live_core(self) -> None:
        """The wait is about a cube, and says so with its color."""
        for elapsed in (0.3, PULSE_PERIOD / 3, PULSE_PERIOD / 2):
            red, green, blue = waiting_core(elapsed)

            for dormant, channel, standby in zip(
                    DORMANT_CORE, (red, green, blue), PULSE_CORE, strict=True,
            ):
                self.assertGreaterEqual(channel, min(dormant, standby))
                self.assertLessEqual(channel, max(dormant, standby))

            self.assertGreater(green, red)
            self.assertGreater(blue, red)

    def test_the_breath_never_reaches_a_live_core(self) -> None:
        """Waiting is never to be read as running: the light says so."""
        for elapsed in (0.3, PULSE_PERIOD / 3, PULSE_PERIOD / 2):
            for channel, live in zip(
                    waiting_core(elapsed), CORE_COLOR, strict=True,
            ):
                self.assertLess(channel, live)

    def test_the_light_swells_with_the_color(self) -> None:
        """The core says it is waiting with its rim as well as its hue."""
        self.assertGreater(
            Assembly(elapsed=PULSE_PERIOD / 2).tint(
                DEFAULT_LOOK,
            ).core_rim_strength,
            DEFAULT_LOOK.core_rim_strength,
        )

    def test_the_light_reaches_further_in_at_the_peak(self) -> None:
        """A rim gaining in strength alone would only line the edge."""
        self.assertLess(
            Assembly(elapsed=PULSE_PERIOD / 2).tint(
                DEFAULT_LOOK,
            ).core_rim_power,
            DEFAULT_LOOK.core_rim_power,
        )

    def test_the_breath_never_touches_the_highlight(self) -> None:
        """An added white swelling over the ball washes it out."""
        rest = Assembly().tint(DEFAULT_LOOK)
        peak = Assembly(elapsed=PULSE_PERIOD / 2).tint(DEFAULT_LOOK)

        self.assertEqual(
            peak.core_specular_strength, rest.core_specular_strength,
        )
        self.assertEqual(
            peak.core_specular_power, rest.core_specular_power,
        )

    def test_the_swell_rests_longer_than_it_rises(self) -> None:
        """An even breath in and out beats like a metronome."""
        self.assertLess(breath(PULSE_PERIOD / 4), 0.5)

    def test_a_link_lights_the_core_with_no_cube_described(self) -> None:
        """The ball answers the link, not the state that follows it."""
        assembly = Assembly()

        assembly.settle(present=False, linked=True, delta=CORE_DURATION)

        self.assertEqual(assembly.glow, 1.0)
        self.assertEqual(assembly.progress, 0.0)
        self.assertIs(assembly.tint(DEFAULT_LOOK), DEFAULT_LOOK)

    def test_a_core_goes_out_with_the_pieces_falling(self) -> None:
        """A cube goes away in one gesture where it arrives in two."""
        assembly = Assembly(progress=1.0, glow=1.0)

        assembly.settle(
            present=False, linked=False, delta=EXPLOSION_DURATION / 2,
        )

        self.assertAlmostEqual(assembly.glow, assembly.progress)

    def test_the_breath_dies_out_as_the_core_lights_up(self) -> None:
        """The breath goes out exactly as the color comes in."""
        peak = PULSE_PERIOD / 2
        half = Assembly(glow=0.5, elapsed=peak)

        self.assertLess(
            half.tint(DEFAULT_LOOK).core_rim_strength,
            Assembly(elapsed=peak).tint(DEFAULT_LOOK).core_rim_strength,
        )
        self.assertGreater(
            half.tint(DEFAULT_LOOK).core_rim_strength,
            DEFAULT_LOOK.core_rim_strength,
        )

    def test_a_waiting_core_reads_as_metal(self) -> None:
        """A bare sphere carries the window alone on a harder spark."""
        dormant = Assembly().tint(DEFAULT_LOOK)

        self.assertGreater(
            dormant.core_specular_strength,
            DEFAULT_LOOK.core_specular_strength,
        )
        self.assertGreater(
            dormant.core_specular_power,
            DEFAULT_LOOK.core_specular_power,
        )
        self.assertGreater(
            dormant.core_metalness,
            DEFAULT_LOOK.core_metalness,
        )

    def test_the_highlight_settles_as_the_link_comes_up(self) -> None:
        """The spark is spent on what is missing, not on the breath."""
        half = Assembly(glow=0.5, elapsed=PULSE_PERIOD / 2).tint(DEFAULT_LOOK)

        self.assertLess(
            half.core_specular_strength,
            Assembly(elapsed=PULSE_PERIOD / 2).tint(
                DEFAULT_LOOK,
            ).core_specular_strength,
        )
        self.assertGreater(
            half.core_specular_strength,
            DEFAULT_LOOK.core_specular_strength,
        )

    def test_the_metalness_settles_as_the_link_comes_up(self) -> None:
        """The core is only ever as metal as it is missing a cube."""
        half = Assembly(glow=0.5).tint(DEFAULT_LOOK).core_metalness

        self.assertGreater(half, DEFAULT_LOOK.core_metalness)
        self.assertLess(half, Assembly().tint(DEFAULT_LOOK).core_metalness)

    def test_a_connected_core_keeps_its_own_metalness(self) -> None:
        """Nothing of the dormant material survives a cube standing whole."""
        self.assertEqual(
            Assembly(progress=1.0, glow=1.0).tint(
                DEFAULT_LOOK,
            ).core_metalness,
            DEFAULT_LOOK.core_metalness,
        )

    def test_the_breath_is_wrapped_on_its_period(self) -> None:
        """A window nobody closes would count a night into a float."""
        assembly = Assembly()

        for _ in range(4):
            assembly.settle(present=False, linked=False, delta=PULSE_PERIOD / 2)

        self.assertLess(assembly.elapsed, PULSE_PERIOD)
        self.assertAlmostEqual(breath(assembly.elapsed), 0.0)


class CoreSpinTestCase(unittest.TestCase):
    """The lamp walking around a core nobody is connected to."""

    @staticmethod
    def gap(direction: tuple[float, float, float]) -> float:
        """
        Tell how far the lamp stands from where the look put it.

        Read on the angle rather than channel by channel: the light
        travels an arc, so a single channel of it swings past both of
        its ends on the way and says nothing about the distance left.

        Args:
            direction: The light as the moment has it.

        Returns:
            How much the lamp has turned away, the more the smaller.

        """
        return Vec3(*direction).normalized().dot(
            Vec3(*DEFAULT_LOOK.light_direction).normalized(),
        )

    def test_the_lamp_walks_around_a_waiting_core(self) -> None:
        """A ball of one color can only be seen to turn by its light."""
        quarter = Assembly(turned=SPIN_PERIOD / 4).tint(DEFAULT_LOOK)

        self.assertNotEqual(
            quarter.light_direction, DEFAULT_LOOK.light_direction,
        )
        self.assertAlmostEqual(
            Vec3(*quarter.light_direction).length(),
            Vec3(*DEFAULT_LOOK.light_direction).length(),
        )

    def test_the_lamp_goes_around_the_vertical(self) -> None:
        """A spot going round the top reads as a ball rolling."""
        for turned in (SPIN_PERIOD / 4, SPIN_PERIOD / 3, SPIN_PERIOD / 2):
            self.assertAlmostEqual(
                Assembly(turned=turned).tint(DEFAULT_LOOK).light_direction[1],
                DEFAULT_LOOK.light_direction[1],
            )

    def test_the_lamp_closes_its_turn_where_it_opened_it(self) -> None:
        """A light that jumped at the wrap would blink on the ball."""
        self.assertEqual(
            Assembly(turned=0.0).tint(DEFAULT_LOOK).light_direction,
            DEFAULT_LOOK.light_direction,
        )

        for channel, live in zip(
                Assembly(turned=SPIN_PERIOD).tint(DEFAULT_LOOK).light_direction,
                DEFAULT_LOOK.light_direction, strict=True,
        ):
            self.assertAlmostEqual(channel, live)

    def test_a_connected_cube_is_lit_from_where_the_look_says(self) -> None:
        """The lamp of the core is the lamp of the cube: it goes home."""
        for channel, live in zip(
                Assembly(glow=1.0, turned=SPIN_PERIOD / 3).tint(
                    DEFAULT_LOOK,
                ).light_direction,
                DEFAULT_LOOK.light_direction, strict=True,
        ):
            self.assertAlmostEqual(channel, live)

    def test_the_lamp_walks_home_as_the_core_lights_up(self) -> None:
        """It comes back the short way rather than snapping into place."""
        turned = SPIN_PERIOD / 3
        away = self.gap(Assembly(turned=turned).tint(
            DEFAULT_LOOK,
        ).light_direction)
        half = self.gap(Assembly(glow=0.5, turned=turned).tint(
            DEFAULT_LOOK,
        ).light_direction)

        self.assertGreater(half, away)
        self.assertLess(half, 1.0)

    def test_a_lit_core_holds_its_lamp_still(self) -> None:
        """A counter left running would say where to rush at the drop."""
        assembly = Assembly(turned=SPIN_PERIOD / 3)

        for _ in range(60):
            assembly.settle(present=True, linked=True, delta=0.016)

        self.assertEqual(assembly.turned, 0.0)

    def test_a_dropped_link_starts_the_turn_from_its_place(self) -> None:
        """The lamp leaves its place rather than arriving from nowhere."""
        assembly = Assembly()

        for _ in range(60):
            assembly.settle(present=True, linked=True, delta=0.016)

        walked = [1.0]

        for _ in range(60):
            assembly.settle(present=False, linked=False, delta=0.016)
            walked.append(self.gap(assembly.tint(DEFAULT_LOOK).light_direction))

        self.assertAlmostEqual(walked[1], 1.0, places=4)

        for standing, next_one in pairwise(walked):
            self.assertLessEqual(next_one, standing)

        self.assertLess(walked[-1], 1.0)

    def test_the_turn_is_wrapped_on_its_own_period(self) -> None:
        """Its own clock: the breath does not divide the turn."""
        assembly = Assembly()

        for _ in range(4):
            assembly.settle(present=False, linked=False, delta=SPIN_PERIOD / 2)

        self.assertLess(assembly.turned, SPIN_PERIOD)
        self.assertNotAlmostEqual(assembly.turned, assembly.elapsed)


class CaptureTestCase(unittest.TestCase):
    """The client fed by real captures, into a real viewer."""

    @staticmethod
    def build(orientation: str = '') -> tuple[Viewer, CubeCast]:
        """
        Wire a real viewer, which needs no GPU until it is attached.

        Args:
            orientation: The two faces the cube is shown by.

        Returns:
            The viewer and the client driving it.

        """
        tracker = OrientationTracker(basis=orientation_basis(orientation))
        viewer = Viewer(cube=VCube(), orientation=tracker)

        return viewer, CubeCast(viewer, tracker, orientation)

    def test_sexy_move_upright(self) -> None:
        """A sexy move done upright is played as a sexy move."""
        viewer, view = self.build('UF')

        replay(view, 'sexy-move-UF.json')

        self.assertEqual(
            [notation for notation, _ in viewer.pending],
            ['R', 'U', "R'", "U'"],
        )

    def test_sexy_move_upside_down(self) -> None:
        """A sexy move done upside down is played as a sexy move."""
        viewer, view = self.build('DF')

        replay(view, 'sexy-move-DF.json')

        self.assertEqual(
            [notation for notation, _ in viewer.pending],
            ['R', 'U', "R'", "U'"],
        )

    def test_moves_keep_the_cadence_they_arrived_at(self) -> None:
        """Every move is stamped, in the order it was heard."""
        viewer, view = self.build('UF')

        replay(view, 'sexy-move-UF.json')

        arrivals = [arrival for _, arrival in viewer.pending]

        self.assertEqual(sorted(arrivals), arrivals)

    def test_rotation_only_capture_pushes_nothing(self) -> None:
        """A capture of a pure rotation only turns the cube."""
        viewer, view = self.build('UF')

        replay(view, 'Y-UF.json')

        self.assertEqual(list(viewer.pending), [])
        self.assertIsNotNone(view.tracker)
        self.assertIsNotNone(view.tracker.reference)  # type: ignore[union-attr]


class TrackerBasisTestCase(unittest.TestCase):
    """What the client hands the tracker of cubing-algs."""

    def test_a_tracker_opened_without_orientation_applies_no_correction(
            self,
    ) -> None:
        """A window opened plain reads a gyroscope stream already canonical."""
        options = entry.build_parser({}).parse_args(['-e', ENDPOINT])

        host = entry.build_host(options)

        self.assertEqual(
            host.view.tracker.basis,  # type: ignore[union-attr]
            Quat.identity(),
        )


class FramingTestCase(unittest.TestCase):
    """The views the camera stands in, and the mirror over them."""

    def test_a_window_opens_on_the_framing_of_cubing_algs(self) -> None:
        """The demo view is the framing every window of the library opens on."""
        self.assertEqual(Framing().rotation, ROTATION)
        self.assertEqual(Framing.opened_on().rotation, ROTATION)

    def test_the_user_view_takes_the_yaw_out(self) -> None:
        """The cube is seen by F and U, nothing turning around the vertical."""
        yaw, pitch, _roll = parse_rotation(
            Framing.opened_on(USER_VIEW).rotation,
        )

        self.assertEqual(yaw, 0.0)
        self.assertGreater(pitch, 0.0)

    def test_the_mirror_is_half_a_turn_of_the_view_it_is_taken_on(
            self,
    ) -> None:
        """Appending the half turn is composing it, whatever the view says."""
        for view in (DEMO_VIEW, USER_VIEW):
            with self.subTest(view=view):
                framing = Framing.opened_on(view)
                front = parse_rotation(framing.rotation)

                framing.flip()
                behind = parse_rotation(framing.rotation)

                self.assertAlmostEqual(
                    behind[0] - front[0], math.pi,
                )
                self.assertAlmostEqual(behind[1], front[1])

    def test_the_mirror_comes_back(self) -> None:
        """The key that passes behind the cube is the one that returns."""
        framing = Framing.opened_on(mirrored=True)

        self.assertNotEqual(framing.rotation, ROTATION)

        framing.flip()

        self.assertFalse(framing.mirrored)
        self.assertEqual(framing.rotation, ROTATION)

    def test_the_mirror_writes_the_angle_it_lands_on(self) -> None:
        """A framing passed behind says where it stands, not what it added."""
        self.assertEqual(flipped('y45x-34'), 'y225x-34')
        self.assertEqual(flipped(USER_ROTATION), 'y180x-34')
        self.assertEqual(flipped('y270x-20'), 'y90x-20')

    def test_a_flipped_framing_is_never_an_empty_one(self) -> None:
        """A framing with nothing left to say would be the library default."""
        self.assertEqual(flipped('y180'), 'y0')

    def test_the_mirror_applies_to_either_view(self) -> None:
        """Watching a back and reframing asks for the back of that framing."""
        framing = Framing.opened_on(DEMO_VIEW, mirrored=True)

        framing.show(USER_VIEW)

        self.assertTrue(framing.mirrored)
        self.assertEqual(framing.rotation, flipped(USER_ROTATION))

    def test_a_typed_rotation_is_the_demo_view(self) -> None:
        """An angle typed by hand stays reachable once it has been left."""
        framing = Framing.opened_on(USER_VIEW, 'y90x-20')

        self.assertEqual(framing.rotation, USER_ROTATION)

        framing.show(DEMO_VIEW)

        self.assertEqual(framing.rotation, 'y90x-20')


class CubeCastHostTestCase(unittest.TestCase):
    """The window, and the title the stream writes in it."""

    def setUp(self) -> None:
        """Wire a host on a mocked viewer and a client."""
        self.viewer = create_autospec(Viewer, instance=True)
        self.viewer.cube = VCube()
        self.view = CubeCast(self.viewer)
        self.host = CubeCastHost(
            viewer=self.viewer, title=self.view.title, view=self.view,
        )

    def test_frame_is_drawn_between_advance_and_draw(self) -> None:
        """The host slips the assembly between the two of the viewer."""
        self.viewer.advance.return_value = solved_scene()
        self.viewer.look = DEFAULT_LOOK

        self.host.frame(0.016)

        self.viewer.advance.assert_called_once_with(0.016)
        self.viewer.frame.assert_not_called()

    def test_frame_draws_no_piece_without_a_cube(self) -> None:
        """A stream with no cube behind it leaves the core alone."""
        self.viewer.advance.return_value = solved_scene()
        self.viewer.look = DEFAULT_LOOK

        self.host.frame(0.016)

        self.assertEqual(
            self.viewer.draw.call_args.kwargs['scene'].instances, (),
        )
        self.assertEqual(
            self.viewer.draw.call_args.kwargs['look'].core_color,
            waiting_core(0.016),
        )

    def test_new_title_reaches_the_window(self) -> None:
        """What the stream says of the cube reaches the bar at the frame."""
        glfw = MagicMock()
        self.host.window = object()
        self.viewer.advance.return_value = solved_scene()
        self.viewer.look = DEFAULT_LOOK
        self.view.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}),
        )

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.frame(0.016)

        glfw.set_window_title.assert_called_once_with(
            self.host.window, f'{ WINDOW_TITLE } · GANi3',
        )

    def test_unchanged_title_is_not_written_again(self) -> None:
        """A title pushed at the cadence of the frames is written once."""
        glfw = MagicMock()
        self.host.window = object()
        self.viewer.advance.return_value = solved_scene()
        self.viewer.look = DEFAULT_LOOK
        self.view.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}),
        )

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.frame(0.016)
            self.host.frame(0.016)

        glfw.set_window_title.assert_called_once()

    def test_title_without_a_window_is_only_remembered(self) -> None:
        """A host with no window keeps the title for when it opens."""
        self.viewer.advance.return_value = solved_scene()
        self.viewer.look = DEFAULT_LOOK
        self.view.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}),
        )

        self.host.frame(0.016)

        self.assertEqual(self.host.title, f'{ WINDOW_TITLE } · GANi3')

    def test_move_key_is_not_played(self) -> None:
        """A face pressed on the keyboard never reaches the cube."""
        glfw = MagicMock()

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.on_key(self.host.window, ord('R'), 0, glfw.PRESS, 0)

        self.viewer.press.assert_not_called()

    def test_the_cube_is_turned_by_nothing_but_the_stream(self) -> None:
        """The window says it plays no move, and the library holds it."""
        self.assertFalse(self.host.moves)

    def test_viewer_key_is_still_read(self) -> None:
        """The keys of the viewer keep the meaning cubing-algs gives them."""
        glfw = MagicMock()
        glfw.KEY_SPACE = ord(' ')

        with patch.dict(sys.modules, {'glfw': glfw}):
            answered = self.host.on_viewer_key(ord(' '))

        self.assertTrue(answered)
        self.viewer.reset_camera.assert_called_once_with()

    def test_backspace_does_not_rebuild_the_cube(self) -> None:
        """A cube put back together is a state the stream never sent."""
        glfw = MagicMock()
        glfw.KEY_BACKSPACE = BACKSPACE

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.on_key(self.host.window, BACKSPACE, 0, glfw.PRESS, 0)

        self.viewer.reset_cube.assert_not_called()

    def test_a_view_key_reframes_the_cube(self) -> None:
        """A view key writes the framing into the viewer and rebuilds it."""
        glfw = MagicMock()
        glfw.KEY_1 = ord('1')
        glfw.KEY_2 = ord('2')

        with patch.dict(sys.modules, {'glfw': glfw}):
            answered = self.host.on_viewer_key(ord('2'))

        self.assertTrue(answered)
        self.assertEqual(self.host.framing.view, USER_VIEW)
        self.assertEqual(self.viewer.rotation, USER_ROTATION)
        self.viewer.reset_camera.assert_called_once_with()

    def test_the_mirror_key_passes_behind_the_cube(self) -> None:
        """The third key flips the view the camera already stands in."""
        glfw = MagicMock()
        glfw.KEY_3 = ord('3')

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.on_viewer_key(ord('3'))

        self.assertTrue(self.host.framing.mirrored)
        self.assertEqual(self.viewer.rotation, flipped(ROTATION))

    def test_a_view_key_is_not_played_as_a_move(self) -> None:
        """A digit reaches the camera and never the cube."""
        glfw = MagicMock()
        glfw.KEY_1 = ord('1')

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.on_viewer_key(ord('1'))

        self.viewer.press.assert_not_called()

    def test_shortcuts_name_the_views(self) -> None:
        """The list written when the window opens holds the three keys."""
        for key in ('  1  ', '  2  ', '  3  '):
            with self.subTest(key=key):
                self.assertIn(key, self.host.shortcuts)

    def test_shortcuts_leave_the_moves_out(self) -> None:
        """The list written when the window opens holds no move."""
        self.assertNotIn('Turn a face', self.host.shortcuts)
        self.assertNotIn('Backspace', self.host.shortcuts)
        self.assertIn('Esc, Q', self.host.shortcuts)


class ManagedWindowTestCase(unittest.TestCase):
    """A window opened for another process to show, hide and close."""

    def setUp(self) -> None:
        """Wire a managed host on a mocked viewer and a client."""
        self.viewer = create_autospec(Viewer, instance=True)
        self.viewer.cube = VCube()
        self.view = CubeCast(self.viewer)
        self.host = CubeCastHost(
            viewer=self.viewer,
            title=self.view.title,
            view=self.view,
            managed=True,
        )

    def test_a_managed_window_opens_hidden(self) -> None:
        """There is nothing else it could open as: nobody asked yet."""
        self.assertFalse(self.host.visible)

    def test_a_window_of_its_own_opens_shown(self) -> None:
        """A cube-cast typed into a terminal is a window that is there."""
        host = CubeCastHost(
            viewer=self.viewer, title=self.view.title, view=self.view,
        )

        self.assertTrue(host.visible)

    def test_an_order_is_written_down_and_not_obeyed(self) -> None:
        """A window belongs to the thread that opened it."""
        self.host.order(SHOW_ORDER)

        self.assertEqual(self.host.wanted, SHOW_ORDER)
        self.assertFalse(self.host.visible)

    def test_an_order_is_obeyed_at_the_next_turn_of_the_loop(self) -> None:
        """What the reader wrote down is what the loop does."""
        glfw = MagicMock()
        self.host.order(SHOW_ORDER)

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.obey()

        self.assertTrue(self.host.visible)
        self.assertEqual(self.host.wanted, '')

    def test_the_window_is_put_away_on_the_hide_order(self) -> None:
        """Nothing is given back: it goes on reading the stream."""
        glfw = MagicMock()

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.order(SHOW_ORDER)
            self.host.obey()

            self.host.order(HIDE_ORDER)
            self.host.obey()

        self.assertFalse(self.host.visible)

    def test_the_close_order_ends_the_window(self) -> None:
        """The process that opened it is the one saying it is over."""
        with patch.object(GlfwHost, 'on_close') as closing:
            self.host.order(CLOSE_ORDER)
            self.host.obey()

        closing.assert_called_once_with()

    def test_an_order_nobody_knows_is_ignored(self) -> None:
        """A client ignores what it does not know, orders included."""
        glfw = MagicMock()

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.order('explode')
            self.host.obey()

        self.assertFalse(self.host.visible)
        glfw.show_window.assert_not_called()

    def test_the_last_order_is_the_one_that_stands(self) -> None:
        """They answer one question, so the last answer is the answer."""
        glfw = MagicMock()

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.order(SHOW_ORDER)
            self.host.order(HIDE_ORDER)
            self.host.obey()

        self.assertFalse(self.host.visible)

    def test_a_frame_reads_the_orders_first(self) -> None:
        """A window shown is shown on the very frame it was asked for."""
        with (
            patch.object(GlfwHost, 'tick') as ticked,
            patch.object(self.host, 'obey') as obeyed,
        ):
            self.host.tick()

        obeyed.assert_called_once_with()
        ticked.assert_called_once_with()

    def test_a_hidden_turn_reads_the_orders_too(self) -> None:
        """A window nobody is shown is the one waiting to be shown."""
        with (
            patch.object(GlfwHost, 'idle') as idled,
            patch.object(self.host, 'obey') as obeyed,
        ):
            self.host.idle()

        obeyed.assert_called_once_with()
        idled.assert_called_once_with()

    def test_the_closing_keys_are_not_a_managed_window_to_answer(
            self,
    ) -> None:
        """Whoever shows the window is the one holding whether it is up."""
        glfw = MagicMock()

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.show()
            self.host.on_close()

        self.assertTrue(self.host.visible)
        glfw.set_window_should_close.assert_not_called()

    def test_the_closing_keys_still_close_a_window_of_its_own(self) -> None:
        """A window nobody drives is a window its own keys close."""
        glfw = MagicMock()
        host = CubeCastHost(
            viewer=self.viewer, title=self.view.title, view=self.view,
        )

        with patch.dict(sys.modules, {'glfw': glfw}):
            host.on_close()

        glfw.set_window_should_close.assert_called_once()

    def test_the_list_offers_no_key_the_window_refuses(self) -> None:
        """A list describing a window other than the one open is a wrong one."""
        self.assertNotIn(HELP_CLOSE, self.host.shortcuts)
        self.assertIn(HELP_CLOSE, VIEWER_SHORTCUTS)

    def test_the_closing_line_is_the_only_one_left_out(self) -> None:
        """The keys are the ones of the library, whoever shows the window."""
        managed = MANAGED_SHORTCUTS.splitlines()
        plain = VIEWER_SHORTCUTS.splitlines()

        left_out = [line for line in plain if line not in managed]

        self.assertEqual(len(left_out), 1)
        self.assertTrue(left_out[0].startswith(f'  { HELP_CLOSE }'))


class ShortcutsTestCase(unittest.TestCase):
    """The list a window prints, against the window it opens."""

    def setUp(self) -> None:
        """Wire a host on a mocked viewer and a client."""
        self.viewer = create_autospec(Viewer, instance=True)
        self.viewer.cube = VCube()
        self.viewer.look = Look()
        self.view = CubeCast(self.viewer)
        self.host = CubeCastHost(
            viewer=self.viewer,
            title=self.view.title,
            view=self.view,
            transparent=True,
        )

    def test_every_inherited_line_is_the_one_of_the_library(self) -> None:
        """A line this window did not add is a line it did not write."""
        added = {'1', '2', '3'}
        inherited = [
            line
            for line in self.host.shortcuts.splitlines()[1:]
            if line.split()[0] not in added
        ]

        self.assertEqual(
            inherited,
            viewer_help(moves=False).splitlines()[1:],
        )

    def test_the_window_is_named_after_the_client(self) -> None:
        """The heading is the one thing of the list this client owns."""
        self.assertEqual(self.host.shortcuts.splitlines()[0], 'cube-cast')

    def test_the_view_keys_are_offered(self) -> None:
        """What this window adds to the library is in the list it prints."""
        for keys in ('1', '2', '3'):
            with self.subTest(keys=keys):
                self.assertNotIn(f'  { keys } ', VIEWER_HELP)
                self.assertIn(f'  { keys } ', self.host.shortcuts)

    def test_the_mouse_reads_the_same_in_both_modes(self) -> None:
        """One list of shortcuts, a mode changing nothing of the mouse."""
        opaque = CubeCastHost(
            viewer=self.viewer, title=self.view.title, view=self.view,
        )

        self.assertEqual(self.host.shortcuts, opaque.shortcuts)

    def test_no_move_is_offered_by_a_cube_turned_elsewhere(self) -> None:
        """The keys turning a cube are not in the list of this window."""
        for line in ('R U F L D B', 'Backspace'):
            with self.subTest(line=line):
                self.assertIn(line, VIEWER_HELP)
                self.assertNotIn(line, self.host.shortcuts)

    def test_the_list_is_what_the_window_prints(self) -> None:
        """A list written here is the one the host hands to its loop."""
        self.assertEqual(self.host.help, self.host.shortcuts)


class CadenceTestCase(unittest.TestCase):
    """What the command line settles of how fast the cube answers."""

    def test_parse_beat(self) -> None:
        """A beat is typed in the milliseconds a hand is talked about in."""
        self.assertAlmostEqual(entry.parse_beat('100'), 0.1)

    def test_beat_rejects_what_no_turn_happens_in(self) -> None:
        """A turn given no time at all is one nothing could play."""
        for value in ('0', '-40', '0.5', 'quick', ''):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                entry.build_parser({}).parse_args(['-e', ENDPOINT, '-b', value])

    def test_parse_lead(self) -> None:
        """A lead of nothing is a stream nothing travels through."""
        self.assertAlmostEqual(entry.parse_lead('50'), 0.05)
        self.assertAlmostEqual(entry.parse_lead('0'), 0.0)

    def test_lead_rejects_what_is_not_a_duration(self) -> None:
        """An argument naming no delay stops the client."""
        for value in ('-10', 'late', '1.5', ''):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                entry.build_parser({}).parse_args(['-e', ENDPOINT, '-l', value])

    def test_build_host_cadences_the_cube(self) -> None:
        """The beat reaches the animation, and the lead reaches the clock."""
        options = entry.build_parser({}).parse_args(
            ['-e', ENDPOINT, '-b', '80', '-l', '30'],
        )

        host = entry.build_host(options)

        self.assertAlmostEqual(host.viewer.duration, 0.08)
        self.assertAlmostEqual(host.view.clock.lead, 0.03)

    def test_build_host_keeps_a_turn_to_look_at(self) -> None:
        """
        A measured delay may never eat the whole of the beat.

        What was typed is another matter: a lead of its own is an answer
        about this link, and asking for a cube that snaps is a thing one
        may want.
        """
        options = entry.build_parser({}).parse_args(
            ['-e', ENDPOINT, '-b', '100', '-l', '10'],
        )
        wide = entry.build_parser({}).parse_args(
            ['-e', ENDPOINT, '-b', '100', '-l', '90'],
        )

        self.assertAlmostEqual(
            entry.build_host(options).view.clock.ceiling, 0.075,
        )
        self.assertAlmostEqual(
            entry.build_host(wide).view.clock.ceiling, 0.09,
        )


class MainTestCase(unittest.TestCase):
    """The command line of the client, and what it assembles."""

    def test_help_is_formatted(self) -> None:
        """The help of the client is written the way term-timer writes it."""
        help_text = entry.build_parser({}).format_help()

        self.assertIn('Usage:', help_text)
        self.assertIn('Connect to this ZeroMQ endpoint', help_text)
        self.assertIn('Options:', help_text)

    def test_parse_size(self) -> None:
        """A size is read whatever the case of its separator."""
        self.assertEqual(entry.parse_size('1024X768'), (1024, 768))

    def test_parse_size_rejects_what_is_not_one(self) -> None:
        """An argument naming no size stops the client."""
        for value in ('1024', '1024x', 'wide x tall', ''):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                entry.build_parser({}).parse_args(['-e', ENDPOINT, '-w', value])

    def test_rotation_rejects_what_is_not_one(self) -> None:
        """A rotation cubing-algs would silently drop stops the client."""
        for value in ('y', '45', 'y45x', 'top', 'y45 x-34'):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                entry.build_parser({}).parse_args(['-e', ENDPOINT, '-r', value])

    def test_endpoint_is_required(self) -> None:
        """A client with no endpoint has nothing to listen to."""
        with self.assertRaises(SystemExit):
            entry.build_parser({}).parse_args([])

    def test_endpoint_ipc_path_expanded(self) -> None:
        """A tilde on the command line is the home the publisher binds."""
        options = entry.build_parser({}).parse_args(
            ['-e', 'ipc://~/.term_timer/cube.ipc'],
        )

        self.assertEqual(
            options.endpoint,
            f'ipc://{ Path.home() }/.term_timer/cube.ipc',
        )

    def test_endpoint_rejects_what_is_not_one(self) -> None:
        """An endpoint naming no transport stops the client."""
        for value in ('cube.ipc', '~/.term_timer/cube.ipc', 'ipc://', ''):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                entry.build_parser({}).parse_args(['-e', value])

    def test_build_host(self) -> None:
        """The options of the client reach the viewer it builds."""
        options = entry.build_parser({}).parse_args(
            [
                '-e', ENDPOINT, '-o', 'DF', '-w', '640x480',
                '-m', 'oll', '-r', 'y90x-20',
            ],
        )

        host = entry.build_host(options)

        self.assertEqual(host.view.orientation, 'DF')
        self.assertEqual(host.viewer.window_size, (640, 480))
        self.assertEqual(host.viewer.mode, 'oll')
        self.assertEqual(host.viewer.rotation, 'y90x-20')
        self.assertIs(host.viewer.orientation, host.view.tracker)
        self.assertEqual(host.title, f'{ WINDOW_TITLE } · offline')
        self.assertTrue(host.msaa)
        self.assertEqual(
            host.view.tracker.basis,  # type: ignore[union-attr]
            orientation_basis('DF'),
        )

    def test_build_host_without_antialiasing(self) -> None:
        """A cube asked for aliased is drawn into the window itself."""
        options = entry.build_parser({}).parse_args(
            ['-e', ENDPOINT, '-t', '--no-msaa'],
        )

        host = entry.build_host(options)

        self.assertTrue(host.transparent)
        self.assertFalse(host.msaa)
        self.assertFalse(host.offscreen)

    def test_build_host_deaf_to_the_gyroscope(self) -> None:
        """A window asked to ignore the gyroscope holds no tracker."""
        options = entry.build_parser({}).parse_args(
            ['-e', ENDPOINT, '-g'],
        )

        host = entry.build_host(options)

        self.assertIsNone(host.view.tracker)
        self.assertIsNone(host.viewer.orientation)

    def test_configuration_carries_the_defaults(self) -> None:
        """What term-timer was configured with is what the client opens on."""
        options = entry.build_parser(CONFIG).parse_args([])

        self.assertEqual(options.endpoint, ENDPOINT)
        self.assertEqual(options.orientation, 'DF')
        self.assertEqual(options.palette, 'dracula')

    def test_command_line_wins_over_the_configuration(self) -> None:
        """An option typed is what the window opens on, configured or not."""
        options = entry.build_parser(CONFIG).parse_args(
            ['-e', 'tcp://127.0.0.1:5334', '-o', 'UF', '-p', 'neon'],
        )

        self.assertEqual(options.endpoint, 'tcp://127.0.0.1:5334')
        self.assertEqual(options.orientation, 'UF')
        self.assertEqual(options.palette, 'neon')

    def test_configured_endpoint_is_the_first_one_bound(self) -> None:
        """A publisher binding several endpoints is connected to on one."""
        options = entry.build_parser(
            {
                'publisher': {
                    'endpoints': [
                        'cube.ipc',
                        'ipc://~/.term_timer/cube.ipc',
                        ENDPOINT,
                    ],
                },
            },
        ).parse_args([])

        self.assertEqual(
            options.endpoint,
            f'ipc://{ Path.home() }/.term_timer/cube.ipc',
        )

    def test_configured_taste_unknown_here_is_dropped(self) -> None:
        """A palette this client cannot draw never stops the window."""
        with self.assertLogs('term_timer_clients.viewer.main', 'WARNING'):
            options = entry.build_parser(
                {
                    'publisher': {'endpoints': [ENDPOINT]},
                    'cube': {'orientation': 'XY', 'palette': 'sepia'},
                },
            ).parse_args([])

        self.assertEqual(options.orientation, '')
        self.assertEqual(options.palette, '')

    def test_configured_help_names_the_defaults(self) -> None:
        """The help of a configured client shows what it will open on."""
        help_text = entry.build_parser(CONFIG).format_help()

        self.assertIn(ENDPOINT, help_text)
        self.assertIn('Default: DF.', help_text)
        self.assertIn('Default: dracula.', help_text)

    def test_main_reads_the_stream_while_the_window_is_open(self) -> None:
        """The stream is read from before the window opens to after."""
        host = MagicMock()
        stream = MagicMock()

        self.assertEqual(run_main(host, stream), 0)

        stream.start.assert_called_once_with(host.view.dispatch)
        host.run.assert_called_once_with()
        stream.stop.assert_called_once_with()

    def test_main_without_a_window(self) -> None:
        """A window that cannot open is reported, not raised."""
        host = MagicMock()
        host.run.side_effect = GLContextError('no context')
        stream = MagicMock()

        with self.assertLogs('term_timer_clients.viewer.main', 'ERROR'):
            self.assertEqual(run_main(host, stream), 1)

        stream.stop.assert_called_once_with()

    def test_main_hears_the_end_of_the_stream(self) -> None:
        """A window takes the one message of the session plane it needs."""
        with (
            patch.object(sys, 'argv', ['cube-cast', '-e', ENDPOINT]),
            patch.object(entry, 'load_config', return_value={}),
            patch.object(entry, 'build_host', return_value=MagicMock()),
            patch.object(entry, 'EventStream') as stream,
        ):
            self.assertEqual(entry.main(), 0)

        stream.assert_called_once_with(ENDPOINT, entry.PREFIXES)

        self.assertIn(SESSION_END_TOPIC, entry.PREFIXES)
        self.assertNotIn(SESSION_PREFIX, entry.PREFIXES)

    def test_main_interrupted(self) -> None:
        """An interruption from the keyboard closes the stream."""
        host = MagicMock()
        host.run.side_effect = KeyboardInterrupt
        stream = MagicMock()

        self.assertEqual(run_main(host, stream), 0)

        stream.stop.assert_called_once_with()


class ManagedOptionTestCase(unittest.TestCase):
    """The window opened for another process to show."""

    def test_build_host_managed(self) -> None:
        """A window opened for somebody else to show opens hidden."""
        options = entry.build_parser({}).parse_args(
            ['-e', ENDPOINT, '--managed'],
        )

        host = entry.build_host(options)

        self.assertTrue(host.managed)
        self.assertFalse(host.visible)

    def test_main_takes_its_orders_on_the_standard_input(self) -> None:
        """The one channel a process is handed by whoever started it."""
        host = MagicMock()
        stream = MagicMock()

        with patch.object(entry, 'OrderReader') as reader:
            self.assertEqual(run_main(host, stream, ['--managed']), 0)

        reader.assert_called_once_with(sys.stdin, host.order)
        reader.return_value.start.assert_called_once_with()
        reader.return_value.stop.assert_called_once_with()

    def test_main_takes_no_orders_of_its_own(self) -> None:
        """A window typed into a terminal answers a keyboard, not a pipe."""
        with patch.object(entry, 'OrderReader') as reader:
            self.assertEqual(run_main(MagicMock(), MagicMock()), 0)

        reader.assert_not_called()

    def test_main_gives_the_orders_back_however_it_ends(self) -> None:
        """A reader left on a pipe is a thread nothing can ever end."""
        host = MagicMock()
        host.run.side_effect = KeyboardInterrupt

        with patch.object(entry, 'OrderReader') as reader:
            self.assertEqual(run_main(host, MagicMock(), ['--managed']), 0)

        reader.return_value.stop.assert_called_once_with()


class ViewOptionTestCase(unittest.TestCase):
    """The view a window opens on, and the angle it is written with."""

    def test_build_host_opens_on_the_view_it_was_given(self) -> None:
        """The view named on the command line is what the window opens on."""
        options = entry.build_parser({}).parse_args(
            ['-e', ENDPOINT, '-v', USER_VIEW],
        )

        host = entry.build_host(options)

        self.assertEqual(host.framing.view, USER_VIEW)
        self.assertEqual(host.viewer.rotation, USER_ROTATION)

    def test_build_host_opens_behind_the_cube(self) -> None:
        """A window asked for the mirror opens on the view already flipped."""
        options = entry.build_parser({}).parse_args(
            ['-e', ENDPOINT, '-v', USER_VIEW, '--mirror'],
        )

        host = entry.build_host(options)

        self.assertTrue(host.framing.mirrored)
        self.assertEqual(host.viewer.rotation, flipped(USER_ROTATION))

    def test_a_typed_rotation_stays_the_view_it_opened_on(self) -> None:
        """--rotation is the demo view, and the first key comes back to it."""
        options = entry.build_parser({}).parse_args(
            ['-e', ENDPOINT, '-r', 'y90x-20', '-v', USER_VIEW],
        )

        host = entry.build_host(options)

        self.assertEqual(host.viewer.rotation, USER_ROTATION)

        host.framing.show(DEMO_VIEW)

        self.assertEqual(host.framing.rotation, 'y90x-20')

    def test_view_rejects_what_is_not_one(self) -> None:
        """A view this client does not stand in stops the client."""
        with self.assertRaises(SystemExit):
            entry.build_parser({}).parse_args(['-e', ENDPOINT, '-v', 'back'])
