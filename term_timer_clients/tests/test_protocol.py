"""
Tests for the reading of the event stream.

Nothing here knows what a cube is: a publisher binds a socket of its
own, a subscription reads what comes out of it, and what an envelope
has to look like is checked frame by frame.
"""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import zmq

from term_timer_clients.protocol import EventStream
from term_timer_clients.protocol import parse_endpoint
from term_timer_clients.tests.fixtures import envelope

# Time left to a subscription to reach the publisher, the "slow joiner"
# of ZeroMQ biting the test before anything else
HANDSHAKE_DELAY = 0.3

# Time given to the reader thread to hear a message
DELIVERY_TIMEOUT = 2.0


class EndpointTestCase(unittest.TestCase):
    """How the two ends of the stream spell an endpoint."""

    def test_endpoint_is_kept_as_it_is(self) -> None:
        """An endpoint naming a transport goes through untouched."""
        self.assertEqual(
            parse_endpoint('tcp://127.0.0.1:5555'),
            'tcp://127.0.0.1:5555',
        )

    def test_endpoint_is_stripped(self) -> None:
        """What surrounds an endpoint is not part of it."""
        self.assertEqual(
            parse_endpoint('  tcp://127.0.0.1:5555  '),
            'tcp://127.0.0.1:5555',
        )

    def test_ipc_path_is_expanded(self) -> None:
        """The tilde of an ipc endpoint names a home, not a directory."""
        self.assertEqual(
            parse_endpoint('ipc://~/.term_timer/cube.ipc'),
            f'ipc://{ Path.home() }/.term_timer/cube.ipc',
        )

    def test_endpoint_without_a_transport(self) -> None:
        """What names no transport is no endpoint."""
        for token in ('cube.ipc', '~/.term_timer/cube.ipc', 'ipc://', '', '  '):
            with self.subTest(token=token):
                self.assertEqual(parse_endpoint(token), '')


class EventStreamDecodeTestCase(unittest.TestCase):
    """What a pair of frames has to look like to be read."""

    def test_decode_reads_an_envelope(self) -> None:
        """A well formed message gives its envelope back."""
        message = EventStream.decode(
            [b'cube.move', json.dumps(envelope('cube.move')).encode('utf-8')],
        )

        self.assertIsNotNone(message)
        self.assertEqual(message['topic'], 'cube.move')  # type: ignore[index]

    def test_decode_drops_a_lone_frame(self) -> None:
        """A message that is not a topic and a payload is dropped."""
        self.assertIsNone(EventStream.decode([b'cube.move']))

    def test_decode_drops_broken_json(self) -> None:
        """A payload that is not JSON is dropped."""
        self.assertIsNone(EventStream.decode([b'cube.move', b'{']))

    def test_decode_drops_what_is_not_an_object(self) -> None:
        """A payload that is not an envelope is dropped."""
        self.assertIsNone(EventStream.decode([b'cube.move', b'[1]']))


class EventStreamTestCase(unittest.TestCase):
    """The subscription, on real sockets and a real thread."""

    def setUp(self) -> None:
        """Prepare an endpoint of its own and a publisher on it."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        self.endpoint = f'ipc://{ Path(directory.name) / "cube.ipc" }'

        self.context = zmq.Context.instance()
        self.publisher: zmq.Socket[bytes] = self.context.socket(zmq.PUB)
        self.publisher.setsockopt(zmq.LINGER, 0)
        self.publisher.bind(self.endpoint)
        self.addCleanup(self.publisher.close)

        self.stream = EventStream(self.endpoint)
        self.addCleanup(self.stream.stop)

        self.received: list[dict[str, Any]] = []
        self.heard = threading.Event()

    def collect(self, message: dict[str, Any]) -> None:
        """
        Keep a message, and tell the test one arrived.

        Args:
            message: The envelope that was read.

        """
        self.received.append(message)
        self.heard.set()

    def send(self, topic: str) -> None:
        """
        Publish one well formed message on the endpoint under test.

        Args:
            topic: Topic of the message.

        """
        payload = json.dumps(envelope(topic))

        self.publisher.send_multipart(
            [topic.encode('utf-8'), payload.encode('utf-8')],
        )

    def test_receive_without_a_socket(self) -> None:
        """A stream that was never opened reads nothing."""
        self.assertFalse(self.stream.receive(self.collect))

    def test_receive_times_out_on_a_silent_stream(self) -> None:
        """A stream nobody talks on gives the loop its hand back."""
        self.stream.open()

        self.assertFalse(self.stream.receive(self.collect))

    def test_opening_twice_keeps_the_socket(self) -> None:
        """An open stream is not opened a second time."""
        self.stream.open()
        socket = self.stream.socket

        self.stream.open()

        self.assertIs(self.stream.socket, socket)

    def test_messages_reach_the_handler(self) -> None:
        """What is published reaches the handler of the stream."""
        self.stream.start(self.collect)
        time.sleep(HANDSHAKE_DELAY)

        self.send('cube.move')

        self.assertTrue(self.heard.wait(DELIVERY_TIMEOUT))
        self.assertEqual(self.received[0]['topic'], 'cube.move')

    def test_session_topics_are_left_on_the_wire(self) -> None:
        """The subscription filters on the hardware plane alone."""
        self.stream.start(self.collect)
        time.sleep(HANDSHAKE_DELAY)

        self.send('session.record')
        self.send('cube.move')

        self.assertTrue(self.heard.wait(DELIVERY_TIMEOUT))
        self.assertEqual(
            [message['topic'] for message in self.received],
            ['cube.move'],
        )

    def test_a_handler_that_raises_does_not_end_the_stream(self) -> None:
        """A message that cannot be handled costs only that message."""
        calls: list[str] = []

        def handler(message: dict[str, Any]) -> None:
            calls.append(message['topic'])
            self.heard.set()
            msg = 'broken handler'
            raise RuntimeError(msg)

        self.stream.start(handler)
        time.sleep(HANDSHAKE_DELAY)

        with self.assertLogs('term_timer_clients.protocol', 'ERROR'):
            self.send('cube.move')
            self.assertTrue(self.heard.wait(DELIVERY_TIMEOUT))
            self.heard.clear()

            self.send('cube.facelets')
            self.assertTrue(self.heard.wait(DELIVERY_TIMEOUT))

        self.assertEqual(len(calls), 2)

    def test_a_broken_message_is_dropped(self) -> None:
        """What cannot be read never reaches the handler."""
        self.stream.start(self.collect)
        time.sleep(HANDSHAKE_DELAY)

        self.publisher.send_multipart([b'cube.move', b'{'])
        self.send('cube.facelets')

        self.assertTrue(self.heard.wait(DELIVERY_TIMEOUT))
        self.assertEqual(
            [message['topic'] for message in self.received],
            ['cube.facelets'],
        )

    def test_a_socket_error_ends_the_loop(self) -> None:
        """A socket that gives up under the reader ends its loop."""
        self.stream.open()
        self.stream.running = True

        with (
            patch.object(self.stream, 'receive', side_effect=zmq.ZMQError),
            self.assertLogs('term_timer_clients.protocol', 'DEBUG'),
        ):
            self.stream.listen(self.collect)

        self.assertEqual(self.received, [])

    def test_a_closed_socket_ends_the_loop(self) -> None:
        """A socket closed under the reader ends its loop."""
        self.stream.open()
        self.stream.running = True
        self.stream.close()

        self.stream.listen(self.collect)

        self.assertEqual(self.received, [])

    def test_stopping_an_idle_stream(self) -> None:
        """Stopping what was never started is a no-op."""
        self.stream.stop()

        self.assertIsNone(self.stream.socket)
        self.assertIsNone(self.stream.thread)
