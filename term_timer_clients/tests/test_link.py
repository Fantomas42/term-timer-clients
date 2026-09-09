"""
Tests for what the stream says of the cube, before anything shows it.

Nothing here holds a viewer or an icon: the rules asserted on are the
ones every client showing a cube reads the same way, which is the whole
reason they live in one place.
"""
import unittest

from term_timer_clients.link import CubeLink
from term_timer_clients.protocol import SESSION_END_TOPIC
from term_timer_clients.tests.fixtures import envelope

LINK_LOGGER = 'term_timer_clients.link'


class LinkTestCase(unittest.TestCase):
    """Base case reading a stream that has said nothing yet."""

    def setUp(self) -> None:
        """Start on a link nothing has been published to."""
        self.link = CubeLink()


class ForeignStreamTestCase(LinkTestCase):
    """What a client does with a stream it cannot read."""

    def test_unknown_protocol_is_ignored(self) -> None:
        """A message of another protocol version does nothing."""
        self.link.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}, version=2),
        )

        self.assertEqual(self.link.hardware, '')
        self.assertFalse(self.link.connected)

    def test_unknown_protocol_is_reported_once(self) -> None:
        """A foreign stream is named once, not on every message."""
        with self.assertLogs(LINK_LOGGER, 'WARNING') as logs:
            self.link.dispatch(envelope('cube.move', version=2))
            self.link.dispatch(envelope('cube.move', version=2))

        self.assertEqual(len(logs.output), 1)

    def test_a_stream_coming_back_to_the_protocol_is_read_again(self) -> None:
        """What this client can read is read, whatever came before."""
        self.link.dispatch(envelope('cube.move', version=2))
        self.link.dispatch(envelope('cube.move', {'move': 'R'}))

        self.assertTrue(self.link.connected)


class SessionTestCase(LinkTestCase):
    """What the envelope says before its payload is read at all."""

    def test_session_is_followed(self) -> None:
        """The session identifier of the stream is remembered."""
        self.link.dispatch(envelope('cube.move', {'move': 'R'}))

        self.assertEqual(self.link.session_id, 'a3f1c8d2')

    def test_a_new_session_throws_the_old_cube_away(self) -> None:
        """A publisher that restarted is not the one that was heard."""
        self.link.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}),
        )
        self.link.dispatch(envelope('cube.battery', {'level': 80}))

        self.link.dispatch(
            envelope('cube.gyro', session_id='ffffffff'),
        )

        self.assertEqual(self.link.session_id, 'ffffffff')
        self.assertEqual(self.link.hardware, '')
        self.assertEqual(self.link.battery, '')

    def test_the_first_session_is_not_a_restart(self) -> None:
        """A client that has heard nothing has nothing to start over."""
        with self.assertNoLogs(LINK_LOGGER, 'INFO'):
            self.link.dispatch(envelope('cube.move', {'move': 'R'}))

    def test_a_new_session_is_reported(self) -> None:
        """A reader of the logs is told the stream started over."""
        self.link.dispatch(envelope('cube.move', {'move': 'R'}))

        with self.assertLogs(LINK_LOGGER, 'INFO'):
            self.link.dispatch(
                envelope('cube.move', {'move': 'R'}, session_id='ffffffff'),
            )

    def test_data_that_is_not_an_object_is_ignored(self) -> None:
        """A payload that is not an object is handed over as an empty one."""
        message = envelope('cube.hardware')
        message['data'] = ['GANi3']

        self.link.dispatch(message)

        self.assertEqual(self.link.hardware, '')


class SourceTestCase(LinkTestCase):
    """What command is publishing the stream."""

    def test_a_stream_that_said_nothing_names_no_source(self) -> None:
        """A client that has heard nothing has heard of no command."""
        self.assertEqual(self.link.source, '')

    def test_the_source_is_followed(self) -> None:
        """The command publishing the stream is remembered."""
        self.link.dispatch(
            envelope('cube.move', {'move': 'R'}, source='train'),
        )

        self.assertEqual(self.link.source, 'train')

    def test_the_source_survives_a_link_that_drops(self) -> None:
        """A command does not stop publishing just because the cube left."""
        self.link.dispatch(
            envelope('cube.move', {'move': 'R'}, source='train'),
        )
        self.link.dispatch(
            envelope(
                'cube.link',
                {'connected': False, 'reason': 'lost'},
                source='train',
            ),
        )

        self.assertEqual(self.link.source, 'train')

    def test_a_new_session_is_a_new_source(self) -> None:
        """A publisher that restarted may not be the same command."""
        self.link.dispatch(
            envelope('cube.move', {'move': 'R'}, source='train'),
        )
        self.link.dispatch(
            envelope(
                'cube.move',
                {'move': 'R'},
                session_id='ffffffff',
                source='solve',
            ),
        )

        self.assertEqual(self.link.source, 'solve')


class PresenceTestCase(LinkTestCase):
    """Whether there is a cube on the other end of the stream."""

    def test_a_stream_that_said_nothing_has_no_cube(self) -> None:
        """A client that has heard nothing has heard of no cube."""
        self.assertFalse(self.link.connected)

    def test_a_cube_talking_is_a_cube_that_is_there(self) -> None:
        """A cube never announces itself, so talking is what says it."""
        self.link.dispatch(envelope('cube.move', {'move': 'R'}))

        self.assertTrue(self.link.connected)

    def test_an_unknown_cube_topic_is_a_cube_that_is_there(self) -> None:
        """A topic added tomorrow is still the cube talking today."""
        self.link.dispatch(envelope('cube.temperature', {'celsius': 21}))

        self.assertTrue(self.link.connected)

    def test_the_session_plane_says_nothing_of_the_cube(self) -> None:
        """What term-timer knows alone is not the cube talking."""
        self.link.dispatch(envelope('session.start', {'kind': 'single'}))

        self.assertFalse(self.link.connected)

    def test_a_link_that_opens_is_a_cube_that_is_there(self) -> None:
        """The one topic that is not the cube talking still says it."""
        self.link.dispatch(
            envelope('cube.link', {'connected': True, 'reason': 'opened'}),
        )

        self.assertTrue(self.link.connected)

    def test_a_link_that_drops_takes_the_cube_away(self) -> None:
        """The only topic that ever says a cube is gone."""
        self.link.dispatch(envelope('cube.move', {'move': 'R'}))
        self.link.dispatch(
            envelope('cube.link', {'connected': False, 'reason': 'lost'}),
        )

        self.assertFalse(self.link.connected)

    def test_a_link_that_says_nothing_is_a_link_that_is_up(self) -> None:
        """A payload with no word on the link is not a cube leaving."""
        self.link.dispatch(envelope('cube.link', {'reason': 'opened'}))

        self.assertTrue(self.link.connected)

    def test_a_cube_that_comes_back_is_there_again(self) -> None:
        """A link is followed both ways, and never only down."""
        self.link.dispatch(
            envelope('cube.link', {'connected': False, 'reason': 'lost'}),
        )
        self.link.dispatch(
            envelope('cube.link', {'connected': True, 'reason': 'opened'}),
        )

        self.assertTrue(self.link.connected)


class IntroductionTestCase(LinkTestCase):
    """What the cube says of itself over a link that is up."""

    def test_the_cube_says_nothing_of_itself_at_first(self) -> None:
        """A stream that said nothing describes no cube."""
        self.assertEqual(self.link.parts, [])

    def test_the_cube_is_named(self) -> None:
        """What the cube calls itself is remembered."""
        self.link.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}),
        )

        self.assertEqual(self.link.parts, ['GANi3'])

    def test_the_charge_follows_the_name(self) -> None:
        """The cube is read in the order it introduces itself."""
        self.link.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}),
        )
        self.link.dispatch(envelope('cube.battery', {'level': 80}))

        self.assertEqual(self.link.parts, ['GANi3', '80%'])

    def test_a_charge_alone_is_read_alone(self) -> None:
        """A cube that gave one of the two is shown by that one."""
        self.link.dispatch(envelope('cube.battery', {'level': 80}))

        self.assertEqual(self.link.parts, ['80%'])

    def test_a_nameless_cube_is_ignored(self) -> None:
        """What says nothing about the cube leaves it as it was."""
        self.link.dispatch(envelope('cube.hardware', {'hardware_name': ''}))
        self.link.dispatch(envelope('cube.battery', {'level': 'high'}))

        self.assertEqual(self.link.parts, [])

    def test_a_cube_that_left_says_nothing_of_itself_any_more(self) -> None:
        """A name belongs to the link it was given over."""
        self.link.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}),
        )
        self.link.dispatch(envelope('cube.battery', {'level': 80}))

        self.link.dispatch(
            envelope('cube.link', {'connected': False, 'reason': 'lost'}),
        )

        self.assertEqual(self.link.parts, [])

    def test_what_is_shown_of_the_cube_is_not_what_is_held(self) -> None:
        """A caller writing in the parts writes in a list of its own."""
        self.link.dispatch(
            envelope('cube.hardware', {'hardware_name': 'GANi3'}),
        )

        self.link.parts.append('offline')

        self.assertEqual(self.link.parts, ['GANi3'])


class SessionEndTestCase(LinkTestCase):
    """The farewell of the publisher, and what it takes with it."""

    def test_a_session_that_ends_takes_the_cube_with_it(self) -> None:
        """A cube nobody publishes any more is a cube that is gone."""
        self.link.dispatch(envelope('cube.move', {'move': 'R'}))

        self.link.dispatch(envelope(SESSION_END_TOPIC, {'reason': 'closed'}))

        self.assertFalse(self.link.connected)

    def test_every_reason_ends_the_same_way(self) -> None:
        """What carried a session away leaves the very same silence."""
        for reason in ('closed', 'interrupted', 'crashed'):
            with self.subTest(reason=reason):
                link = CubeLink()
                link.dispatch(envelope('cube.move', {'move': 'R'}))

                link.dispatch(envelope(SESSION_END_TOPIC, {'reason': reason}))

                self.assertFalse(link.connected)

    def test_the_end_of_a_session_is_reported(self) -> None:
        """A reader of the logs is told why the stream stopped."""
        with self.assertLogs(LINK_LOGGER, 'INFO') as logs:
            self.link.dispatch(
                envelope(SESSION_END_TOPIC, {'reason': 'crashed'}),
            )

        self.assertIn('crashed', logs.output[0])

    def test_a_session_that_ends_on_nothing_is_reported_too(self) -> None:
        """A farewell with no reason in it is still a farewell."""
        with self.assertLogs(LINK_LOGGER, 'INFO') as logs:
            self.link.dispatch(envelope(SESSION_END_TOPIC))

        self.assertIn('no reason given', logs.output[0])

    def test_a_cube_comes_back_with_the_next_session(self) -> None:
        """A publisher that comes back is followed like any other."""
        self.link.dispatch(envelope(SESSION_END_TOPIC, {'reason': 'closed'}))

        self.link.dispatch(
            envelope('cube.move', {'move': 'R'}, session_id='ffffffff'),
        )

        self.assertTrue(self.link.connected)


if __name__ == '__main__':
    unittest.main()
