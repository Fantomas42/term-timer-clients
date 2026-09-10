"""Entry point of the ``cube-tray`` client."""
import asyncio
import logging
import sys
import time
from argparse import Namespace

from term_timer_clients.argparser import LOG_FORMAT
from term_timer_clients.argparser import ArgumentParser
from term_timer_clients.argparser import add_endpoint_argument
from term_timer_clients.argparser import parse_size
from term_timer_clients.argparser import write_size
from term_timer_clients.config import Config
from term_timer_clients.config import configured_endpoint
from term_timer_clients.config import load_config
from term_timer_clients.protocol import CUBE_PREFIX
from term_timer_clients.protocol import SESSION_END_TOPIC
from term_timer_clients.protocol import EventStream
from term_timer_clients.tray.bus import BusError
from term_timer_clients.tray.bus import close_bus
from term_timer_clients.tray.bus import follow_watcher
from term_timer_clients.tray.bus import open_bus
from term_timer_clients.tray.bus import publish
from term_timer_clients.tray.bus import register
from term_timer_clients.tray.cast import DEFAULT_POPUP_SIZE
from term_timer_clients.tray.cast import Popup
from term_timer_clients.tray.cast import cast_command
from term_timer_clients.tray.client import CubeTray
from term_timer_clients.tray.item import TrayItem
from term_timer_clients.tray.item import TrayMenu

logger = logging.getLogger(__name__)

# The same two planes the window subscribes to, and for the same
# reason: a cube publishing anything at all says it is there, and the
# farewell of the publisher is the other way it stops being there.
# Everything else the session plane carries is what a window shows and
# an icon has nowhere to say.
PREFIXES = (CUBE_PREFIX, SESSION_END_TOPIC)

# How often the bar is brought up to date, in seconds. Nothing is drawn
# on this clock - the icon is written again only when what it says has
# changed - so what it buys is how long a window closing itself goes
# unnoticed and how closely a followed cube is answered, and it sits
# where the stream reads its own timeout.
TICK = 0.2

# What is said when there is nowhere to put an icon. It names the
# extension rather than the specification, because that is what has to
# be turned on: a GNOME session carries no tray of its own, and the
# error the bus hands back names nothing anybody can act on.
NO_WATCHER = (
    'Cannot show an icon: no system tray on this desktop. '
    'On GNOME, the AppIndicator extension is what provides one'
)


def build_parser(config: Config) -> ArgumentParser:
    """
    Describe what the client takes on its command line.

    The configuration is handed over rather than read here: it is what
    the defaults of the parser are made of, and a parser built on an
    empty one is the client with nothing configured anywhere.

    Args:
        config: The configuration of term-timer, as it was read.

    Returns:
        The parser of the ``cube-tray`` arguments.

    """
    parser = ArgumentParser(
        description='Watch a cube from the bar, on the term-timer stream.',
        epilog=(
            'Everything typed after -- is handed to cube-cast as it\n'
            'stands, so the window is argued with where it is\n'
            'documented: cube-tray -- --palette rgb --view user.'
        ),
    )

    add_endpoint_argument(parser, configured_endpoint(config))

    parser.add_argument(
        '-w', '--window-size',
        type=parse_size,
        default=DEFAULT_POPUP_SIZE,
        metavar='WIDTHxHEIGHT',
        help=(
            'Set the size of the window a click opens.\n'
            f'Default: { write_size(DEFAULT_POPUP_SIZE) }.'
        ),
    )
    parser.add_argument(
        '-a', '--auto',
        action='store_true',
        help=(
            'Show the window on its own whenever a cube connects,\n'
            'and take it away once the cube is gone.\n'
            'Default: the window is shown by hand.'
        ),
    )
    parser.add_argument(
        'cast_arguments',
        nargs='*',
        metavar='-- ARGUMENTS',
        help=(
            'Open the window with these arguments on top,\n'
            'whatever cube-cast takes.\n'
            'Default: nothing added.'
        ),
    )

    return parser


def build_tray(options: Namespace) -> CubeTray:
    """
    Assemble the icon and the window a click on it shows.

    Args:
        options: The arguments the client was called with.

    Returns:
        The client, ready to be handed envelopes.

    """
    return CubeTray(
        Popup(
            cast_command(
                options.endpoint,
                options.window_size,
                options.cast_arguments,
            ),
        ),
        auto=options.auto,
    )


async def serve(tray: CubeTray) -> None:
    """
    Show the icon, and keep it saying what the stream says.

    The bar is written to only when what it shows has changed, and it
    is the whole reason there is a state to compare: the gyroscope
    alone publishes tens of times a second, and an icon redrawn that
    often is an icon redrawn for nothing.

    The link is read at every turn rather than in the stream, which is
    what lets a followed cube show its window at all: the thread
    reading the stream only ever writes down what it heard, the way it
    hands a title to a window it may not touch, and this loop is what
    acts on it. It is also the clock the delay of the blast is measured
    against, and the only one this client has.

    Args:
        tray: What the icon shows, and what a click reaches.

    """
    bus = await open_bus()

    item = TrayItem(tray)
    menu = TrayMenu(tray)

    service = await publish(bus, item, menu)

    # Followed before it is asked anything, so that a tray coming up
    # between the two is not a tray this icon missed
    await follow_watcher(bus, service)
    await register(bus, service)

    shown = tray.state

    while not tray.stopped:
        await asyncio.sleep(TICK)

        tray.settle()
        tray.follow(time.monotonic())

        if tray.state != shown:
            shown = tray.state

            item.refresh()
            menu.refresh()

    close_bus(bus)


def main() -> int:
    """
    Show the cube in the bar until somebody puts it away.

    Returns:
        Exit code, 1 when there is nowhere to show an icon.

    """
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    # Read before the arguments: what term-timer was configured with is
    # what the client is configured with, and the command line is what
    # says otherwise
    options = build_parser(load_config()).parse_args(sys.argv[1:])

    tray = build_tray(options)
    stream = EventStream(options.endpoint, PREFIXES)

    # Read in a thread of its own, and started before the icon is on
    # the bus: the loop belongs to the bus the way a window belongs to
    # the thread that opened it, so the stream only ever moves what the
    # next tick reads - and a subscriber connected first misses nothing
    # of the session it waited for.
    stream.start(tray.dispatch)

    # Opened with the icon and hidden behind it, for the reason the
    # icon exists at all: a cube describes itself when it connects and
    # announces nothing when it arrives, so a window opened at the
    # click has heard none of it and shows a core alone. The one that
    # was there all along is the cube as it now stands, and a click is
    # a line on a pipe rather than a process and a first frame.
    tray.popup.launch()

    try:
        asyncio.run(serve(tray))
    except (BusError, OSError) as error:
        logger.error('%s: %s', NO_WATCHER, error)  # ruff: ignore[error-instead-of-exception]
        return 1
    except KeyboardInterrupt:
        logger.info('Closing the tray')
    finally:
        stream.stop()
        tray.popup.close()

    return 0
