"""
Tests for the ``tt-tail`` client.

Nothing here writes to a terminal: the client turns an envelope into
lines and hands them to a writer, so a list is the whole of the output
device. The colors are off everywhere but where they are the subject -
an escape counted as a column is a block nobody can assert on.
"""
import io
import json
import os
import sys
import time
import unittest
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

from term_timer_clients.protocol import SESSION_END_TOPIC
from term_timer_clients.tail import ansi
from term_timer_clients.tail import main as entry
from term_timer_clients.tail.ansi import Paint
from term_timer_clients.tail.ansi import build_paint
from term_timer_clients.tail.client import QUIET_TOPICS
from term_timer_clients.tail.client import StreamTail
from term_timer_clients.tail.client import TopicFilter
from term_timer_clients.tail.render import MINIMUM_WIDTH
from term_timer_clients.tail.render import Renderer
from term_timer_clients.tail.render import format_date
from term_timer_clients.tail.render import format_facelets
from term_timer_clients.tail.render import format_float
from term_timer_clients.tail.render import format_gap
from term_timer_clients.tail.render import format_seconds
from term_timer_clients.tail.render import format_time
from term_timer_clients.tail.render import is_scalar
from term_timer_clients.tests.fixtures import envelope
from term_timer_clients.tests.fixtures import envelopes

ENDPOINT = 'tcp://127.0.0.1:5333'

# A configuration as term-timer writes it, cut down to what a client of
# the stream reads in it
CONFIG = {
    'publisher': {
        'active': True,
        'endpoints': [ENDPOINT],
    },
}

# The width the blocks are laid out on here, so that wrapping is what a
# test asks for rather than what the terminal running it happens to be
WIDTH = 76

STAMP = 1755500000.0

GYRO = next(iter(QUIET_TOPICS))


def message(
        topic: str,
        data: dict[str, Any] | None = None,
        sequence: int = 0,
        stamp: float = STAMP,
) -> dict[str, Any]:
    """
    Build a message placed in the sequence and in time.

    Args:
        topic: Topic of the message.
        data: Payload of the message.
        sequence: Where it sits in what the publisher counted.
        stamp: When it was published, in epoch seconds.

    Returns:
        The envelope, ready to be dispatched.

    """
    envelope_ = envelope(topic, data)
    envelope_['seq'] = sequence
    envelope_['ts'] = stamp

    return envelope_


class PaintTestCase(unittest.TestCase):
    """What wears a color, and what decides nothing does."""

    def test_disabled_paint_hands_the_text_back(self) -> None:
        """A painter that is off returns what it was given."""
        paint = Paint(enabled=False)

        self.assertEqual(paint('R', ansi.HIGHLIGHT), 'R')

    def test_enabled_paint_wraps_the_text(self) -> None:
        """A painter that is on opens and closes the escape."""
        paint = Paint()

        self.assertEqual(
            paint('R', ansi.HIGHLIGHT),
            f'{ ansi.HIGHLIGHT }R{ ansi.RESET }',
        )

    def test_paint_wears_every_code_given(self) -> None:
        """Several codes are worn at once, and closed once."""
        painted = Paint()('R', ansi.HIGHLIGHT, ansi.BOLD)

        self.assertEqual(
            painted,
            f'{ ansi.HIGHLIGHT }{ ansi.BOLD }R{ ansi.RESET }',
        )

    def test_paint_without_a_code_changes_nothing(self) -> None:
        """A text asked for no color is not wrapped at all."""
        self.assertEqual(Paint()('R'), 'R')

    def test_empty_text_is_never_painted(self) -> None:
        """An escape around nothing is an escape nobody needs."""
        self.assertEqual(Paint()('', ansi.HIGHLIGHT), '')

    def test_a_terminal_wears_colors(self) -> None:
        """An output that says it is a terminal is painted."""
        stream = MagicMock()
        stream.isatty.return_value = True

        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(build_paint(stream, colorless=False).enabled)

    def test_a_file_wears_none(self) -> None:
        """Escapes in a file are what a reader has to strip first."""
        with patch.dict(os.environ, {}, clear=True):
            paint = build_paint(io.StringIO(), colorless=False)

        self.assertFalse(paint.enabled)

    def test_the_command_line_refuses_the_colors(self) -> None:
        """--no-color is answered whatever the output is."""
        stream = MagicMock()
        stream.isatty.return_value = True

        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(build_paint(stream, colorless=True).enabled)

    def test_the_environment_refuses_the_colors(self) -> None:
        """NO_COLOR is answered whatever the output is."""
        stream = MagicMock()
        stream.isatty.return_value = True

        with patch.dict(os.environ, {ansi.COLOR_VARIABLE: '1'}, clear=True):
            self.assertFalse(build_paint(stream, colorless=False).enabled)


class FormatTestCase(unittest.TestCase):
    """The units and the shapes a value of the stream is read in."""

    def test_float_drops_the_zeros_it_ends_on(self) -> None:
        """A number is written no longer than it has to be."""
        cases = (
            (0.6009704886013367, '0.60097'),
            (-0.7972960600604266, '-0.797296'),
            (0.0, '0'),
            (1.0, '1'),
        )

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(format_float(value), expected)

    def test_time_is_written_where_the_client_runs(self) -> None:
        """An instant of the stream is the time of day it happened at."""
        with patch.dict(os.environ, {'TZ': 'UTC'}):
            time.tzset()
            self.assertEqual(format_time(STAMP), '06:53:20.000')
            self.assertEqual(format_date(STAMP), '2025-08-18 06:53:20')

        time.tzset()

    def test_durations_are_counted_in_seconds(self) -> None:
        """A duration is written to the millisecond, and named."""
        self.assertEqual(format_seconds(12.3456), '12.346 s')
        self.assertEqual(format_gap(1.2), '1.200s')

    def test_facelets_are_spaced_out_into_faces(self) -> None:
        """A state of the cube is read one face at a time."""
        self.assertEqual(
            format_facelets('U' * 9 + 'R' * 9 + 'F' * 9 + 'D' * 9
                            + 'L' * 9 + 'B' * 9),
            'UUUUUUUUU RRRRRRRRR FFFFFFFFF DDDDDDDDD LLLLLLLLL BBBBBBBBB',
        )

    def test_facelets_of_no_cube_are_left_alone(self) -> None:
        """What does not divide into faces is not cut into any."""
        for value in ('', 'UUUUU'):
            with self.subTest(value=value):
                self.assertEqual(format_facelets(value), value)

    def test_scalars_are_what_fits_on_a_line(self) -> None:
        """A value carrying nothing else is written inline."""
        for value in ('R', 1, 1.0, True, None):
            with self.subTest(value=value):
                self.assertTrue(is_scalar(value))

        for carrier in ({}, [], {'a': 1}, [1]):
            with self.subTest(value=carrier):
                self.assertFalse(is_scalar(carrier))


class BlockTestCase(unittest.TestCase):
    """Base case rendering one message on a fixed width."""

    def setUp(self) -> None:
        """Render on a fixed width, with the colors off."""
        self.renderer = Renderer(Paint(enabled=False), width=WIDTH)

    def block(
            self,
            topic: str,
            data: dict[str, Any] | None = None,
            gap: float = -1.0,
            topic_gap: float = -1.0,
    ) -> list[str]:
        """
        Write one message and hand its lines over.

        Args:
            topic: Topic of the message.
            data: Payload of the message.
            gap: Seconds since the message before.
            topic_gap: Seconds since the one before of the same topic.

        Returns:
            The lines of the block.

        """
        return self.renderer.block(
            message(topic, data), gap, topic_gap,
        )


class RenderTestCase(BlockTestCase):
    """The frame a message is written in, and what heads it."""

    def test_a_block_opens_and_closes(self) -> None:
        """A message is framed, whatever it carries."""
        lines = self.block('cube.reset')

        self.assertTrue(lines[0].startswith('┌ '))
        self.assertEqual(lines[-1], '└')

    def test_the_header_names_the_topic_and_the_sequence(self) -> None:
        """The head of a block says what and when it is."""
        header = self.block('cube.move', {'move': 'R'})[0]

        self.assertIn('cube.move', header)
        self.assertIn('#0', header)
        self.assertIn(format_time(STAMP), header)

    def test_the_first_block_shows_no_gap(self) -> None:
        """Nothing came before, so there is no time to show."""
        self.assertNotIn('+', self.block('cube.move', {'move': 'R'})[0])

    def test_the_gaps_are_shown(self) -> None:
        """The cadence of a solve is what the two gaps are for."""
        header = self.block('cube.move', {'move': 'R'}, 1.2, 0.512)[0]

        self.assertIn('+1.200s', header)
        self.assertIn('Δcube.move 0.512s', header)

    def test_a_lone_topic_shows_one_gap(self) -> None:
        """Two gaps of the same message are one gap said twice."""
        header = self.block('cube.move', {'move': 'R'}, 1.2, 1.2)[0]

        self.assertIn('+1.200s', header)
        self.assertNotIn('Δ', header)

    def test_a_time_that_is_not_one_is_survived(self) -> None:
        """An envelope with no instant in it is written all the same."""
        broken = message('cube.move', {'move': 'R'})
        broken['ts'] = 'yesterday'

        self.assertIn('--:--:--.---', self.renderer.block(broken, -1, -1)[0])


class PayloadTestCase(BlockTestCase):
    """What the fields of a payload are written as."""

    def test_names_are_aligned(self) -> None:
        """The values of a block start on one column."""
        lines = self.block(
            'cube.battery', {'level': 80, 'charging_state': 1},
        )

        self.assertEqual(lines[1], '│ level           80')
        self.assertEqual(lines[2], '│ charging_state  1')

    def test_units_are_the_ones_a_reader_counts_in(self) -> None:
        """A field is converted to what its name says it holds."""
        lines = self.block(
            'session.solve',
            {
                'cube_timestamp': 20370.0,
                'time': 12345678901,
                'timestamp': STAMP,
            },
        )

        self.assertIn('20.370 s', lines[1])
        self.assertIn('12.346 s', lines[2])
        self.assertIn(format_time(STAMP), lines[3])

    def test_a_record_is_read_in_seconds(self) -> None:
        """The nanoseconds of a record are what nobody reads."""
        lines = self.block(
            'session.record',
            {'value': 12345678901, 'previous': 13000000000},
        )

        self.assertIn('12.346 s', lines[1])
        self.assertIn('13.000 s', lines[2])

    def test_booleans_and_nothing_are_named(self) -> None:
        """A payload is written in the words JSON wrote it with."""
        lines = self.block(
            'cube.link', {'connected': True, 'lost': False, 'why': None},
        )

        self.assertIn('true', lines[1])
        self.assertIn('false', lines[2])
        self.assertIn('null', lines[3])

    def test_a_mapping_of_scalars_stays_on_its_line(self) -> None:
        """A quaternion is one value in four parts, not four things."""
        lines = self.block(
            'cube.gyro',
            {'quaternion': {'x': 0.5, 'y': 0.5, 'z': 0.5, 'w': 0.5}},
        )

        self.assertEqual(
            lines[1],
            '│ quaternion  x 0.5  y 0.5  z 0.5  w 0.5',
        )

    def test_a_mapping_too_wide_is_laid_out_under_its_name(self) -> None:
        """What does not fit on a line is written one field per line."""
        lines = self.block(
            'cube.gyro',
            {
                'quaternion': {
                    'x': 0.013458662678914763,
                    'y': 0.053895687734611,
                    'z': 0.600970488601336,
                    'w': -0.797296060060426,
                    'extra': 0.123456789012345,
                    'more': 0.987654321098765,
                },
            },
        )

        self.assertEqual(lines[1], '│ quaternion')
        self.assertEqual(lines[2], '│   x      0.013459')

    def test_a_mapping_of_lists_is_laid_out_too(self) -> None:
        """A mapping carrying anything but scalars gets its own lines."""
        lines = self.block(
            'cube.facelets', {'state': {'CP': [0, 1], 'CO': [0, 0]}},
        )

        self.assertEqual(lines[1], '│ state')
        self.assertEqual(lines[2], '│   CP  [0, 1]')

    def test_an_empty_mapping_and_list_are_shown_as_such(self) -> None:
        """Nothing is still something a reader has to see."""
        lines = self.block('cube.reset', {'state': {}, 'moves': []})

        self.assertIn('{}', lines[1])
        self.assertIn('[]', lines[2])

    def test_a_list_of_things_becomes_a_block_each(self) -> None:
        """The steps of a solve are things in their own right."""
        lines = self.block(
            'session.solve',
            {
                'steps': [
                    {'name': 'Cross', 'qtm': 4},
                    {'name': 'F2L', 'qtm': 8},
                ],
            },
        )

        self.assertEqual(lines[1], '│ steps')
        self.assertEqual(lines[2], '│   [1]')
        self.assertEqual(lines[3], '│     name  Cross')
        self.assertEqual(lines[5], '│   [2]')

    def test_a_date_is_written_with_its_day(self) -> None:
        """A solve of yesterday is not an instant of this stream."""
        lines = self.block('session.solve', {'date': STAMP})

        self.assertIn(format_date(STAMP), lines[1])

    def test_a_list_of_lists_is_laid_out_entry_by_entry(self) -> None:
        """What is not a mapping is still an entry of its own."""
        lines = self.block('cube.history', {'moves': [['R', 'U'], ['F']]})

        self.assertEqual(lines[1], '│ moves')
        self.assertEqual(lines[2], '│   [1]')
        self.assertIn('[R, U]', lines[3])

    def test_a_long_value_hangs_under_itself(self) -> None:
        """A scramble stays one field rather than becoming a paragraph."""
        scramble = (
            "R U R' U' F2 B D2 L' R F U2 D B' L2 R2 U D' F' B2 L D2 F "
            "R' B L2 U' F2 D"
        )
        lines = self.block('session.scramble', {'scramble': scramble})

        self.assertTrue(lines[1].startswith('│ scramble  R U'))
        self.assertTrue(lines[2].startswith('│           '))
        self.assertLessEqual(max(len(line) for line in lines), WIDTH)


class EnvelopeTestCase(BlockTestCase):
    """What is written of a message the protocol says nothing of."""

    def test_an_unknown_topic_is_written_all_the_same(self) -> None:
        """A tail that hid what it does not know would be blind."""
        lines = self.block('cube.something_new', {'field': 'value'})

        self.assertIn('cube.something_new', lines[0])
        self.assertIn('value', lines[1])

    def test_a_payload_that_is_not_an_object_is_shown(self) -> None:
        """What the protocol forbids says something about the publisher."""
        broken = message('cube.move')
        broken['data'] = ['R', 'U']

        lines = self.renderer.block(broken, -1, -1)

        self.assertIn('data', lines[1])
        self.assertIn('R', lines[1])

    def test_a_payload_of_nothing_is_a_block_of_nothing(self) -> None:
        """A message with no payload is still a message."""
        empty = message('cube.reset')
        empty['data'] = None

        self.assertEqual(len(self.renderer.block(empty, -1, -1)), 2)

    def test_the_session_line_names_the_publisher(self) -> None:
        """Nothing but a line of its own would ever show the session."""
        line = self.renderer.session(message('cube.move'))

        self.assertIn('session a3f1c8d2', line)
        self.assertIn('solve', line)
        self.assertEqual(len(line), WIDTH)

    def test_a_loss_is_counted_in_the_plural_it_deserves(self) -> None:
        """One message lost is not one messages lost."""
        self.assertIn('1 message lost', self.renderer.loss(1))
        self.assertIn('12 messages lost', self.renderer.loss(12))

    def test_the_colors_say_which_plane_a_topic_is_of(self) -> None:
        """The two planes of the stream are told apart at a glance."""
        renderer = Renderer(Paint(), width=WIDTH)

        self.assertIn(ansi.CUBE_PLANE, renderer.header(
            message('cube.move'), -1, -1,
        ))
        self.assertIn(ansi.SESSION_PLANE, renderer.header(
            message('session.state'), -1, -1,
        ))

    def test_the_state_of_a_solve_is_worn(self) -> None:
        """The field a reader looks for is the one that is colored."""
        renderer = Renderer(Paint(), width=WIDTH)

        lines = renderer.block(
            message('session.state', {'state': 'solving'}), -1, -1,
        )

        self.assertIn(ansi.TRUE, lines[1])

    def test_a_state_of_something_else_is_left_alone(self) -> None:
        """A card of a trainer is not a state of a solve."""
        renderer = Renderer(Paint(), width=WIDTH)

        lines = renderer.block(
            message('session.train', {'state': 'review'}), -1, -1,
        )

        self.assertIn(ansi.STRING, lines[1])

    def test_the_end_of_a_session_is_closed_on_a_line(self) -> None:
        """A stream that is over looks like a quiet one without it."""
        line = self.renderer.farewell(
            message(SESSION_END_TOPIC, {'reason': 'interrupted'}),
        )

        self.assertIn('end of session a3f1c8d2', line)
        self.assertIn('interrupted', line)
        self.assertEqual(len(line), WIDTH)

    def test_a_farewell_with_no_reason_is_still_drawn(self) -> None:
        """What ended a session is not what says it ended."""
        empty = message(SESSION_END_TOPIC)
        empty['data'] = None

        line = self.renderer.farewell(empty)

        self.assertIn('end of session a3f1c8d2', line)
        self.assertEqual(len(line), WIDTH)

    def test_a_reason_is_worn_by_what_it_is(self) -> None:
        """An end nobody asked for is not one that was."""
        renderer = Renderer(Paint(), width=WIDTH)

        self.assertIn(ansi.ALERT, renderer.block(
            message(SESSION_END_TOPIC, {'reason': 'crashed'}), -1, -1,
        )[1])
        self.assertIn(ansi.BREAK, renderer.block(
            message(SESSION_END_TOPIC, {'reason': 'interrupted'}), -1, -1,
        )[1])
        link = message('cube.link', {'connected': False, 'reason': 'lost'})

        self.assertIn(ansi.ALERT, renderer.block(link, -1, -1)[2])

    def test_a_reason_of_something_else_is_left_alone(self) -> None:
        """Only what this protocol names is worn as one of its reasons."""
        renderer = Renderer(Paint(), width=WIDTH)

        lines = renderer.block(
            message('session.train', {'reason': 'review'}), -1, -1,
        )

        self.assertIn(ansi.STRING, lines[1])

    def test_the_width_follows_the_terminal(self) -> None:
        """A renderer given no width reads the one it is shown on."""
        renderer = Renderer(Paint(enabled=False))

        with patch(
                'term_timer_clients.tail.render.shutil.get_terminal_size',
                return_value=os.terminal_size((120, 40)),
        ):
            renderer.measure()

        self.assertEqual(renderer.width, 120)

    def test_a_narrow_terminal_is_given_a_floor(self) -> None:
        """Under a width, a block is more indentation than text."""
        renderer = Renderer(Paint(enabled=False))

        with patch(
                'term_timer_clients.tail.render.shutil.get_terminal_size',
                return_value=os.terminal_size((10, 40)),
        ):
            renderer.measure()

        self.assertEqual(renderer.width, MINIMUM_WIDTH)


class TopicFilterTestCase(unittest.TestCase):
    """What --topic and --exclude narrow the stream down to."""

    def test_nothing_narrowed_shows_everything(self) -> None:
        """A filter with neither side set holds nothing back."""
        self.assertTrue(TopicFilter().shows('cube.move'))

    def test_a_topic_is_kept_by_its_prefix(self) -> None:
        """``cube.`` is what the whole plane is asked for by."""
        whole_plane = TopicFilter(topics=('cube.',))

        self.assertTrue(whole_plane.shows('cube.move'))
        self.assertFalse(whole_plane.shows('session.state'))

    def test_a_whole_topic_name_filters_as_well_as_a_plane(self) -> None:
        """A topic is its own prefix, and asked for the same way."""
        one_topic = TopicFilter(topics=('cube.move',))

        self.assertTrue(one_topic.shows('cube.move'))
        self.assertFalse(one_topic.shows('cube.facelets'))

    def test_an_exclusion_is_a_prefix_too(self) -> None:
        """--exclude drops what it names, the rest goes through."""
        excluded = TopicFilter(excluded=('cube.gyro',))

        self.assertFalse(excluded.shows('cube.gyro'))
        self.assertTrue(excluded.shows('cube.move'))


class StreamTailTestCase(unittest.TestCase):
    """What the client keeps of the stream while it reads it."""

    def setUp(self) -> None:
        """Read into a list, colorless, everything shown."""
        self.written: list[str] = []
        self.tail = StreamTail(
            Renderer(Paint(enabled=False), width=WIDTH),
            self.written.append,
            everything=True,
        )

    @property
    def text(self) -> str:
        """
        Everything the client wrote, as one piece.

        Returns:
            The blocks, joined the way a terminal shows them.

        """
        return '\n'.join(self.written)

    def test_the_session_is_announced_first(self) -> None:
        """A reader is told whose messages these are before any of them."""
        self.tail.dispatch(message('cube.move', {'move': 'R'}))

        self.assertIn('session a3f1c8d2', self.written[0])
        self.assertIn('cube.move', self.written[1])

    def test_a_session_is_announced_once(self) -> None:
        """The line belongs to the session, not to the message."""
        self.tail.dispatch(message('cube.move', {'move': 'R'}, 0))
        self.tail.dispatch(message('cube.move', {'move': 'U'}, 1))

        self.assertEqual(self.text.count('session a3f1c8d2'), 1)

    def test_a_new_session_is_announced_again(self) -> None:
        """A publisher that restarted is a stream that starts over."""
        self.tail.dispatch(message('cube.move', {'move': 'R'}))

        restarted = message('cube.move', {'move': 'U'})
        restarted['sid'] = 'ffffffff'
        self.tail.dispatch(restarted)

        self.assertIn('session ffffffff', self.text)
        self.assertEqual(self.tail.session_id, 'ffffffff')

    def test_a_new_session_is_never_timed_from_the_old_one(self) -> None:
        """Gaps belong to the session they were measured in."""
        self.tail.dispatch(message('cube.move', {'move': 'R'}, 0, STAMP))

        restarted = message('cube.move', {'move': 'U'}, 0, STAMP + 3600)
        restarted['sid'] = 'ffffffff'
        self.tail.dispatch(restarted)

        self.assertNotIn('+3600.000s', self.text)

    def test_the_gaps_are_measured_on_what_is_printed(self) -> None:
        """The cadence shown is the cadence of the blocks."""
        self.tail.dispatch(message('cube.move', {'move': 'R'}, 0, STAMP))
        self.tail.dispatch(
            message('cube.facelets', {'facelets': 'U'}, 1, STAMP + 0.5),
        )
        self.tail.dispatch(message('cube.move', {'move': 'U'}, 2, STAMP + 2))

        self.assertIn('+1.500s', self.text)
        self.assertIn('Δcube.move 2.000s', self.text)

    def test_the_gyroscope_is_held_back(self) -> None:
        """A block per gyroscope message is a window showing nothing else."""
        quiet = StreamTail(
            Renderer(Paint(enabled=False), width=WIDTH),
            self.written.append,
        )

        quiet.dispatch(message(GYRO, {'quaternion': {'w': 1.0}}))

        self.assertNotIn(GYRO, self.text)

    def test_everything_shows_the_gyroscope(self) -> None:
        """--all is what gives the one topic held back up."""
        self.tail.dispatch(message(GYRO, {'quaternion': {'w': 1.0}}))

        self.assertIn(GYRO, self.text)

    def test_a_break_in_the_sequence_is_a_loss(self) -> None:
        """The two prefixes cover everything, so a hole is a loss."""
        self.tail.dispatch(message('cube.move', {'move': 'R'}, 0))
        self.tail.dispatch(message('cube.move', {'move': 'U'}, 13))

        self.assertIn('12 messages lost', self.text)

    def test_a_sequence_that_follows_is_no_loss(self) -> None:
        """Nothing is reported of a stream that lost nothing."""
        self.tail.dispatch(message('cube.move', {'move': 'R'}, 0))
        self.tail.dispatch(message('cube.move', {'move': 'U'}, 1))

        self.assertNotIn('lost', self.text)

    def test_a_loss_hidden_by_a_filter_is_reported(self) -> None:
        """A message held back was published all the same."""
        quiet = StreamTail(
            Renderer(Paint(enabled=False), width=WIDTH),
            self.written.append,
        )

        quiet.dispatch(message('cube.move', {'move': 'R'}, 0))
        quiet.dispatch(message(GYRO, {'quaternion': {'w': 1.0}}, 5))
        quiet.dispatch(message('cube.move', {'move': 'U'}, 6))

        self.assertIn('4 messages lost', self.text)
        self.assertNotIn(GYRO, self.text)

    def test_a_message_with_no_sequence_is_survived(self) -> None:
        """An envelope missing what it is counted by is still read."""
        broken = message('cube.move', {'move': 'R'})
        del broken['seq']

        self.tail.dispatch(broken)

        self.assertIn('cube.move', self.text)

    def test_the_end_of_a_session_closes_it(self) -> None:
        """The farewell is drawn across, under the block that carries it."""
        self.tail.dispatch(message('cube.move', {'move': 'R'}, 0))
        self.tail.dispatch(
            message(SESSION_END_TOPIC, {'reason': 'closed'}, 1),
        )

        self.assertIn(SESSION_END_TOPIC, self.written[-2])
        self.assertIn('end of session a3f1c8d2', self.written[-1])
        self.assertIn('closed', self.written[-1])

    def test_a_tail_goes_on_reading_after_the_end(self) -> None:
        """A publisher that comes back is read by the tail already there."""
        self.tail.dispatch(
            message(SESSION_END_TOPIC, {'reason': 'interrupted'}, 0),
        )

        restarted = message('cube.move', {'move': 'R'}, 0)
        restarted['sid'] = 'ffffffff'
        self.tail.dispatch(restarted)

        self.assertIn('session ffffffff', self.text)
        self.assertIn('cube.move', self.text)
        self.assertNotIn('lost', self.text)

    def test_another_protocol_is_never_read(self) -> None:
        """A stream this client does not speak is left alone."""
        with self.assertLogs('term_timer_clients.tail.client', 'WARNING'):
            self.tail.dispatch(envelope('cube.move', version=2))

        self.assertEqual(self.written, [])

    def test_another_protocol_is_reported_once(self) -> None:
        """A foreign stream says so in every one of its messages."""
        with self.assertLogs(
                'term_timer_clients.tail.client', 'WARNING',
        ) as logs:
            self.tail.dispatch(envelope('cube.move', version=2))
            self.tail.dispatch(envelope('cube.move', version=2))

        self.assertEqual(len(logs.output), 1)

    def test_nothing_is_kept_unless_somewhere_to_keep_it(self) -> None:
        """A reader is a reader, and writes nothing down by itself."""
        self.assertIsNone(self.tail.recorder)

    def test_what_arrives_is_kept_whatever_is_read(self) -> None:
        """Reading and recording are two gestures, and two filters."""
        kept: list[dict[str, Any]] = []
        tail = StreamTail(
            Renderer(Paint(enabled=False), width=WIDTH),
            self.written.append,
            kept.append,
        )

        tail.dispatch(message('cube.move', {'move': 'R'}))
        tail.dispatch(message(GYRO, {'quaternion': {'w': 1}}, 1))

        self.assertEqual(
            [envelope_['topic'] for envelope_ in kept],
            ['cube.move', GYRO],
        )
        self.assertNotIn(GYRO, self.text)

    def test_another_protocol_is_kept_all_the_same(self) -> None:
        """A stream nobody can read is what a capture is opened for."""
        kept: list[dict[str, Any]] = []
        tail = StreamTail(
            Renderer(Paint(enabled=False), width=WIDTH),
            self.written.append,
            kept.append,
        )

        with self.assertLogs('term_timer_clients.tail.client', 'WARNING'):
            tail.dispatch(envelope('cube.move', version=2))

        self.assertEqual(len(kept), 1)
        self.assertEqual(self.written, [])


class StreamTailFilterTestCase(unittest.TestCase):
    """What --topic and --exclude narrow the reading down to."""

    def setUp(self) -> None:
        """Read into a list, colorless."""
        self.written: list[str] = []

    @property
    def text(self) -> str:
        """
        Everything the client wrote, as one piece.

        Returns:
            The blocks, joined the way a terminal shows them.

        """
        return '\n'.join(self.written)

    def test_a_topic_filter_narrows_what_is_shown(self) -> None:
        """--topic keeps only what a reader asked to see."""
        tail = StreamTail(
            Renderer(Paint(enabled=False), width=WIDTH),
            self.written.append,
            everything=True,
            topic_filter=TopicFilter(topics=('session.',)),
        )

        tail.dispatch(message('cube.move', {'move': 'R'}, 0))
        tail.dispatch(message('session.state', {'state': 'solving'}, 1))

        self.assertNotIn('cube.move', self.text)
        self.assertIn('session.state', self.text)

    def test_an_exclusion_holds_a_topic_back(self) -> None:
        """--exclude drops a topic on top of what --all already shows."""
        tail = StreamTail(
            Renderer(Paint(enabled=False), width=WIDTH),
            self.written.append,
            everything=True,
            topic_filter=TopicFilter(excluded=('cube.facelets',)),
        )

        tail.dispatch(message('cube.move', {'move': 'R'}, 0))
        tail.dispatch(message('cube.facelets', {'facelets': 'U'}, 1))

        self.assertIn('cube.move', self.text)
        self.assertNotIn('cube.facelets', self.text)

    def test_the_gyroscope_stays_held_back_under_a_filter(self) -> None:
        """--topic narrows what --all shows, it does not stand for it."""
        tail = StreamTail(
            Renderer(Paint(enabled=False), width=WIDTH),
            self.written.append,
            topic_filter=TopicFilter(topics=(GYRO,)),
        )

        tail.dispatch(message(GYRO, {'quaternion': {'w': 1.0}}, 0))

        self.assertNotIn(GYRO, self.text)

    def test_a_loss_hidden_by_a_topic_filter_is_reported(self) -> None:
        """A message held back by --topic was published all the same."""
        tail = StreamTail(
            Renderer(Paint(enabled=False), width=WIDTH),
            self.written.append,
            everything=True,
            topic_filter=TopicFilter(topics=('cube.move',)),
        )

        tail.dispatch(message('cube.move', {'move': 'R'}, 0))
        tail.dispatch(message('cube.facelets', {'facelets': 'U'}, 5))
        tail.dispatch(message('cube.move', {'move': 'U'}, 6))

        self.assertIn('4 messages lost', self.text)
        self.assertNotIn('cube.facelets', self.text)


class CaptureTestCase(unittest.TestCase):
    """Real captures, read the way a reader would see them."""

    def setUp(self) -> None:
        """Read a capture into a list, colorless."""
        self.written: list[str] = []
        self.tail = StreamTail(
            Renderer(Paint(enabled=False), width=WIDTH),
            self.written.append,
            everything=True,
        )

    def replay(self, name: str) -> str:
        """
        Play a capture through the client.

        Args:
            name: Name of the capture file.

        Returns:
            Everything the client wrote.

        """
        for envelope_ in envelopes(name):
            self.tail.dispatch(envelope_)

        return '\n'.join(self.written)

    def test_a_capture_shows_its_moves(self) -> None:
        """What the cube turned is what the reader came for."""
        text = self.replay('sexy-move-UF.json')

        for move in ('R', 'U', "R'", "U'"):
            with self.subTest(move=move):
                self.assertIn(f'move             { move }\n', f'{ text }\n')

    def test_a_capture_never_writes_past_the_width(self) -> None:
        """A block wider than the terminal is a block that wraps twice."""
        self.replay('Y-Tperm-Y.json')

        for line in self.written:
            with self.subTest(line=line):
                self.assertLessEqual(
                    max(len(part) for part in line.split('\n')),
                    WIDTH,
                )

    def test_a_capture_of_rotations_is_all_gyroscope(self) -> None:
        """A cube turned in the hand publishes no move at all."""
        quiet = StreamTail(
            Renderer(Paint(enabled=False), width=WIDTH),
            self.written.append,
        )

        for envelope_ in envelopes('Y-UF.json'):
            quiet.dispatch(envelope_)

        self.assertNotIn('cube.move', '\n'.join(self.written))


class MainTestCase(unittest.TestCase):
    """The command line of the client, and what it assembles."""

    def test_the_help_is_formatted(self) -> None:
        """The parser of the client is the one of the clients."""
        help_text = entry.build_parser({}).format_help()

        self.assertIn('Usage:', help_text)
        self.assertIn('Options:', help_text)

    def test_the_endpoint_is_required_without_a_configuration(self) -> None:
        """What is missing then is the stream itself."""
        with self.assertRaises(SystemExit):
            entry.build_parser({}).parse_args([])

    def test_the_configured_endpoint_is_the_default(self) -> None:
        """A client finds the session it listens to on its own."""
        options = entry.build_parser(CONFIG).parse_args([])

        self.assertEqual(options.endpoint, ENDPOINT)

    def test_the_command_line_wins(self) -> None:
        """What is typed says otherwise, and is what happens."""
        other = 'tcp://127.0.0.1:5999'
        options = entry.build_parser(CONFIG).parse_args(['-e', other])

        self.assertEqual(options.endpoint, other)

    def test_a_broken_endpoint_is_refused(self) -> None:
        """A subscriber given one would wait in silence forever."""
        with self.assertRaises(SystemExit):
            entry.build_parser(CONFIG).parse_args(['-e', 'nowhere'])

    def test_the_flags_default_to_the_quiet_reading(self) -> None:
        """Nothing is asked for that was not asked for."""
        options = entry.build_parser(CONFIG).parse_args([])

        self.assertFalse(options.everything)
        self.assertFalse(options.colorless)

    def test_the_flags_are_read(self) -> None:
        """Both of them are answered."""
        options = entry.build_parser(CONFIG).parse_args(
            ['--all', '--no-color'],
        )

        self.assertTrue(options.everything)
        self.assertTrue(options.colorless)

    def test_the_filters_default_to_nothing_narrowed(self) -> None:
        """Nothing is asked for that was not asked for."""
        options = entry.build_parser(CONFIG).parse_args([])

        self.assertEqual(options.topics, [])
        self.assertEqual(options.excluded, [])

    def test_a_topic_is_repeatable(self) -> None:
        """Several prefixes are asked for one flag at a time."""
        options = entry.build_parser(CONFIG).parse_args(
            ['--topic', 'cube.move', '--topic', 'session.'],
        )

        self.assertEqual(options.topics, ['cube.move', 'session.'])

    def test_an_exclusion_is_repeatable(self) -> None:
        """--exclude takes as many prefixes as --topic does."""
        options = entry.build_parser(CONFIG).parse_args(
            ['--exclude', 'cube.gyro', '--exclude', 'cube.battery'],
        )

        self.assertEqual(options.excluded, ['cube.gyro', 'cube.battery'])

    def test_topic_and_exclude_refuse_each_other(self) -> None:
        """Two ways of narrowing the same stream are one too many."""
        with self.assertRaises(SystemExit):
            entry.build_parser(CONFIG).parse_args(
                ['--topic', 'cube.', '--exclude', 'cube.gyro'],
            )

    def test_the_tail_is_assembled_with_its_filter(self) -> None:
        """What is typed on the command line is what the reader gets."""
        options = entry.build_parser(CONFIG).parse_args(
            ['--topic', 'cube.move', '--topic', 'session.'],
        )

        with patch.dict(os.environ, {}, clear=True):
            tail = entry.build_tail(options, io.StringIO())

        self.assertEqual(
            tail.topic_filter,
            TopicFilter(('cube.move', 'session.')),
        )

    def test_a_block_is_written_whole_and_flushed(self) -> None:
        """A tail left to its own buffering says nothing for pages."""
        stream = MagicMock()

        entry.build_writer(stream)('one\ntwo')

        self.assertEqual(stream.write.call_args.args, ('one\ntwo\n',))
        stream.flush.assert_called_once_with()

    def test_the_tail_is_assembled_on_the_output(self) -> None:
        """A client writing to a file writes no escape into it."""
        options = entry.build_parser(CONFIG).parse_args(['--all'])

        with patch.dict(os.environ, {}, clear=True):
            tail = entry.build_tail(options, io.StringIO())

        self.assertTrue(tail.everything)
        self.assertFalse(tail.renderer.paint.enabled)

    def test_main_reads_the_stream_until_it_is_stopped(self) -> None:
        """One reader, one writer, and the main thread to itself."""
        stream = MagicMock()
        stream.receive.side_effect = KeyboardInterrupt

        with (
            patch.object(sys, 'argv', ['tt-tail', '-e', ENDPOINT]),
            patch.object(entry, 'load_config', return_value={}),
            patch.object(entry, 'EventStream', return_value=stream) as built,
        ):
            code = entry.main()

        self.assertEqual(code, 0)
        self.assertEqual(built.call_args.args[0], ENDPOINT)
        self.assertEqual(built.call_args.args[1], entry.PREFIXES)
        stream.open.assert_called_once_with()
        stream.close.assert_called_once_with()

    def test_main_subscribes_to_both_planes(self) -> None:
        """A tail of one plane is a tail of half a session."""
        self.assertEqual(entry.PREFIXES, ('cube.', 'session.'))


class RecordTestCase(unittest.TestCase):
    """Where the stream is kept, and what is kept of it."""

    def test_nothing_is_recorded_unless_it_is_asked_for(self) -> None:
        """A tail keeps nothing of what it read by itself."""
        options = entry.build_parser(CONFIG).parse_args([])

        self.assertIsNone(options.record)

    def test_the_file_is_read_the_way_an_endpoint_is(self) -> None:
        """A tilde typed by hand is a home rather than a directory."""
        options = entry.build_parser(CONFIG).parse_args(
            ['--record', '~/stream.jsonl'],
        )

        self.assertEqual(options.record, Path.home() / 'stream.jsonl')

    def test_an_envelope_is_kept_whole_and_flushed(self) -> None:
        """What is still in a buffer is what nobody has."""
        stream = MagicMock()
        message_ = envelope('cube.move', {'move': 'R'})

        entry.build_recorder(stream)(message_)

        line = stream.write.call_args.args[0]
        self.assertTrue(line.endswith('\n'))
        self.assertEqual(json.loads(line), message_)
        stream.flush.assert_called_once_with()

    def test_a_file_asked_for_is_appended_to(self) -> None:
        """A tail started again never costs the capture before it."""
        with TemporaryDirectory() as directory:
            recording = Path(directory) / 'stream.jsonl'
            recording.write_text('{ "kept": true }\n')

            options = entry.build_parser(CONFIG).parse_args(
                ['--record', str(recording)],
            )

            with ExitStack() as stack:
                recorder = entry.open_recording(options, stack)

                if recorder is None:
                    self.fail('The recording was asked for')

                recorder(envelope('cube.move', {'move': 'R'}))

            lines = recording.read_text().splitlines()

        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[1])['topic'], 'cube.move')

    def test_the_tail_is_handed_what_keeps_the_stream(self) -> None:
        """What a client writes down is injected like where it writes."""
        options = entry.build_parser(CONFIG).parse_args([])
        recorder = MagicMock()

        tail = entry.build_tail(options, io.StringIO(), recorder)

        self.assertIs(tail.recorder, recorder)

    def test_a_recording_nowhere_stops_the_client(self) -> None:
        """One found missing the day it is read would be too late."""
        with TemporaryDirectory() as directory:
            nowhere = Path(directory) / 'missing' / 'stream.jsonl'

            with (
                patch.object(
                    sys, 'argv',
                    ['tt-tail', '-e', ENDPOINT, '-r', str(nowhere)],
                ),
                patch.object(entry, 'load_config', return_value={}),
                patch.object(entry, 'EventStream') as built,
                self.assertLogs('term_timer_clients.tail.main', 'ERROR'),
            ):
                code = entry.main()

        self.assertEqual(code, 1)
        built.assert_not_called()

    def test_main_keeps_the_stream_where_it_was_asked_to(self) -> None:
        """The whole of it, from the socket to the line on the disk."""
        published = [envelope('cube.move', {'move': 'R'})]

        def receive(handler: Callable[[dict[str, Any]], None]) -> None:
            if not published:
                raise KeyboardInterrupt

            handler(published.pop())

        stream = MagicMock()
        stream.receive.side_effect = receive

        with TemporaryDirectory() as directory:
            recording = Path(directory) / 'stream.jsonl'

            with (
                patch.object(
                    sys, 'argv',
                    ['tt-tail', '-e', ENDPOINT, '-r', str(recording)],
                ),
                patch.object(entry, 'load_config', return_value={}),
                patch.object(entry, 'EventStream', return_value=stream),
                patch.object(sys, 'stdout', io.StringIO()),
            ):
                code = entry.main()

            lines = recording.read_text().splitlines()

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(lines[0])['topic'], 'cube.move')
