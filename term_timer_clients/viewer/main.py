"""Entry point of the ``cube-cast`` client."""
import logging
import sys
from argparse import ArgumentTypeError
from argparse import Namespace

from cubing_algs.constants import ORIENTATIONS
from cubing_algs.display.gl import SENSOR_BASIS
from cubing_algs.display.gl import OrientationTracker
from cubing_algs.display.gl import Viewer
from cubing_algs.display.mode import MODE_CONFIGS
from cubing_algs.display.palettes import PALETTES
from cubing_algs.exceptions import CubingAlgsError
from cubing_algs.vcube import VCube

from term_timer_clients.argparser import ArgumentParser
from term_timer_clients.protocol import EventStream
from term_timer_clients.protocol import parse_endpoint
from term_timer_clients.viewer.client import CubeCast
from term_timer_clients.viewer.host import CubeCastHost

logger = logging.getLogger(__name__)

LOG_FORMAT = '%(levelname)s: %(message)s'

DEFAULT_WINDOW_SIZE = (400, 300)

SIZE_SEPARATOR = 'x'

# Shown as the cube reports itself, painted as cubing-algs paints it,
# and whole: a client of a stream has no configuration file of its own
# to read a taste from, and each of the three is one option away
DEFAULT_ORIENTATION = ''

DEFAULT_PALETTE = ''

DEFAULT_MODE = ''


def parse_stream_endpoint(value: str) -> str:
    """
    Read the endpoint of the stream a ``--endpoint`` argument names.

    The endpoint goes through what the publisher reads its own with, so
    that a tilde written on the command line points at the same socket
    as the one written in the configuration.

    Args:
        value: The argument, as it was typed.

    Returns:
        The endpoint to connect to.

    Raises:
        ArgumentTypeError: When the argument names no transport. A
            subscriber given a broken endpoint would wait in silence
            forever, so it is refused here.

    """
    endpoint = parse_endpoint(value)

    if not endpoint:
        msg = (
            f'"{ value }" is not an endpoint, '
            f'expected TRANSPORT://ADDRESS'
        )
        raise ArgumentTypeError(msg)

    return endpoint


def parse_size(value: str) -> tuple[int, int]:
    """
    Read the size of the window a ``WIDTHxHEIGHT`` argument names.

    Args:
        value: The argument, as it was typed.

    Returns:
        The width and the height, in pixels.

    Raises:
        ArgumentTypeError: When the argument names no size.

    """
    width, separator, height = value.lower().partition(SIZE_SEPARATOR)

    if not separator or not width.isdigit() or not height.isdigit():
        msg = (
            f'"{ value }" is not a size, '
            f'expected WIDTH{ SIZE_SEPARATOR }HEIGHT'
        )
        raise ArgumentTypeError(msg)

    return int(width), int(height)


def build_parser() -> ArgumentParser:
    """
    Describe what the client takes on its command line.

    Returns:
        The parser of the ``cube-cast`` arguments.

    """
    parser = ArgumentParser(
        description='Watch a cube in 3D, from the term-timer event stream.',
    )

    parser.add_argument(
        '-e', '--endpoint',
        required=True,
        type=parse_stream_endpoint,
        metavar='ENDPOINT',
        help=(
            'Connect to this ZeroMQ endpoint, one of those the\n'
            '[publisher] section of the configuration binds'
        ),
    )
    parser.add_argument(
        '-o', '--orientation',
        default=DEFAULT_ORIENTATION,
        choices=sorted(ORIENTATIONS),
        metavar='ORIENTATION',
        help=(
            'Set the cube orientation used.\n'
            'Default: the faces the cube is held by.'
        ),
    )
    parser.add_argument(
        '-p', '--palette',
        default=DEFAULT_PALETTE,
        choices=sorted(PALETTES),
        metavar='PALETTE',
        help=(
            'Set the colors of the cube.\n'
            'Default: the colors of a cube.'
        ),
    )
    parser.add_argument(
        '-m', '--mode',
        default=DEFAULT_MODE,
        choices=sorted(MODE_CONFIGS),
        metavar='MODE',
        help=(
            'Show only what a step of the solve is about, e.g. oll.\n'
            'Default: the whole cube.'
        ),
    )
    parser.add_argument(
        '-w', '--window-size',
        type=parse_size,
        default=DEFAULT_WINDOW_SIZE,
        metavar='WIDTHxHEIGHT',
        help=(
            'Set the size of the window.\n'
            f'Default: { DEFAULT_WINDOW_SIZE[0] }'
            f'{ SIZE_SEPARATOR }{ DEFAULT_WINDOW_SIZE[1] }.'
        ),
    )
    parser.add_argument(
        '-t', '--transparent',
        action='store_true',
        help=(
            'Lay the cube on the desktop: no background, no window\n'
            'decoration, and floating above everything.\n'
            'Default: False.'
        ),
    )
    parser.add_argument(
        '--no-msaa',
        action='store_true',
        help=(
            'Draw the cube into the window itself, aliased but with\n'
            'nothing in between.\n'
            'Default: False.'
        ),
    )

    return parser


def build_host(options: Namespace) -> CubeCastHost:
    """
    Assemble the window, the viewer and what translates the stream.

    Args:
        options: The arguments the client was called with.

    Returns:
        The host, ready to be opened.

    """
    tracker = OrientationTracker(basis=SENSOR_BASIS)

    # A mode is resolved once, on the solved cube the viewer is built
    # with, and what is kept of it is the mask: the stream reposes the
    # cube on every state it describes, and the orientation a mode
    # carries would be thrown away with it. Here it would be anyway -
    # the window is held by the gyroscope of the cube.
    viewer = Viewer(
        cube=VCube(),
        palette=options.palette,
        mode=options.mode,
        window_size=options.window_size,
        orientation=tracker,
    )

    view = CubeCast(viewer, tracker, options.orientation)

    return CubeCastHost(
        viewer=viewer,
        title=view.title,
        view=view,
        transparent=options.transparent,
        msaa=not options.no_msaa,
    )


def main() -> int:
    """
    Open a window on the event stream, and draw the cube it describes.

    Returns:
        Exit code, 1 when no window could be opened.

    """
    options = build_parser().parse_args(sys.argv[1:])

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    host = build_host(options)
    stream = EventStream(options.endpoint)

    # Read before the window opens: a subscriber connects to a publisher
    # that may not be there yet, and misses nothing while it waits
    stream.start(host.view.dispatch)

    try:
        host.run()
    except CubingAlgsError as error:
        logger.error('Cannot open a window: %s', error)  # noqa: TRY400
        return 1
    except KeyboardInterrupt:
        logger.info('Closing the window')
    finally:
        stream.stop()

    return 0
