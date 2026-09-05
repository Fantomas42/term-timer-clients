"""Entry point of the ``tt-tail`` client."""
import json
import logging
import sys
from argparse import Namespace
from contextlib import ExitStack
from pathlib import Path
from typing import IO

from term_timer_clients.argparser import LOG_FORMAT
from term_timer_clients.argparser import ArgumentParser
from term_timer_clients.argparser import add_endpoint_argument
from term_timer_clients.config import Config
from term_timer_clients.config import configured_endpoint
from term_timer_clients.config import load_config
from term_timer_clients.protocol import CUBE_PREFIX
from term_timer_clients.protocol import SESSION_PREFIX
from term_timer_clients.protocol import Envelope
from term_timer_clients.protocol import EventStream
from term_timer_clients.tail.ansi import build_paint
from term_timer_clients.tail.client import Recorder
from term_timer_clients.tail.client import StreamTail
from term_timer_clients.tail.client import TopicFilter
from term_timer_clients.tail.client import Writer
from term_timer_clients.tail.render import Renderer

logger = logging.getLogger(__name__)

# Both planes: what a cube does and what only term-timer knows are
# published apart, and a tail showing one of them would be a tail of
# half a session
PREFIXES = (CUBE_PREFIX, SESSION_PREFIX)


def parse_record_file(value: str) -> Path:
    """
    Read where a ``--record`` argument says the stream is kept.

    The path is expanded the way the address of an ``ipc`` endpoint is,
    and for the same reason: it is typed by hand, and a literal tilde
    would be taken for the name of a directory.

    Args:
        value: The argument, as it was typed.

    Returns:
        The file the envelopes are appended to.

    """
    return Path(value).expanduser()


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

    filters = parser.add_mutually_exclusive_group()
    filters.add_argument(
        '-t', '--topic',
        dest='topics',
        action='append',
        default=[],
        metavar='PREFIX',
        help=(
            'Show only topics starting with this, cube.move or\n'
            'cube. for the whole plane. Repeatable.\n'
            'Default: every topic shown.'
        ),
    )
    filters.add_argument(
        '--exclude',
        dest='excluded',
        action='append',
        default=[],
        metavar='PREFIX',
        help=(
            'Hide topics starting with this, on top of the\n'
            'gyroscope held back by default. Repeatable.\n'
            'Default: nothing excluded.'
        ),
    )

    parser.add_argument(
        '-r', '--record',
        type=parse_record_file,
        metavar='FILE',
        help=(
            'Append every message that arrives to this file, one\n'
            'JSON envelope per line, the gyroscope included and\n'
            'whatever --all shows or hides.\n'
            'Default: nothing is recorded.'
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


def build_recorder(stream: IO[str]) -> Recorder:
    """
    Give the client a place to keep the stream as it goes by.

    One JSON object per line, and the envelope whole: what is written
    down is what passed on the wire rather than what a reading made of
    it, which is what makes the file replayable instead of merely
    readable. A line at a time and flushed like the blocks, for the
    reason a capture exists at all - what is still in a buffer when the
    session is killed is the very part nobody has.

    Args:
        stream: Where the envelopes are kept.

    Returns:
        What an envelope is handed to.

    """
    def record(envelope: Envelope) -> None:
        stream.write(f'{ json.dumps(envelope) }\n')
        stream.flush()

    return record


def build_tail(
        options: Namespace,
        stream: IO[str],
        recorder: Recorder | None = None,
) -> StreamTail:
    """
    Assemble what reads the stream out loud.

    Args:
        options: The arguments the client was called with.
        stream: Where the client writes.
        recorder: Where the client keeps what arrives, none when
            nothing was asked to be kept.

    Returns:
        The reader, ready to be handed envelopes.

    """
    paint = build_paint(stream, colorless=options.colorless)

    return StreamTail(
        Renderer(paint),
        build_writer(stream),
        recorder,
        everything=options.everything,
        topic_filter=TopicFilter(
            tuple(options.topics), tuple(options.excluded),
        ),
    )


def open_recording(options: Namespace, stack: ExitStack) -> Recorder | None:
    """
    Open where the stream is kept, when it was asked to be kept at all.

    Appended to rather than started over: a tail is stopped and started
    again all day long, and the sessions tell themselves apart by the
    identifier of their envelopes exactly as they do on the screen. So
    what a second run has to say is added to what the first one heard,
    and no run of it ever costs a capture.

    A file that cannot be opened is left to say so, which is what
    stops the client: a recording asked for and silently not made would
    be found missing the day it is read, and by then the session it was
    to hold is gone.

    Args:
        options: The arguments the client was called with.
        stack: What the file is closed by.

    Returns:
        What an envelope is handed to, none when nothing is recorded.

    """
    if options.record is None:
        return None

    return build_recorder(
        stack.enter_context(
            options.record.open('a', encoding='utf-8'),
        ),
    )


def main() -> int:
    """
    Read the event stream until the reader has seen enough.

    The stream is read in the main thread rather than in one of its
    own: a window is what needs the main thread to itself, and there is
    none here. One reader, one writer, and nothing to lock.

    Returns:
        Exit code, 0 once the tail is stopped and 1 when the recording
        it was asked for cannot be written.

    """
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    # Read before the arguments: what term-timer was configured with is
    # what the client is configured with, and the command line is what
    # says otherwise
    options = build_parser(load_config()).parse_args(sys.argv[1:])

    with ExitStack() as stack:
        try:
            recorder = open_recording(options, stack)
        except OSError as error:
            # Fatal rather than reported: what is asked for on a
            # command line is asked for, and a tail reading on with
            # nothing kept is the capture found missing later
            logger.critical('Cannot record the stream: %s', error)
            return 1

        tail = build_tail(options, sys.stdout, recorder)
        stream = EventStream(options.endpoint, PREFIXES)

        # A subscriber connects to a publisher that may not be there
        # yet, and misses nothing of the session it waited for
        stream.open()

        try:
            while True:
                stream.receive(tail.dispatch)
        except KeyboardInterrupt:
            logger.info('Closing the stream')
        finally:
            stream.close()

    return 0
