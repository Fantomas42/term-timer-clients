"""Entry point of the ``cube-cast`` client."""
import logging
import sys
from argparse import ArgumentTypeError
from argparse import Namespace
from collections.abc import Collection

from cubing_algs.constants import ORIENTATIONS
from cubing_algs.display.gl import SENSOR_BASIS
from cubing_algs.display.gl import OrientationTracker
from cubing_algs.display.gl import Viewer
from cubing_algs.display.image import ROTATION_PATTERN
from cubing_algs.display.mode import MODE_CONFIGS
from cubing_algs.display.palettes import PALETTES
from cubing_algs.exceptions import CubingAlgsError
from cubing_algs.vcube import VCube

from term_timer_clients.argparser import LOG_FORMAT
from term_timer_clients.argparser import ArgumentParser
from term_timer_clients.argparser import add_endpoint_argument
from term_timer_clients.config import Config
from term_timer_clients.config import configured_cube
from term_timer_clients.config import configured_endpoint
from term_timer_clients.config import load_config
from term_timer_clients.protocol import EventStream
from term_timer_clients.viewer.client import CubeCast
from term_timer_clients.viewer.host import CubeCastHost

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SIZE = (400, 300)

SIZE_SEPARATOR = 'x'

# Read from the configuration of term-timer, under the very keys the
# session it listens to is displayed with: a window opened next to a
# terminal shows the same cube as the terminal, and each is still one
# option away. What the file says nothing of is shown as the cube
# reports itself, painted as cubing-algs paints it, and whole.
ORIENTATION_SETTING = 'orientation'

PALETTE_SETTING = 'palette'

# A step of the solve is what a window is opened on, never a taste kept
# between sessions, so nothing configures it
DEFAULT_MODE = ''

# The framing of cubing-algs. What is given here is also what the
# camera goes back to on Space: the viewer reframes on the rotation it
# opened with, and a window opened turned would be lost on the first
# reset otherwise
DEFAULT_ROTATION = ''


def configured_choice(
        setting: str,
        value: str,
        choices: Collection[str],
) -> str:
    """
    Keep a configured setting only when this client knows what it names.

    term-timer validates its own configuration, but it and the
    cubing-algs this window draws with have their own releases: a taste
    written for one this client does not have is dropped rather than
    refused, a client ignoring what it does not know rather than
    failing on it. Only what is typed on the command line stops the
    client, and argparse says so itself.

    Args:
        setting: Name of the setting, as the configuration spells it.
        value: The setting, as the configuration carries it.
        choices: What this client is able to draw.

    Returns:
        The setting, empty when it names nothing known here.

    """
    if value and value not in choices:
        logger.warning(
            'Ignoring the configured cube %s "%s", unknown here',
            setting, value,
        )
        return ''

    return value


def parse_camera_rotation(value: str) -> str:
    """
    Read the angle a ``--rotation`` argument frames the cube from.

    cubing-algs falls back on its own framing for a string it cannot
    read, so a typo would open the very window it was meant to change,
    with nothing said about it: it is refused here instead.

    Args:
        value: The argument, as it was typed.

    Returns:
        The rotation string, empty for the framing of cubing-algs.

    Raises:
        ArgumentTypeError: When the argument names no rotation.

    """
    if value and not ROTATION_PATTERN.match(value):
        msg = (
            f'"{ value }" is not a rotation, '
            f'expected AXISDEGREES parts, e.g. y45x-34'
        )
        raise ArgumentTypeError(msg)

    return value


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


def build_parser(config: Config) -> ArgumentParser:
    """
    Describe what the client takes on its command line.

    The configuration is handed over rather than read here: it is what
    the defaults of the parser are made of, and a parser built on an
    empty one is the client with nothing configured anywhere.

    Args:
        config: The configuration of term-timer, as it was read.

    Returns:
        The parser of the ``cube-cast`` arguments.

    """
    parser = ArgumentParser(
        description='Watch a cube in 3D, from the term-timer event stream.',
    )

    orientations = sorted(ORIENTATIONS)
    palettes = sorted(PALETTES)

    endpoint = configured_endpoint(config)
    orientation = configured_choice(
        ORIENTATION_SETTING,
        configured_cube(config, ORIENTATION_SETTING),
        orientations,
    )
    palette = configured_choice(
        PALETTE_SETTING,
        configured_cube(config, PALETTE_SETTING),
        palettes,
    )

    add_endpoint_argument(parser, endpoint)

    parser.add_argument(
        '-o', '--orientation',
        default=orientation,
        choices=orientations,
        metavar='ORIENTATION',
        help=(
            'Set the cube orientation used.\n'
            'Default: '
            f'{ orientation or "the faces the cube is held by" }.'
        ),
    )
    parser.add_argument(
        '-p', '--palette',
        default=palette,
        choices=palettes,
        metavar='PALETTE',
        help=(
            'Set the colors of the cube.\n'
            f'Default: { palette or "the colors of a cube" }.'
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
        '-r', '--rotation',
        type=parse_camera_rotation,
        default=DEFAULT_ROTATION,
        metavar='ROTATION',
        help=(
            'Set the angle the camera looks the cube from,\n'
            'as AXISDEGREES parts, e.g. y45x-34.\n'
            'Default: the framing of cubing-algs.'
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
        rotation=options.rotation,
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
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    # Read before the arguments: what term-timer was configured with is
    # what the client is configured with, and the command line is what
    # says otherwise
    options = build_parser(load_config()).parse_args(sys.argv[1:])

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
