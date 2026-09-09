"""
Tests for the orders a window takes from the process that opened it.

The pipe is a real one wherever a thread reads it: what is being
asserted is that the end of it is heard, and a stream standing in for a
pipe is a stream that ends whenever the test says so.
"""
import io
import os
import threading
import unittest
from typing import IO
from unittest.mock import MagicMock

from term_timer_clients.orders import CLOSE_ORDER
from term_timer_clients.orders import HIDE_ORDER
from term_timer_clients.orders import SHOW_ORDER
from term_timer_clients.orders import OrderReader
from term_timer_clients.orders import read_orders
from term_timer_clients.orders import write_order

# How long a reader is given to hear what was just written to it, in
# seconds. It is a pipe on the same machine, so anything at all is
# enough: what it bounds is a suite hanging on a thread that will never
# answer.
HEARING_TIMEOUT = 5.0


def pipe_pair() -> tuple[IO[str], IO[str]]:
    """
    Open a real pipe, as a process opened by another one is handed one.

    Returns:
        The reading end and the writing end.

    """
    reading, writing = os.pipe()

    return (
        os.fdopen(reading, 'r'),
        os.fdopen(writing, 'w'),
    )


class WriteOrderTestCase(unittest.TestCase):
    """What is written when a window is asked for something."""

    def test_an_order_is_a_word_and_a_line(self) -> None:
        """A word typed into a terminal is a word followed by a newline."""
        pipe = io.StringIO()

        self.assertTrue(write_order(pipe, SHOW_ORDER))
        self.assertEqual(pipe.getvalue(), f'{ SHOW_ORDER }\n')

    def test_an_order_is_written_on_the_spot(self) -> None:
        """A window shown at the next flush is shown for no visible reason."""
        reading, writing = pipe_pair()
        self.addCleanup(reading.close)

        write_order(writing, SHOW_ORDER)
        writing.close()

        self.assertEqual(reading.read(), f'{ SHOW_ORDER }\n')

    def test_a_pipe_that_is_gone_is_reported(self) -> None:
        """A window that died is a window that answers nothing."""
        pipe = io.StringIO()
        pipe.close()

        self.assertFalse(write_order(pipe, SHOW_ORDER))


class ReadOrdersTestCase(unittest.TestCase):
    """What a window makes of the lines it is handed."""

    def setUp(self) -> None:
        """Hold what the orders were obeyed as."""
        self.obeyed: list[str] = []

    def test_every_order_is_handed_over_in_turn(self) -> None:
        """A pipe of orders is read as it was written."""
        read_orders(
            io.StringIO(f'{ SHOW_ORDER }\n{ HIDE_ORDER }\n'),
            self.obeyed.append,
        )

        self.assertEqual(
            self.obeyed, [SHOW_ORDER, HIDE_ORDER, CLOSE_ORDER],
        )

    def test_a_line_with_nothing_on_it_is_no_order(self) -> None:
        """A pipe written to by hand is a pipe with blank lines in it."""
        read_orders(
            io.StringIO(f'\n  \n{ SHOW_ORDER }  \n'), self.obeyed.append,
        )

        self.assertEqual(self.obeyed, [SHOW_ORDER, CLOSE_ORDER])

    def test_the_end_of_the_pipe_is_an_order_of_its_own(self) -> None:
        """A window nothing can reach again is a window that has to go."""
        read_orders(io.StringIO(''), self.obeyed.append)

        self.assertEqual(self.obeyed, [CLOSE_ORDER])

    def test_a_pipe_taken_away_closes_the_window_all_the_same(self) -> None:
        """A process killed outright is the very same absence."""
        pipe = io.StringIO(f'{ SHOW_ORDER }\n')
        pipe.close()

        with self.assertLogs('term_timer_clients.orders', 'DEBUG'):
            read_orders(pipe, self.obeyed.append)

        self.assertEqual(self.obeyed, [CLOSE_ORDER])


class OrderReaderTestCase(unittest.TestCase):
    """The pipe of orders, read in a thread of its own."""

    def setUp(self) -> None:
        """Hold a real pipe, and what the reader made of it."""
        self.reading, self.writing = pipe_pair()
        self.obeyed: list[str] = []
        self.heard = threading.Event()

        self.reader = OrderReader(self.reading, self.obey)
        self.addCleanup(self.reader.stop)

    def obey(self, order: str) -> None:
        """
        Take note of one order, and let the test know it arrived.

        Args:
            order: What was asked of the window.

        """
        self.obeyed.append(order)
        self.heard.set()

    def test_an_order_reaches_the_window_as_it_is_written(self) -> None:
        """A click is answered while the reader waits for the next one."""
        self.reader.start()

        write_order(self.writing, SHOW_ORDER)

        self.assertTrue(self.heard.wait(HEARING_TIMEOUT))
        self.assertEqual(self.obeyed, [SHOW_ORDER])

    def test_the_end_of_the_pipe_closes_the_window(self) -> None:
        """A tray taken away closes the window it opened, whatever took it."""
        self.reader.start()

        self.writing.close()

        self.assertTrue(self.heard.wait(HEARING_TIMEOUT))

        self.reader.stop()

        self.assertEqual(self.obeyed, [CLOSE_ORDER])

    def test_a_reader_that_never_started_is_stopped_all_the_same(self) -> None:
        """A window given back is given back whatever it was doing."""
        self.reader.stop()

        self.assertEqual(self.obeyed, [])

    def test_a_pipe_closed_twice_is_no_error(self) -> None:
        """A client is given back once, and never held back by the second."""
        self.reader.stop()
        self.reader.stop()

        self.assertIsNone(self.reader.thread)

    def test_a_pipe_that_will_not_close_holds_nothing_back(self) -> None:
        """A client is given back whatever the channel it was reading."""
        pipe = MagicMock()
        pipe.close.side_effect = OSError('gone')

        with self.assertLogs('term_timer_clients.orders', 'DEBUG'):
            OrderReader(pipe, self.obey).stop()

    def tearDown(self) -> None:
        """Give the writing end back, whatever the test did with it."""
        if not self.writing.closed:
            self.writing.close()


if __name__ == '__main__':
    unittest.main()
