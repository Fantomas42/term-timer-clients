"""The orders a window takes from the process that opened it."""
import logging
import threading
from collections.abc import Callable
from typing import IO
from typing import Final

logger = logging.getLogger(__name__)

Obeyer = Callable[[str], None]

# What one process asks of a window another one holds. Three words and
# a line each, because that is the whole of what there is to say: a
# window is on the screen or it is not, and one day it is over.
SHOW_ORDER: Final = 'show'

HIDE_ORDER: Final = 'hide'

CLOSE_ORDER: Final = 'close'

# What separates two orders on the pipe. A line and not a length: the
# channel is read by hand as much as by a client - a window is driven
# from a shell to be watched being driven - and a word typed into a
# terminal is a word followed by a newline.
ORDER_SEPARATOR: Final = '\n'

# How long the reader is waited for once the pipe is done, in seconds.
# It is already returning by then, the end of the pipe being what ended
# it, and what is bounded here is a reader that is not.
READER_TIMEOUT: Final = 1.0


def write_order(pipe: IO[str], order: str) -> bool:
    """
    Ask a window for one thing, over the pipe it takes its orders on.

    Flushed on the spot rather than left to a buffer: an order is
    written because somebody clicked, and a window shown at the next
    flush is a window shown for no reason anybody can see.

    Args:
        pipe: The channel the window reads its orders on.
        order: What is asked of it.

    Returns:
        True when the order was handed over, False when the pipe is
        gone - a window that died is a window that answers nothing, and
        it is the caller that knows what to make of it.

    """
    try:
        pipe.write(f'{ order }{ ORDER_SEPARATOR }')
        pipe.flush()
    except (OSError, ValueError) as error:
        logger.debug('Cannot order a window about: %s', error)
        return False

    return True


def read_orders(pipe: IO[str], obey: Obeyer) -> None:
    """
    Read the orders of a pipe until there is nobody left to give them.

    **The end of the pipe is an order of its own**: a window driven
    from outside is a window whose reason to be open is the process
    that opened it, so that process going away closes it rather than
    leaving a window nothing can ever reach again. It is the one thing
    a caller cannot ask for by forgetting to.

    An order this window knows nothing about is ignored rather than
    guessed at, which is what a client does with a topic it does not
    know.

    Args:
        pipe: The channel the orders arrive on.
        obey: What every order is handed to.

    """
    try:
        for line in pipe:
            order = line.strip()

            if order:
                obey(order)
    except (OSError, ValueError) as error:
        logger.debug('End of the orders: %s', error)

    obey(CLOSE_ORDER)


class OrderReader:
    """
    A pipe of orders, read in a thread of its own.

    The very arrangement the event stream is read in, and for the very
    same reason: a window belongs to the thread that opened it, so what
    arrives here is only ever *written down*, and the window reads it
    at the next turn of its loop.
    """

    def __init__(self, pipe: IO[str], obey: Obeyer) -> None:
        """
        Prepare a reader, reading nothing yet.

        Args:
            pipe: The channel the orders arrive on.
            obey: What every order is handed to.

        """
        self.pipe = pipe
        self.obey = obey
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        """Read the orders in a thread of its own, until the pipe ends."""
        self.thread = threading.Thread(
            target=read_orders,
            args=(self.pipe, self.obey),
            name='window-orders',
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        """
        Stop taking orders, and wait for the reader.

        The pipe is closed under the reader rather than asked to stop,
        a thread waiting on a line having nothing else to look at. A
        pipe this process does not own - the standard input of a
        window opened by hand - is closed all the same: what is given
        back is the end of this client and nothing else.
        """
        try:
            self.pipe.close()
        except (OSError, ValueError) as error:
            logger.debug('Cannot close the orders: %s', error)

        thread, self.thread = self.thread, None

        if thread is not None:
            thread.join(timeout=READER_TIMEOUT)
