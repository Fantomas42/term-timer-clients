"""Entry point of the ``tt-tail`` client."""
import logging
import sys
from argparse import Namespace
from typing import IO

from term_timer_clients.argparser import LOG_FORMAT
from term_timer_clients.argparser import ArgumentParser
from term_timer_clients.argparser import add_endpoint_argument
from term_timer_clients.config import Config
from term_timer_clients.config import configured_endpoint
from term_timer_clients.config import load_config
from term_timer_clients.protocol import CUBE_PREFIX
from term_timer_clients.protocol import SESSION_PREFIX
from term_timer_clients.protocol import EventStream
from term_timer_clients.tail.ansi import build_paint
from term_timer_clients.tail.client import StreamTail
from term_timer_clients.tail.client import Writer
from term_timer_clients.tail.render import Renderer

logger = logging.getLogger(__name__)

# Both planes: what a cube does and what only term-timer knows are
# published apart, and a tail showing one of them would be a tail of
# half a session
PREFIXES = (CUBE_PREFIX, SESSION_PREFIX)


def build_parser(config: Config) -> ArgumentParser:
    """
    Describe what the client takes on its command line.

    The configuration is handed over rather than read here: it is what
    the defaults of the parser are made of, and a parser built on an
    empty one is the client with nothing configured anywhere.

    Args:
        config: The configuration of term-timer, as it was read.

    Returns:
        The parser of the ``tt-tail`` arguments.

    """
    parser = ArgumentParser(
        description='Read the term-timer event stream as it goes by.',
    )

    add_endpoint_argument(parser, configured_endpoint(config))

    parser.add_argument(
        '-a', '--all',
        dest='everything',
        action='store_true',
        help=(
            'Show every message, the gyroscope included.\n'
            'Default: False.'
        ),
    )
    parser.add_argument(
        '--no-color',
        dest='colorless',
        action='store_true',
        help=(
            'Write the stream without any color, as it already is\n'
            'when the output is not a terminal or NO_COLOR is set.\n'
            'Default: False.'
        ),
    )

    return parser


def build_writer(stream: IO[str]) -> Writer:
    """
    Give the client a place to write one block at a time.

    Each block is written whole and flushed: a stream left to its own
    buffering is a tail that says nothing for pages at a time, which is
    exactly what it is not for.

    Args:
        stream: Where the client writes.

    Returns:
        What a block of lines is handed to.

    """
    def write(text: str) -> None:
        stream.write(f'{ text }\n')
        stream.flush()

    return write


def build_tail(options: Namespace, stream: IO[str]) -> StreamTail:
    """
    Assemble what reads the stream out loud.

    Args:
        options: The arguments the client was called with.
        stream: Where the client writes.

    Returns:
        The reader, ready to be handed envelopes.

    """
    paint = build_paint(stream, colorless=options.colorless)

    return StreamTail(
        Renderer(paint),
        build_writer(stream),
        everything=options.everything,
    )


def main() -> int:
    """
    Read the event stream until the reader has seen enough.

    The stream is read in the main thread rather than in one of its
    own: a window is what needs the main thread to itself, and there is
    none here. One reader, one writer, and nothing to lock.

    Returns:
        Exit code, always 0: a tail ends when it is stopped.

    """
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    # Read before the arguments: what term-timer was configured with is
    # what the client is configured with, and the command line is what
    # says otherwise
    options = build_parser(load_config()).parse_args(sys.argv[1:])

    tail = build_tail(options, sys.stdout)
    stream = EventStream(options.endpoint, PREFIXES)

    # A subscriber connects to a publisher that may not be there yet,
    # and misses nothing of the session it waited for
    stream.open()

    try:
        while True:
            stream.receive(tail.dispatch)
    except KeyboardInterrupt:
        logger.info('Closing the stream')
    finally:
        stream.close()

    return 0
