"""
Tests for the ``cube-tray`` client.

Nothing here talks to a bus and nothing opens a window: the client
decides what the icon says and what a click does, the popup is handed
over, and the icon is drawn into a buffer that is read back. What is
left out is the two service interfaces, which translate one call into
another and are asserted where they can be: on the lines they carry.
"""
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock
from unittest.mock import patch

from term_timer_clients.orders import HIDE_ORDER
from term_timer_clients.orders import SHOW_ORDER
from term_timer_clients.tests.fixtures import envelope
from term_timer_clients.tray import main as entry
from term_timer_clients.tray.bus import BusError
from term_timer_clients.tray.cast import CLOSING_TIMEOUT
from term_timer_clients.tray.cast import DEFAULT_POPUP_SIZE
from term_timer_clients.tray.cast import MANAGED_FLAG
from term_timer_clients.tray.cast import TRANSPARENT_FLAG
from term_timer_clients.tray.cast import Popup
from term_timer_clients.tray.cast import cast_command
from term_timer_clients.tray.cast import cast_program
from term_timer_clients.tray.client import HIDE_LABEL
from term_timer_clients.tray.client import QUIT_ITEM
from term_timer_clients.tray.client import SHOW_LABEL
from term_timer_clients.tray.client import STATUS_ITEM
from term_timer_clients.tray.client import TOGGLE_ITEM
from term_timer_clients.tray.client import TRAY_CONNECTED
from term_timer_clients.tray.client import TRAY_OFFLINE
from term_timer_clients.tray.client import CubeTray
from term_timer_clients.tray.icon import FLAT_SHARE
from term_timer_clients.tray.icon import ICON_SIZES
from term_timer_clients.tray.icon import LIVE_FACES
from term_timer_clients.tray.icon import NOTHING
from term_timer_clients.tray.icon import OUTLINE
from term_timer_clients.tray.icon import average
from term_timer_clients.tray.icon import pixmap
from term_timer_clients.tray.icon import pixmaps
from term_timer_clients.tray.icon import shade
from term_timer_clients.tray.icon import within
from term_timer_clients.tray.item import LABEL_PROPERTY
from term_timer_clients.tray.item import SEPARATOR_TYPE
from term_timer_clients.tray.item import TYPE_PROPERTY
from term_timer_clients.tray.item import entry_properties
from term_timer_clients.tray.item import item_service
from term_timer_clients.tray.item import selected

# Bytes per pixel, as the tray protocol carries them.
CHANNELS = 4

# A radius round enough to read the arithmetic of a face off it.
RADIUS = 10.0

ENDPOINT = 'ipc:///tmp/cube-tray-tests'


def run_main(tray: CubeTray, stream: MagicMock) -> int:
    """
    Run the entry point on a mocked stream and a bus that is not there.

    What ``serve()`` does is asserted on a bus of its own, in
    ``test_tray_bus``: what is read here is what the client does around
    it - the stream it starts, and what it gives back however it ends.

    Args:
        tray: The client the entry point is to assemble.
        stream: The object standing in for the subscription.

    Returns:
        The exit code of the entry point.

    """
    argv = ['cube-tray', '-e', ENDPOINT]

    # The configuration of a machine running the tests is never read:
    # what the client is given here is its command line and nothing else
    with (
        patch.object(sys, 'argv', argv),
        patch.object(entry, 'load_config', return_value={}),
        patch.object(entry, 'build_tray', return_value=tray),
        patch.object(entry, 'EventStream', return_value=stream),
    ):
        return entry.main()


class StubPopup(Popup):
    """
    A window that is shown and hidden without a process behind it.

    Every test of what a click does goes through one: what ``Popup``
    owns is a process, and a suite that started one would be a suite
    opening windows. What the real one does with that process and the
    pipe it talks to it on is asserted in ``PopupTestCase``.
    """

    def __init__(self) -> None:
        """Start on a window that is not up."""
        super().__init__(['cube-cast'])

        self.launched = 0
        self.opened = 0
        self.closed = 0
        self.gone = False

    def launch(self) -> None:
        """Open the window, without a process to open."""
        self.launched += 1

    def show(self) -> None:
        """Put the window on the screen."""
        self.opened += 1
        self.shown = True

    def hide(self) -> None:
        """Take the window off the screen."""
        self.closed += 1
        self.shown = False

    def close(self) -> None:
        """Take the window down, with nothing to take down."""
        self.hide()

    def settle(self) -> bool:
        """
        Notice a window that went away.

        Returns:
            True when it did, once.

        """
        if not self.gone:
            return False

        self.gone = False
        self.shown = False

        return True


class IconShapeTestCase(unittest.TestCase):
    """Where the cube is on the icon, and where it is not."""

    def test_the_corner_of_a_cube_is_at_the_center(self) -> None:
        """The three faces meet where the icon is centered."""
        self.assertIn(shade((0.0, 0.0), RADIUS, LIVE_FACES), LIVE_FACES)

    def test_nothing_is_drawn_beyond_the_cube(self) -> None:
        """What is around the cube belongs to the bar."""
        self.assertEqual(
            shade((RADIUS * 2, RADIUS * 2), RADIUS, LIVE_FACES),
            NOTHING,
        )

    def test_the_cube_is_worn_at_its_own_height(self) -> None:
        """A cube taller than its radius is a cube nobody drew."""
        self.assertEqual(
            shade((0.0, -RADIUS * 1.01), RADIUS, LIVE_FACES),
            NOTHING,
        )

    def test_the_outline_runs_all_the_way_around(self) -> None:
        """
        The rim is the cube drawn wider, so it has no gap.

        The sides are read off `FLAT_SHARE` rather than written down:
        what that number picks is the corner the cube is seen from, and
        a test naming a width of its own would fail the day the cube is
        seen from another one - saying nothing at all about the rim.
        """
        side = RADIUS * FLAT_SHARE * 0.99

        for point in (
                (0.0, -RADIUS * 0.99),
                (0.0, RADIUS * 0.99),
                (-side, 0.0),
                (side, 0.0),
        ):
            with self.subTest(point=point):
                self.assertEqual(shade(point, RADIUS, LIVE_FACES), OUTLINE)

    def test_the_three_faces_are_all_drawn(self) -> None:
        """A cube seen by its corner shows three of its faces."""
        seen = {
            shade(point, RADIUS, LIVE_FACES)
            for point in ((0.0, -RADIUS / 2), (-4.0, 3.0), (4.0, 3.0))
        }

        self.assertEqual(len(seen), 3)

    def test_a_face_with_no_surface_holds_no_point(self) -> None:
        """A rhombus of one line is one nothing can fall on."""
        flat = ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))

        self.assertFalse(within((0.0, 0.0), flat))

    def test_the_top_face_is_the_lightest(self) -> None:
        """What makes three rhombi read as one solid."""
        top, left, right = LIVE_FACES

        self.assertGreater(sum(top[:3]), sum(left[:3]))
        self.assertGreater(sum(top[:3]), sum(right[:3]))


class IconBlendTestCase(unittest.TestCase):
    """How what is found under a pixel becomes the pixel."""

    def test_a_pixel_with_nothing_under_it_is_nothing(self) -> None:
        """An empty corner of the icon lets the bar through."""
        self.assertEqual(average([NOTHING, NOTHING]), NOTHING)

    def test_an_edge_keeps_the_color_and_loses_the_cover(self) -> None:
        """
        The color is weighed by how much of it there is.

        Averaging the channels flat would drag the black of what is
        merely absent into the color, and edge every face with a halo.
        """
        color = (200, 100, 50, 255)

        red, green, blue, alpha = average([color, NOTHING])

        self.assertEqual((red, green, blue), (200, 100, 50))
        self.assertLess(alpha, 255)

    def test_two_of_the_same_stay_the_same(self) -> None:
        """A pixel wholly inside a face wears that face."""
        color = (200, 100, 50, 255)

        self.assertEqual(average([color, color]), color)


class IconPixmapTestCase(unittest.TestCase):
    """The icon as the bar is handed it."""

    def test_the_icon_is_as_big_as_it_says(self) -> None:
        """A pixmap and its size disagreeing is a bar drawing noise."""
        width, height, pixels = pixmap(22, connected=True)

        self.assertEqual((width, height), (22, 22))
        self.assertEqual(len(pixels), width * height * CHANNELS)

    def test_the_icon_is_drawn_at_every_size_asked_for(self) -> None:
        """A scaled display picks the big one, a plain bar the small."""
        drawn = pixmaps(connected=True)

        self.assertEqual(
            tuple(width for width, _height, _pixels in drawn),
            ICON_SIZES,
        )

    def test_a_cube_that_is_there_is_not_the_one_that_is_not(self) -> None:
        """The whole of what an icon in a bar has to say."""
        self.assertNotEqual(
            pixmap(22, connected=True),
            pixmap(22, connected=False),
        )

    def test_the_same_icon_is_drawn_twice_the_same(self) -> None:
        """A picture that moves on its own is a bar that flickers."""
        self.assertEqual(
            pixmap(22, connected=False),
            pixmap(22, connected=False),
        )

    def test_the_middle_of_the_icon_is_the_cube(self) -> None:
        """A cube drawn off the icon is one nobody sees."""
        width, height, pixels = pixmap(22, connected=True)

        middle = ((height // 2) * width + width // 2) * CHANNELS

        self.assertEqual(pixels[middle], 255)

    def test_the_corners_of_the_icon_are_left_alone(self) -> None:
        """A bar puts its own room around an icon."""
        _width, _height, pixels = pixmap(22, connected=True)

        self.assertEqual(pixels[0], 0)
        self.assertEqual(pixels[-CHANNELS], 0)


class CastCommandTestCase(unittest.TestCase):
    """What is run when the window is opened."""

    def test_the_window_is_opened_on_the_stream_of_the_icon(self) -> None:
        """One endpoint for the two clients, or two different cubes."""
        command = cast_command('ipc:///tmp/cube', (100, 200), program='cast')

        self.assertEqual(
            command,
            ['cast', '--endpoint', 'ipc:///tmp/cube',
             TRANSPARENT_FLAG, MANAGED_FLAG, '--window-size', '100x200'],
        )

    def test_the_window_is_laid_on_the_desktop(self) -> None:
        """A popup is a window with no bar, floating over the rest."""
        self.assertIn(
            TRANSPARENT_FLAG,
            cast_command('ipc:///tmp/cube', DEFAULT_POPUP_SIZE),
        )

    def test_what_was_typed_comes_last(self) -> None:
        """Coming last is what lets it argue with what is written here."""
        command = cast_command(
            'ipc:///tmp/cube', (100, 200), ['--palette', 'rgb'],
            program='cast',
        )

        self.assertEqual(command[-2:], ['--palette', 'rgb'])

    def test_the_window_is_the_one_of_this_installation(self) -> None:
        """A tray in a virtualenv opens the window of that virtualenv."""
        self.assertTrue(cast_program().endswith('cube-cast'))

    def test_a_window_installed_elsewhere_is_looked_for(self) -> None:
        """An installation with no client beside it still has a path."""
        with (
            patch(
                'term_timer_clients.tray.cast.Path.exists',
                return_value=False,
            ),
            patch(
                'term_timer_clients.tray.cast.shutil.which',
                return_value='/usr/bin/cube-cast',
            ),
        ):
            self.assertEqual(cast_program(), '/usr/bin/cube-cast')


def orders(process: MagicMock) -> list[str]:
    """
    Read back what was asked of a window, in the order it was asked.

    Args:
        process: The process the orders were written to.

    Returns:
        The orders, without the newline that separates them.

    """
    return [
        call.args[0].strip()
        for call in process.stdin.write.call_args_list
    ]


class PopupTestCase(unittest.TestCase):
    """The window as the process it is, and the pipe it is driven on."""

    def setUp(self) -> None:
        """Hold a popup that has opened nothing."""
        self.popup = Popup(['cube-cast'])

    @contextmanager
    def opening(self, *, alive: bool = True) -> Iterator[MagicMock]:
        """
        Run a block with a process standing in for the window.

        Args:
            alive: Whether the process answers as one that is running.

        Yields:
            The process the popup opened, as the mock it is.

        """
        with patch(
                'term_timer_clients.tray.cast.subprocess.Popen',
        ) as opening:
            process = opening.return_value
            process.poll.return_value = None if alive else 0

            self.opened = opening

            yield process

    def test_a_popup_opens_nothing_by_itself(self) -> None:
        """A popup is opened by the tray, and never by being built."""
        self.assertFalse(self.popup.shown)
        self.assertFalse(self.popup.running)

    def test_the_window_is_opened_hidden(self) -> None:
        """The whole point: it follows the stream before anybody looks."""
        with self.opening() as process:
            self.popup.launch()

        self.opened.assert_called_once()
        self.assertEqual(self.opened.call_args.args[0], ['cube-cast'])
        self.assertIs(
            self.opened.call_args.kwargs['stdin'], subprocess.PIPE,
        )
        self.assertTrue(self.popup.running)
        self.assertFalse(self.popup.shown)
        self.assertEqual(orders(process), [])

    def test_a_window_that_cannot_be_opened_leaves_the_icon(self) -> None:
        """The icon is what is left, and it still says what it says."""
        with (
                patch(
                    'term_timer_clients.tray.cast.subprocess.Popen',
                    side_effect=OSError('no such program'),
                ),
                self.assertLogs('term_timer_clients.tray.cast', 'ERROR'),
        ):
            self.popup.show()

        self.assertFalse(self.popup.shown)
        self.assertFalse(self.popup.running)

    def test_a_second_launch_opens_no_second_window(self) -> None:
        """One icon, one window."""
        with self.opening():
            self.popup.launch()
            self.popup.launch()

        self.assertEqual(self.opened.call_count, 1)

    def test_a_click_shows_the_window_that_is_already_there(self) -> None:
        """A click is a line on a pipe, not a process and a first frame."""
        with self.opening() as process:
            self.popup.launch()
            self.popup.show()

        self.assertEqual(self.opened.call_count, 1)
        self.assertEqual(orders(process), [SHOW_ORDER])
        self.assertTrue(self.popup.shown)

    def test_a_click_with_no_window_left_opens_one(self) -> None:
        """An icon that stops showing anything is worse than a first frame."""
        with self.opening() as process:
            self.popup.show()

        self.assertEqual(self.opened.call_count, 1)
        self.assertEqual(orders(process), [SHOW_ORDER])

    def test_hiding_leaves_the_window_following_the_stream(self) -> None:
        """Nothing is closed and nothing is given back."""
        with self.opening() as process:
            self.popup.show()
            self.popup.hide()

        self.assertEqual(orders(process), [SHOW_ORDER, HIDE_ORDER])
        self.assertFalse(self.popup.shown)
        self.assertTrue(self.popup.running)
        process.wait.assert_not_called()

    def test_a_second_click_takes_the_window_away(self) -> None:
        """One gesture, both ways."""
        with self.opening() as process:
            self.popup.toggle()
            self.assertTrue(self.popup.shown)

            self.popup.toggle()

        self.assertEqual(orders(process), [SHOW_ORDER, HIDE_ORDER])
        self.assertFalse(self.popup.shown)

    def test_a_window_that_is_not_there_is_ordered_nothing(self) -> None:
        """Nothing is written where there is no pipe to write to."""
        self.popup.hide()

        self.assertFalse(self.popup.shown)

    def test_a_pipe_that_is_gone_is_a_window_that_is_gone(self) -> None:
        """A window nothing can reach is a window nothing is showing."""
        with self.opening() as process:
            process.stdin.write.side_effect = BrokenPipeError('gone')

            self.popup.show()

        self.assertFalse(self.popup.shown)

    def test_a_window_that_is_still_up_is_not_settled(self) -> None:
        """A process that has not returned is a window that is there."""
        with self.opening():
            self.popup.show()

            self.assertFalse(self.popup.settle())
            self.assertTrue(self.popup.shown)

    def test_a_window_that_went_away_is_noticed(self) -> None:
        """A window that crashed is one the next click has to open again."""
        with self.opening(alive=False):
            self.popup.show()

            self.assertTrue(self.popup.settle())
            self.assertFalse(self.popup.shown)
            self.assertFalse(self.popup.running)

    def test_a_window_is_asked_to_go_by_the_end_of_its_pipe(self) -> None:
        """The one order a process taken away cannot fail to give."""
        with self.opening() as process:
            self.popup.show()
            self.popup.close()

        process.stdin.close.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=CLOSING_TIMEOUT)
        self.assertFalse(self.popup.shown)

    def test_a_window_that_will_not_go_is_taken_down(self) -> None:
        """A window hung on its driver still has to make way."""
        with self.opening() as process:
            process.wait.side_effect = [
                subprocess.TimeoutExpired('cube-cast', CLOSING_TIMEOUT), None,
            ]

            self.popup.show()

            with self.assertLogs(
                    'term_timer_clients.tray.cast', 'WARNING',
            ):
                self.popup.close()

        process.kill.assert_called_once_with()

    def test_a_window_with_no_pipe_left_is_taken_down_all_the_same(
            self,
    ) -> None:
        """A window is closed by whatever there is left to close it with."""
        with self.opening() as process:
            process.stdin = None

            self.popup.launch()
            self.popup.close()

        process.wait.assert_called_once_with(timeout=CLOSING_TIMEOUT)

    def test_a_window_that_is_not_up_is_not_taken_down(self) -> None:
        """A tray closed before it ever showed anything closes nothing."""
        self.popup.close()

        self.assertFalse(self.popup.shown)


class TrayLabelTestCase(unittest.TestCase):
    """What the icon says of the cube, in one line."""

    def setUp(self) -> None:
        """Wire a tray on a window that opens nothing."""
        self.popup = StubPopup()
        self.tray = CubeTray(self.popup)

    def test_a_stream_that_said_nothing_has_no_cube(self) -> None:
        """An icon opened on a silent stream says so."""
        self.assertEqual(self.tray.label, TRAY_OFFLINE)

    def test_a_cube_that_has_not_named_itself_is_still_a_cube(self) -> None:
        """A session joined in the middle has heard no name."""
        self.tray.dispatch(envelope('cube.move', {'move': 'R'}))

        self.assertEqual(self.tray.label, TRAY_CONNECTED)

    def test_the_cube_is_named_as_it_introduces_itself(self) -> None:
        """What the window writes in its bar, an icon says here."""
        self.tray.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}),
        )
        self.tray.dispatch(envelope('cube.battery', {'level': 80}))

        self.assertEqual(self.tray.label, 'GANi3 · 80%')

    def test_a_cube_that_left_takes_its_name_with_it(self) -> None:
        """A name belongs to the link it was given over."""
        self.tray.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}),
        )
        self.tray.dispatch(
            envelope('cube.link', {'connected': False, 'reason': 'lost'}),
        )

        self.assertEqual(self.tray.label, TRAY_OFFLINE)


class TrayMenuTestCase(unittest.TestCase):
    """The lines the icon drops, and what a click on them does."""

    def setUp(self) -> None:
        """Wire a tray on a window that opens nothing."""
        self.popup = StubPopup()
        self.tray = CubeTray(self.popup)

    def test_every_line_has_an_identifier_of_its_own(self) -> None:
        """A line sharing an identifier is a click landing elsewhere."""
        identifiers = [entry.identifier for entry in self.tray.entries]

        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_no_line_is_the_root_of_the_menu(self) -> None:
        """Zero is the menu itself, and a shell reads it as such."""
        self.assertNotIn(0, [entry.identifier for entry in self.tray.entries])

    def test_the_state_of_the_cube_comes_first(self) -> None:
        """A menu is opened to read as much as to act."""
        first = self.tray.entries[0]

        self.assertEqual(first.identifier, STATUS_ITEM)
        self.assertEqual(first.label, TRAY_OFFLINE)
        self.assertFalse(first.enabled)

    def test_the_gesture_says_what_it_will_do(self) -> None:
        """The same line shows the window and hides it."""
        entries = {entry.identifier: entry for entry in self.tray.entries}
        self.assertEqual(entries[TOGGLE_ITEM].label, SHOW_LABEL)

        self.tray.toggle()

        entries = {entry.identifier: entry for entry in self.tray.entries}
        self.assertEqual(entries[TOGGLE_ITEM].label, HIDE_LABEL)

    def test_the_menu_opens_the_window_too(self) -> None:
        """Some shells never send a plain click, so the menu carries it."""
        self.tray.activate(TOGGLE_ITEM)

        self.assertEqual(self.popup.opened, 1)

    def test_quitting_takes_the_window_with_it(self) -> None:
        """A tray that goes away leaves no window behind."""
        self.tray.toggle()

        self.tray.activate(QUIT_ITEM)

        self.assertTrue(self.tray.stopped)
        self.assertFalse(self.popup.shown)

    def test_a_line_that_is_not_there_does_nothing(self) -> None:
        """What a client does not know, it ignores."""
        self.tray.activate(404)

        self.assertEqual(self.popup.opened, 0)
        self.assertFalse(self.tray.stopped)


class TrayStateTestCase(unittest.TestCase):
    """What the bar is written again for, and what it is not."""

    def setUp(self) -> None:
        """Wire a tray on a window that opens nothing."""
        self.popup = StubPopup()
        self.tray = CubeTray(self.popup)

    def test_a_cube_that_connects_moves_the_bar(self) -> None:
        """The one thing an icon is there to show."""
        before = self.tray.state

        self.tray.dispatch(envelope('cube.move', {'move': 'R'}))

        self.assertNotEqual(self.tray.state, before)

    def test_a_gyroscope_moves_nothing_in_the_bar(self) -> None:
        """Tens of messages a second, and nothing new to say."""
        self.tray.dispatch(envelope('cube.gyro', {'quaternion': {}}))
        before = self.tray.state

        for _ in range(10):
            self.tray.dispatch(envelope('cube.gyro', {'quaternion': {}}))

        self.assertEqual(self.tray.state, before)

    def test_a_window_opening_moves_the_bar(self) -> None:
        """The menu offers to hide what is up."""
        before = self.tray.state

        self.tray.toggle()

        self.assertNotEqual(self.tray.state, before)

    def test_a_window_closing_itself_is_settled(self) -> None:
        """Or the next click would close a window already gone."""
        self.tray.toggle()
        self.popup.gone = True

        with self.assertLogs('term_timer_clients.tray.client', 'INFO'):
            self.assertTrue(self.tray.settle())

        self.assertFalse(self.popup.shown)

    def test_a_window_that_is_up_settles_nothing(self) -> None:
        """Nothing is said of a window that is simply there."""
        self.tray.toggle()

        self.assertFalse(self.tray.settle())
        self.assertTrue(self.popup.shown)


class MenuPropertiesTestCase(unittest.TestCase):
    """A line of the menu, as the protocol carries it."""

    def setUp(self) -> None:
        """Wire a tray on a window that opens nothing."""
        self.tray = CubeTray(StubPopup())

    def test_a_separator_is_a_rule_and_nothing_else(self) -> None:
        """A rule carries no label, and a shell draws it as a line."""
        properties = entry_properties(self.tray.entries[1])

        self.assertEqual(list(properties), [TYPE_PROPERTY])
        self.assertEqual(properties[TYPE_PROPERTY].value, SEPARATOR_TYPE)

    def test_a_line_carries_what_it_says_and_whether_it_answers(
            self,
    ) -> None:
        """The whole of what this menu ever offers."""
        properties = entry_properties(self.tray.entries[0])

        self.assertEqual(properties[LABEL_PROPERTY].value, TRAY_OFFLINE)
        self.assertNotIn(TYPE_PROPERTY, properties)

    def test_only_what_was_asked_for_is_handed_over(self) -> None:
        """A shell asking for one property is given one."""
        properties = entry_properties(self.tray.entries[0])

        self.assertEqual(
            list(selected(properties, [LABEL_PROPERTY])),
            [LABEL_PROPERTY],
        )

    def test_asking_for_nothing_asks_for_all_of_it(self) -> None:
        """An empty list is how the protocol spells everything."""
        properties = entry_properties(self.tray.entries[0])

        self.assertEqual(selected(properties, []), properties)

    def test_the_icon_is_named_after_the_process_holding_it(self) -> None:
        """Two trays running at once must not collide on the bus."""
        self.assertIn(str(os.getpid()), item_service())


class ParserTestCase(unittest.TestCase):
    """What the client takes on its command line."""

    def setUp(self) -> None:
        """Build the parser of a client with nothing configured."""
        self.parser = entry.build_parser({})

    def test_the_stream_is_required_when_nothing_configures_it(self) -> None:
        """A client with no stream to listen to says so."""
        with patch('sys.stderr'), self.assertRaises(SystemExit):
            self.parser.parse_args([])

    def test_the_window_opens_on_a_size_of_its_own(self) -> None:
        """A popup is glanced at, not worked in."""
        options = self.parser.parse_args(['-e', 'ipc:///tmp/cube'])

        self.assertEqual(options.window_size, DEFAULT_POPUP_SIZE)

    def test_what_follows_two_dashes_is_for_the_window(self) -> None:
        """The window is argued with where it is documented."""
        options = self.parser.parse_args(
            ['-e', 'ipc:///tmp/cube', '--', '--palette', 'rgb'],
        )

        self.assertEqual(options.cast_arguments, ['--palette', 'rgb'])

    def test_the_window_is_built_on_what_was_typed(self) -> None:
        """One command line for the icon and the window under it."""
        options = self.parser.parse_args(
            ['-e', 'ipc:///tmp/cube', '-w', '100x100', '--', '--view', 'user'],
        )

        command = entry.build_tray(options).popup.command

        self.assertIn('ipc:///tmp/cube', command)
        self.assertIn('100x100', command)
        self.assertEqual(command[-2:], ['--view', 'user'])


if __name__ == '__main__':
    unittest.main()


class EntryPointTestCase(unittest.TestCase):
    """What the client does around the loop that shows the icon."""

    def setUp(self) -> None:
        """Hold a tray and a stream that neither listen nor draw."""
        self.popup = StubPopup()
        self.tray = CubeTray(self.popup)
        self.stream = MagicMock()

    def run_serving(self, error: BaseException | None = None) -> int:
        """
        Run the entry point on a loop that does what it is told.

        Args:
            error: What the loop is to end on, none for a loop that
                simply returns. A ``KeyboardInterrupt`` is one of
                them, and it is no ``Exception``.

        Returns:
            The exit code of the entry point.

        """
        # The loop is held back at both ends: what `serve()` would have
        # made is never made either, a coroutine nothing ever awaits
        # being an object Python complains about on its own.
        with (
            patch.object(entry, 'serve', new=MagicMock()),
            patch('asyncio.run', side_effect=error),
        ):
            return run_main(self.tray, self.stream)

    def test_the_stream_is_read_before_the_icon_is_shown(self) -> None:
        """A subscriber connected first misses nothing of a session."""
        self.assertEqual(self.run_serving(), 0)

        self.stream.start.assert_called_once_with(self.tray.dispatch)

    def test_a_desktop_with_no_tray_is_reported(self) -> None:
        """A client with nowhere to be shown says where a tray is."""
        with self.assertLogs('term_timer_clients.tray.main', 'ERROR') as logs:
            code = self.run_serving(BusError('no watcher'))

        self.assertEqual(code, 1)
        self.assertIn('AppIndicator', logs.output[0])

    def test_a_bus_that_is_not_there_is_reported_too(self) -> None:
        """A session with no bus at all is the same absence."""
        self.assertEqual(
            self.run_serving(OSError('no bus')),
            1,
        )

    def test_the_tray_is_closed_by_hand_like_any_client(self) -> None:
        """A Ctrl-C in the terminal is how a tray is stopped."""
        self.assertEqual(
            self.run_serving(KeyboardInterrupt()),
            0,
        )

    def test_the_window_is_opened_with_the_icon(self) -> None:
        """
        A window opened at the click has heard nothing of the session.

        The whole reason there are two processes and one of them starts
        with the other: a cube describes itself when it connects and
        announces nothing when it arrives, so a window opened in the
        middle of a session shows the core alone until the cube
        connects again.
        """
        self.assertEqual(self.run_serving(), 0)

        self.assertEqual(self.popup.launched, 1)
        self.assertFalse(self.popup.shown)

    def test_the_window_never_outlives_the_icon(self) -> None:
        """A popup left behind is one nothing can ever close again."""
        self.popup.shown = True

        self.run_serving(KeyboardInterrupt())

        self.assertFalse(self.popup.shown)

    def test_the_stream_is_given_back_however_it_ends(self) -> None:
        """A socket held by a client that is gone is a socket lost."""
        self.run_serving(BusError('no watcher'))

        self.stream.stop.assert_called_once_with()
