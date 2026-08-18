"""
Tests for the ``cube-view`` client.

Nothing here opens a window: the client only translates a stream into
calls on a viewer, so a mocked one - or a real one, which needs no GPU
until a stage is attached to it - is enough. The captures of
``tests/replays/gan_gen2/`` play the part of the cube.
"""
import json
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import create_autospec
from unittest.mock import patch

from cubing_algs.display.gl import SENSOR_BASIS
from cubing_algs.display.gl import Look
from cubing_algs.display.gl import OrientationTracker
from cubing_algs.display.gl import Viewer
from cubing_algs.display.gl.context import GLContextError
from cubing_algs.display.gl.host import GlfwHost
from cubing_algs.vcube import VCube

from term_timer_clients.tests.fixtures import envelope
from term_timer_clients.viewer import host as window
from term_timer_clients.viewer import main as entry
from term_timer_clients.viewer.client import WINDOW_TITLE
from term_timer_clients.viewer.client import CubeView
from term_timer_clients.viewer.host import TRANSPARENT
from term_timer_clients.viewer.host import CubeViewHost

REPLAYS = Path(__file__).parent / 'replays' / 'gan_gen2'

ENDPOINT = 'tcp://127.0.0.1:5333'

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


# Topic of every driver event the viewer listens to
TOPICS = {
    'facelets': 'cube.facelets',
    'move': 'cube.move',
    'move_history': 'cube.history',
    'gyro': 'cube.gyro',
    'hardware': 'cube.hardware',
    'battery': 'cube.battery',
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


def replay(view: CubeView, name: str) -> None:
    """
    Play a capture through the client, event by event.

    Args:
        view: The client the capture is played into.
        name: Name of the capture file.

    """
    for event in capture(name):
        topic = TOPICS.get(event['event'])

        if topic is None:
            continue

        view.dispatch(
            envelope(
                topic,
                {
                    key: value
                    for key, value in event.items()
                    if key != 'event'
                },
            ),
        )


def run_main(host: MagicMock, stream: MagicMock) -> int:
    """
    Run the entry point on a mocked window and a mocked stream.

    Args:
        host: The host standing in for the window.
        stream: The object standing in for the subscription.

    Returns:
        The exit code of the entry point.

    """
    argv = ['cube-view', '-e', ENDPOINT]

    with (
        patch.object(sys, 'argv', argv),
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
        self.tracker = OrientationTracker(basis=SENSOR_BASIS)
        self.view = CubeView(self.viewer, self.tracker)


class EnvelopeTestCase(ClientTestCase):
    """What the client reads before the payload of a message."""

    def test_unknown_protocol_is_ignored(self) -> None:
        """A message of another protocol version does nothing."""
        self.view.dispatch(envelope('cube.move', {'move': 'R'}, version=2))

        self.viewer.push.assert_not_called()

    def test_unknown_protocol_is_reported_once(self) -> None:
        """A foreign stream is named once, not on every message."""
        with self.assertLogs(
                'term_timer_clients.viewer.client', 'WARNING',
        ) as logs:
            self.view.dispatch(envelope('cube.move', version=2))
            self.view.dispatch(envelope('cube.move', version=2))

        self.assertEqual(len(logs.output), 1)

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
        view = CubeView(self.viewer, self.tracker, 'DF')
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

        self.viewer.push.assert_called_once_with("R'")

    def test_history_is_pushed_too(self) -> None:
        """A move caught up on is played like any other."""
        self.view.dispatch(envelope('cube.history', {'move': 'U2'}))

        self.viewer.push.assert_called_once_with('U2')

    def test_move_is_read_in_the_display_frame(self) -> None:
        """A move is turned the way the cube is looked at."""
        view = CubeView(self.viewer, self.tracker, 'DF')

        view.dispatch(envelope('cube.move', {'move': 'L'}))

        self.viewer.push.assert_called_once_with('R')

    def test_empty_move_is_ignored(self) -> None:
        """A message carrying no move plays nothing."""
        self.view.dispatch(envelope('cube.move', {'move': ''}))
        self.view.dispatch(envelope('cube.move', {'serial': 3}))

        self.viewer.push.assert_not_called()

    def test_untranslatable_move_is_pushed_as_it_is(self) -> None:
        """A notation nothing can read is handed over untouched."""
        view = CubeView(self.viewer, self.tracker, 'DF')

        view.dispatch(envelope('cube.move', {'move': '[R,'}))

        self.viewer.push.assert_called_once_with('[R,')


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
        view = CubeView(self.viewer)

        view.dispatch(
            envelope(
                'cube.gyro',
                {'quaternion': {'w': 1.0, 'x': 0.0, 'y': 0.0, 'z': 0.0}},
            ),
        )

        self.assertIsNone(view.tracker)

    def test_title_names_the_cube(self) -> None:
        """The hardware and the battery are written in the title."""
        self.assertEqual(self.view.title, WINDOW_TITLE)

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

    def test_nameless_hardware_is_ignored(self) -> None:
        """What says nothing about the cube leaves the title alone."""
        self.view.dispatch(envelope('cube.hardware', {'hardware_name': ''}))
        self.view.dispatch(envelope('cube.battery', {'level': 'high'}))

        self.assertEqual(self.view.title, WINDOW_TITLE)


class CaptureTestCase(unittest.TestCase):
    """The client fed by real captures, into a real viewer."""

    @staticmethod
    def build(orientation: str = '') -> tuple[Viewer, CubeView]:
        """
        Wire a real viewer, which needs no GPU until it is attached.

        Args:
            orientation: The two faces the cube is shown by.

        Returns:
            The viewer and the client driving it.

        """
        tracker = OrientationTracker(basis=SENSOR_BASIS)
        viewer = Viewer(cube=VCube(), orientation=tracker)

        return viewer, CubeView(viewer, tracker, orientation)

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


class CubeViewHostTestCase(unittest.TestCase):
    """The window, and the title the stream writes in it."""

    def setUp(self) -> None:
        """Wire a host on a mocked viewer and a client."""
        self.viewer = create_autospec(Viewer, instance=True)
        self.viewer.cube = VCube()
        self.view = CubeView(self.viewer)
        self.host = CubeViewHost(
            viewer=self.viewer, title=self.view.title, view=self.view,
        )

    def test_frame_is_drawn_by_the_viewer(self) -> None:
        """The frame of the host is the frame of the viewer."""
        self.host.frame(0.016)

        self.viewer.frame.assert_called_once_with(0.016)

    def test_unchanged_title_is_not_written(self) -> None:
        """A title that did not move is not written again."""
        glfw = MagicMock()
        self.host.window = object()

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.retitle()

        glfw.set_window_title.assert_not_called()

    def test_new_title_reaches_the_window(self) -> None:
        """A title the stream changed reaches the window bar."""
        glfw = MagicMock()
        self.host.window = object()
        self.view.hardware = 'GANi3'

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.retitle()

        glfw.set_window_title.assert_called_once_with(
            self.host.window, f'{ WINDOW_TITLE } · GANi3',
        )

    def test_title_without_a_window_is_only_remembered(self) -> None:
        """A host with no window keeps the title for when it opens."""
        self.view.hardware = 'GANi3'

        self.host.retitle()

        self.assertEqual(self.host.title, f'{ WINDOW_TITLE } · GANi3')

    def test_move_key_is_not_played(self) -> None:
        """A face pressed on the keyboard never reaches the cube."""
        glfw = MagicMock()

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.on_key(self.host.window, ord('R'), 0, glfw.PRESS, 0)

        self.viewer.press.assert_not_called()

    def test_move_key_is_answered(self) -> None:
        """A key the window does not use is claimed rather than played."""
        glfw = MagicMock()

        with patch.dict(sys.modules, {'glfw': glfw}):
            answered = self.host.on_viewer_key(ord('R'))

        self.assertTrue(answered)

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
            answered = self.host.on_viewer_key(BACKSPACE)

        self.assertTrue(answered)
        self.viewer.reset_cube.assert_not_called()

    def test_shortcuts_leave_the_moves_out(self) -> None:
        """The list written when the window opens holds no move."""
        self.assertNotIn('Turn a face', self.host.shortcuts)
        self.assertNotIn('Backspace', self.host.shortcuts)
        self.assertIn('Esc, Q', self.host.shortcuts)


class CubeViewHostWindowCase(unittest.TestCase):
    """What every test of the window is wired on, and no test."""

    def setUp(self) -> None:
        """Wire a transparent host on a mocked viewer and a client."""
        self.viewer = create_autospec(Viewer, instance=True)
        self.viewer.cube = VCube()
        self.viewer.look = Look()
        self.view = CubeView(self.viewer)
        self.host = CubeViewHost(
            viewer=self.viewer,
            title=self.view.title,
            view=self.view,
            transparent=True,
        )

    def opaque_host(self) -> CubeViewHost:
        """
        Build the same host, on a window of the ordinary kind.

        Returns:
            A host drawing into a decorated, opaque window.

        """
        return CubeViewHost(
            viewer=self.viewer, title=self.view.title, view=self.view,
        )


class CubeViewHostTransparentTestCase(CubeViewHostWindowCase):
    """The cube laid on the desktop, and what it is drawn through."""

    def test_window_is_asked_to_let_the_desktop_through(self) -> None:
        """The three hints are posted before the window is created."""
        glfw = MagicMock()
        stage = MagicMock()

        with (
            patch.dict(sys.modules, {'glfw': glfw}),
            patch.object(window, 'has_glfw', return_value=True),
            patch.object(GlfwHost, 'open', return_value=stage),
        ):
            self.host.open()

        hints = {call.args[0] for call in glfw.window_hint.call_args_list}

        self.assertEqual(
            hints,
            {
                glfw.TRANSPARENT_FRAMEBUFFER,
                glfw.DECORATED,
                glfw.FLOATING,
            },
        )
        self.assertEqual(stage.background, TRANSPARENT)

    def test_window_asks_for_no_samples_of_its_own(self) -> None:
        """A multisampled window gets the transparency refused."""
        glfw = MagicMock()
        stage = MagicMock()
        asked = []

        def opened() -> MagicMock:
            asked.append(self.viewer.look.samples)
            return stage

        with (
            patch.dict(sys.modules, {'glfw': glfw}),
            patch.object(window, 'has_glfw', return_value=True),
            patch.object(GlfwHost, 'open', side_effect=opened),
        ):
            self.host.open()

        self.assertEqual(asked, [0])

        # Put back at once: the screenshot and the report read it too.
        self.assertEqual(self.viewer.look.samples, Look().samples)

    def test_refused_transparency_is_named(self) -> None:
        """A compositor saying no leaves the cube on the viewer grey."""
        glfw = MagicMock()
        glfw.get_window_attrib.return_value = 0
        stage = MagicMock()
        stage.background = 'untouched'

        with (
            patch.dict(sys.modules, {'glfw': glfw}),
            patch.object(window, 'has_glfw', return_value=True),
            patch.object(GlfwHost, 'open', return_value=stage),
            self.assertLogs('term_timer_clients.viewer.host', 'WARNING'),
        ):
            self.host.open()

        self.assertEqual(stage.background, 'untouched')

    def test_a_missing_glfw_is_left_to_the_parent(self) -> None:
        """The extra to install is named by cubing-algs, not here."""
        with (
            patch.object(window, 'has_glfw', return_value=False),
            patch.object(GlfwHost, 'open') as opened,
        ):
            self.host.open()

        opened.assert_called_once_with()

    def test_target_is_built_once_for_a_size(self) -> None:
        """The offscreen target is kept until the window changes size."""
        stage = MagicMock()
        stage.size = (200, 200)
        self.viewer.require_stage.return_value = stage
        target = MagicMock()
        target.size = (200, 200)

        with patch.object(window, 'OffscreenTarget') as offscreen:
            offscreen.create.return_value = target

            self.host.refresh_target()
            self.host.refresh_target()

        offscreen.create.assert_called_once_with(
            stage.context, (200, 200), Look().samples,
        )
        self.assertIs(stage.target, target.framebuffer)

    def test_target_follows_a_resized_window(self) -> None:
        """A window of another size is drawn into another target."""
        stage = MagicMock()
        stage.size = (400, 400)
        self.viewer.require_stage.return_value = stage
        target = MagicMock()
        target.size = (200, 200)
        self.host.target = target

        with patch.object(window, 'OffscreenTarget') as offscreen:
            self.host.refresh_target()

        target.release.assert_called_once_with()
        offscreen.create.assert_called_once()

    def test_an_opaque_window_draws_into_itself(self) -> None:
        """No detour is taken when the window holds its own samples."""
        host = self.opaque_host()

        with patch.object(window, 'OffscreenTarget') as offscreen:
            host.refresh_target()

        offscreen.create.assert_not_called()
        self.assertIsNone(host.target)

    def test_frame_lands_in_the_window(self) -> None:
        """The frame is resolved, and then copied to the screen."""
        stage = MagicMock()
        self.viewer.require_stage.return_value = stage
        target = MagicMock()
        self.host.target = target

        self.host.resolve()

        stage.context.copy_framebuffer.assert_any_call(
            target.resolved, target.framebuffer,
        )
        stage.context.copy_framebuffer.assert_any_call(
            stage.context.screen, target.resolved,
        )

    def test_nothing_is_resolved_without_a_target(self) -> None:
        """A window drawn into directly has nothing to copy."""
        self.host.resolve()

        self.viewer.require_stage.assert_not_called()

    def test_close_gives_the_target_back(self) -> None:
        """The target is released while the context is still alive."""
        target = MagicMock()
        self.host.target = target

        self.host.close()

        target.release.assert_called_once_with()
        self.assertIsNone(self.host.target)


class CubeViewHostMouseTestCase(CubeViewHostWindowCase):
    """What the mouse does, and what it does the same in both modes."""

    def test_the_mouse_reads_the_same_in_both_modes(self) -> None:
        """One list of shortcuts, a mode changing nothing of the mouse."""
        self.assertEqual(self.host.shortcuts, self.opaque_host().shortcuts)
        self.assertIn('Ctrl drag', self.host.shortcuts)
        self.assertIn('Drag             Orbit', self.host.shortcuts)

    def test_control_takes_hold_of_the_window(self) -> None:
        """Ctrl over a drag carries the window instead of the cube."""
        glfw = mouse_glfw()

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.on_mouse_button(None, LEFT_BUTTON, PRESS, CONTROL)

        self.assertTrue(self.host.carrying)
        self.assertFalse(self.host.dragging)
        self.assertEqual(self.host.anchor, (5.0, 7.0))

    def test_a_plain_drag_orbits_a_window_with_no_bar(self) -> None:
        """The gesture the viewer is made of is what a mode may not move."""
        glfw = mouse_glfw()

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.on_mouse_button(None, LEFT_BUTTON, PRESS, 0)

        self.assertTrue(self.host.dragging)
        self.assertFalse(self.host.carrying)

    def test_an_opaque_window_is_carried_the_same_way(self) -> None:
        """A window keeping its bar answers the carry all the same."""
        host = self.opaque_host()
        glfw = mouse_glfw()

        with patch.dict(sys.modules, {'glfw': glfw}):
            host.on_mouse_button(None, LEFT_BUTTON, PRESS, CONTROL)

        self.assertTrue(host.carrying)
        self.assertFalse(host.dragging)

    def test_an_opaque_window_orbits_on_the_left(self) -> None:
        """A decorated window keeps the buttons cubing-algs gives it."""
        host = self.opaque_host()
        glfw = mouse_glfw()

        with patch.dict(sys.modules, {'glfw': glfw}):
            host.on_mouse_button(None, LEFT_BUTTON, PRESS, 0)

        self.assertTrue(host.dragging)
        self.assertFalse(host.carrying)

    def test_the_carry_ends_with_the_button(self) -> None:
        """Ctrl let go halfway through carries the window all the same."""
        glfw = mouse_glfw()
        self.host.carrying = True

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.on_mouse_button(None, LEFT_BUTTON, RELEASE, 0)

        self.assertFalse(self.host.carrying)
        self.assertFalse(self.host.dragging)

    def test_another_button_is_left_to_the_parent(self) -> None:
        """The right button does here what cubing-algs does with it."""
        glfw = mouse_glfw()

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.on_mouse_button(None, RIGHT_BUTTON, PRESS, 0)

        self.assertFalse(self.host.dragging)
        self.assertFalse(self.host.carrying)

    def test_window_follows_the_cursor_it_is_held_by(self) -> None:
        """The window moves by what the cursor gained on its anchor."""
        glfw = mouse_glfw()
        glfw.get_window_pos.return_value = (100, 100)
        self.host.carrying = True
        self.host.anchor = (10.0, 10.0)

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.on_cursor(None, 30.0, 15.0)

        glfw.set_window_pos.assert_called_once_with(
            self.host.window, 120, 105,
        )

    def test_a_window_nobody_holds_stays_put(self) -> None:
        """A cursor moving over the window moves nothing by itself."""
        glfw = mouse_glfw()

        with patch.dict(sys.modules, {'glfw': glfw}):
            self.host.on_cursor(None, 30.0, 15.0)

        glfw.set_window_pos.assert_not_called()


class CubeViewHostAliasedTestCase(unittest.TestCase):
    """A cube drawn into the window itself, antialiasing dropped."""

    def setUp(self) -> None:
        """Wire a host asked for no antialiasing at all."""
        self.viewer = create_autospec(Viewer, instance=True)
        self.viewer.cube = VCube()
        self.viewer.look = Look()
        self.view = CubeView(self.viewer)

    def build_host(self, *, transparent: bool, msaa: bool) -> CubeViewHost:
        """
        Build a host of either window, antialiased or not.

        Args:
            transparent: Whether the cube is laid on the desktop.
            msaa: Whether the cube is antialiased at all.

        Returns:
            The host, on the mocked viewer of this case.

        """
        return CubeViewHost(
            viewer=self.viewer,
            title=self.view.title,
            view=self.view,
            transparent=transparent,
            msaa=msaa,
        )

    def opened_samples(self, host: CubeViewHost) -> list[int]:
        """
        Read the samples the window was asked for as it opened.

        Args:
            host: The host to open, its parent mocked out.

        Returns:
            What the look of the viewer held while the parent opened.

        """
        asked = []

        def opened() -> MagicMock:
            asked.append(self.viewer.look.samples)
            return MagicMock()

        with patch.object(GlfwHost, 'open', side_effect=opened):
            host.open()

        return asked

    def test_a_window_holding_its_samples_keeps_them(self) -> None:
        """An ordinary window is opened as cubing-algs opens it."""
        host = self.build_host(transparent=False, msaa=True)

        self.assertEqual(self.opened_samples(host), [Look().samples])

    def test_an_aliased_window_asks_for_no_samples(self) -> None:
        """No antialiasing at all is no antialiasing in the window."""
        host = self.build_host(transparent=False, msaa=False)

        self.assertEqual(self.opened_samples(host), [0])

        # Put back at once: the screenshot and the report read it too.
        self.assertEqual(self.viewer.look.samples, Look().samples)

    def test_an_aliased_window_draws_into_itself(self) -> None:
        """A transparent window takes no detour either, asked aliased."""
        host = self.build_host(transparent=True, msaa=False)

        with patch.object(window, 'OffscreenTarget') as offscreen:
            host.refresh_target()

        offscreen.create.assert_not_called()
        self.assertIsNone(host.target)
        self.assertFalse(host.offscreen)


class MainTestCase(unittest.TestCase):
    """The command line of the client, and what it assembles."""

    def test_help_is_formatted(self) -> None:
        """The help of the client is written the way term-timer writes it."""
        help_text = entry.build_parser().format_help()

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
                entry.build_parser().parse_args(['-e', ENDPOINT, '-w', value])

    def test_endpoint_is_required(self) -> None:
        """A client with no endpoint has nothing to listen to."""
        with self.assertRaises(SystemExit):
            entry.build_parser().parse_args([])

    def test_endpoint_ipc_path_expanded(self) -> None:
        """A tilde on the command line is the home the publisher binds."""
        options = entry.build_parser().parse_args(
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
                entry.build_parser().parse_args(['-e', value])

    def test_build_host(self) -> None:
        """The options of the client reach the viewer it builds."""
        options = entry.build_parser().parse_args(
            ['-e', ENDPOINT, '-o', 'DF', '-w', '640x480', '-m', 'oll'],
        )

        host = entry.build_host(options)

        self.assertEqual(host.view.orientation, 'DF')
        self.assertEqual(host.viewer.window_size, (640, 480))
        self.assertEqual(host.viewer.mode, 'oll')
        self.assertIs(host.viewer.orientation, host.view.tracker)
        self.assertEqual(host.title, WINDOW_TITLE)
        self.assertTrue(host.msaa)

    def test_build_host_without_antialiasing(self) -> None:
        """A cube asked for aliased is drawn into the window itself."""
        options = entry.build_parser().parse_args(
            ['-e', ENDPOINT, '-t', '--no-msaa'],
        )

        host = entry.build_host(options)

        self.assertTrue(host.transparent)
        self.assertFalse(host.msaa)
        self.assertFalse(host.offscreen)

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

    def test_main_interrupted(self) -> None:
        """An interruption from the keyboard closes the stream."""
        host = MagicMock()
        host.run.side_effect = KeyboardInterrupt
        stream = MagicMock()

        self.assertEqual(run_main(host, stream), 0)

        stream.stop.assert_called_once_with()
