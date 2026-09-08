"""Entry point of the ``cube-cast`` client."""
import logging
import sys
from argparse import ArgumentTypeError
from argparse import Namespace
from collections.abc import Collection

from cubing_algs.constants import ORIENTATIONS
from cubing_algs.display.gl import OrientationTracker
from cubing_algs.display.gl import Viewer
from cubing_algs.display.gl import orientation_basis
from cubing_algs.display.mode import MODE_CONFIGS
from cubing_algs.display.palettes import PALETTES
from cubing_algs.display.rotation import valid_rotation
from cubing_algs.exceptions import CubingAlgsError
from cubing_algs.vcube import VCube

from term_timer_clients.argparser import LOG_FORMAT
from term_timer_clients.argparser import ArgumentParser
from term_timer_clients.argparser import add_endpoint_argument
from term_timer_clients.config import Config
from term_timer_clients.config import configured_cube
from term_timer_clients.config import configured_endpoint
from term_timer_clients.config import load_config
from term_timer_clients.protocol import CUBE_PREFIX
from term_timer_clients.protocol import SESSION_END_TOPIC
from term_timer_clients.protocol import EventStream
from term_timer_clients.viewer.client import CubeCast
from term_timer_clients.viewer.clock import CubeClock
from term_timer_clients.viewer.framing import DEFAULT_VIEW
from term_timer_clients.viewer.framing import VIEWS
from term_timer_clients.viewer.framing import Framing
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

# How long a quarter turn takes on screen, and how much of it is
# already over when the window hears about it, in milliseconds.
#
# **What the beat adds to the lag is exactly what it gives to see**:
# measured on the cadence harness of cubing-algs against a simulated
# bluetooth link, the delay from the gesture to the cube landing is
# `latency + beat - lead`, so every millisecond of visible turn is a
# millisecond of retard and there is no third term to trade against.
# A hundred and fifty is where a cube stops feeling like it is being
# dragged, against the four hundred of the cubing-algs beat, which is
# written for an algorithm one reads rather than for a hand one follows.
#
# The two are **not independent**: a lead only ever takes effect while
# the beat is shorter than the gap between two moves, a longer one
# saturating the queue and pinning every move behind the one before it.
# A hundred holds up to ten turns a second, which is above what a hand
# sustains between two pauses.
DEFAULT_BEAT = 100

DEFAULT_LEAD = 50

# The share of a turn an age may eat into, past which a move would land
# without ever being seen to move. It has to sit **above** the lead and
# not on it: what it bounds is the delay measured on top of the lead - a
# packet held back, a burst handed over in one go - and a ceiling equal
# to the lead would clamp every measurement away and leave the reading
# of the clock doing nothing at all. Three quarters keeps a visible
# quarter of the turn in the worst case while leaving the jitter room
# to be worth measuring.
#
# A lead typed on the command line is honored whatever it says, this
# holding back only what is added to it: asking for a cube that snaps
# is a thing one may want, and it is asked for with `--lead`.
LEAD_SHARE = 0.75

MILLISECONDS = 1000.0

# The framing of cubing-algs, and what `--rotation` replaces: an angle
# typed by hand is the demo view written out, rather than a fourth
# framing standing next to the ones the keys reach - one typed and
# left behind by the first key pressed would be an angle nothing can
# ever come back to. What the view says is what the camera goes back
# to on Space, the viewer reframing on the rotation it holds.
DEFAULT_ROTATION = ''

# The hardware plane, and the one message of the other one a window has
# any use for: a stream that is over describes no cube any more, and a
# viewer that never heard of its end would keep showing the cube of a
# session nobody is publishing. Everything else term-timer knows alone
# stays on the wire.
PREFIXES = (CUBE_PREFIX, SESSION_END_TOPIC)


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


def read_milliseconds(value: str, floor: int) -> float:
    """
    Read a duration typed in milliseconds, in the seconds of a clock.

    Args:
        value: The argument, as it was typed.
        floor: The smallest it is allowed to be, in milliseconds.

    Returns:
        The duration, in seconds.

    Raises:
        ArgumentTypeError: When the argument names no such duration.

    """
    if not value.isdigit() or int(value) < floor:
        msg = (
            f'"{ value }" is not a duration, '
            f'expected milliseconds from { floor }'
        )
        raise ArgumentTypeError(msg)

    return int(value) / MILLISECONDS


def parse_beat(value: str) -> float:
    """
    Read how long a quarter turn is given to happen.

    Args:
        value: The argument, as it was typed.

    Returns:
        The beat, in seconds.

    """
    return read_milliseconds(value, 1)


def parse_lead(value: str) -> float:
    """
    Read how much of a move is over by the time it is heard of.

    Zero is a perfectly good answer, and it is the one for a stream
    nothing travels through: it plays every turn whole.

    Args:
        value: The argument, as it was typed.

    Returns:
        The lead, in seconds.

    """
    return read_milliseconds(value, 0)


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
    if value and not valid_rotation(value):
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
            'Set the angle the demo view looks the cube from,\n'
            'as AXISDEGREES parts, e.g. y45x-34.\n'
            'Default: the framing of cubing-algs.'
        ),
    )
    parser.add_argument(
        '-v', '--view',
        default=DEFAULT_VIEW,
        choices=VIEWS,
        metavar='VIEW',
        help=(
            'Set the view the window opens on.\n'
            'demo: the cube seen by three faces at once.\n'
            'user: the cube seen by its front and top faces.\n'
            f'Default: { DEFAULT_VIEW }.'
        ),
    )
    parser.add_argument(
        '-i', '--mirror',
        action='store_true',
        help=(
            'Look at the cube from behind: the view is seen\n'
            'from the other side, at the same height.\n'
            'Default: False.'
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
        '-b', '--beat',
        type=parse_beat,
        default=DEFAULT_BEAT / MILLISECONDS,
        metavar='MILLISECONDS',
        help=(
            'Set how long a quarter turn takes to turn on screen.\n'
            'What it adds to the delay is what it gives to see.\n'
            f'Default: { DEFAULT_BEAT }.'
        ),
    )
    parser.add_argument(
        '-l', '--lead',
        type=parse_lead,
        default=DEFAULT_LEAD / MILLISECONDS,
        metavar='MILLISECONDS',
        help=(
            'Set how much of a move is already over when the\n'
            'window hears of it, and starts the turn that far in.\n'
            f'Default: { DEFAULT_LEAD }.'
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
        '-g', '--no-gyroscope',
        action='store_true',
        help=(
            'Leave the cube where the camera puts it, deaf to the\n'
            'gyroscope: the window is framed by the view and the\n'
            'mouse, and the moves alone come from the cube.\n'
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
    # A window deaf to the gyroscope is one with no tracker at all,
    # rather than one dropping the messages as they arrive: it is the
    # very same absence as a stream where nothing turns the cube, and
    # the viewer already draws a cube nobody orients from the camera
    # alone. The quaternions still arrive, and `turn_cube()` has
    # nothing to feed them to.
    #
    # The gyroscope quaternion published on the stream is already
    # canonical - the driver applies its own sensor basis before
    # publishing, so the client has no hardware frame left to correct.
    # Only the display orientation stays to compose, the same rotation
    # already turning the state and the moves (`rebuild()` and
    # `translate()` in `client.py`).
    tracker = (
        None
        if options.no_gyroscope
        else OrientationTracker(
            basis=orientation_basis(options.orientation),
        )
    )

    # Where the camera stands, and what the view keys move it between.
    # The viewer is built on the very string the framing hands over
    # rather than on what was typed: `--rotation` is the demo view
    # written by hand, and `--mirror` is the 3 key already pressed.
    framing = Framing.opened_on(
        options.view, options.rotation, mirrored=options.mirror,
    )

    # A mode is resolved once, on the solved cube the viewer is built
    # with, and what is kept of it is the mask: the stream reposes the
    # cube on every state it describes, and the orientation a mode
    # carries would be thrown away with it. Here it would be anyway -
    # what holds the window is the gyroscope of the cube, or the
    # camera alone when nothing is listening to it.
    viewer = Viewer(
        cube=VCube(),
        palette=options.palette,
        mode=options.mode,
        rotation=framing.rotation,
        window_size=options.window_size,
        orientation=tracker,
        duration=options.beat,
    )

    # The ceiling is read on the beat because that is what it protects:
    # an age reaching the whole of a turn starts it where it ends. What
    # was typed is never held back by it - a lead of its own is an
    # answer about this link, and this only ever bounds what the jitter
    # of the link adds on top of it.
    clock = CubeClock(
        lead=options.lead,
        ceiling=max(options.lead, options.beat * LEAD_SHARE),
    )

    view = CubeCast(viewer, tracker, options.orientation, clock)

    return CubeCastHost(
        viewer=viewer,
        title=view.title,
        view=view,
        framing=framing,
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
    stream = EventStream(options.endpoint, PREFIXES)

    # Read before the window opens: a subscriber connects to a publisher
    # that may not be there yet, and misses nothing while it waits
    stream.start(host.view.dispatch)

    try:
        host.run()
    except CubingAlgsError as error:
        logger.error('Cannot open a window: %s', error)  # ruff: ignore[error-instead-of-exception]
        return 1
    except KeyboardInterrupt:
        logger.info('Closing the window')
    finally:
        stream.stop()

    return 0
