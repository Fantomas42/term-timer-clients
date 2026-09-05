"""
A cube that is not there, for rehearsing a client without hardware.

Publishes the very frames term-timer publishes, over and over: nothing
at all for a few seconds, then a link and a state, then moves, then a
link that drops. Ctrl+C is one more departure: the cube says it is
going before the process does.

Nothing but the ``cube.*`` plane is published here, the plane a cube
would produce by itself. What only term-timer knows - a session, its
solves, its end - is the business of a publisher of its own.

It binds where term-timer binds, so a client opens on it with nothing
typed either side:

    python publishers/phantom_cube.py
    cube-cast
    tt-tail

What the cube connects on is ``--setup`` and what it turns once
connected is ``--algorithm``, both written the way the hands write
them, and ``--orientation`` says which faces those hands hold the cube
by - the very orientation the window is watched with:

    python publishers/phantom_cube.py -s "F R U2" -a "R U R2" -o DF
    cube-cast -o DF

Every pause of the rehearsal is an argument of its own, so a client is
watched at the pace of what is being debugged - the pieces held apart
for ten seconds, or moves with next to nothing in between:

    python publishers/phantom_cube.py --gathering 10 --pace 0.05
"""
# A debug script rather than a client: it writes the stream instead of
# reading it, nothing imports it, and its prints are its whole output.
# ruff: noqa: INP001, T201
import json
import sys
import time
import uuid
from argparse import ArgumentTypeError
from argparse import Namespace
from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

import zmq
from cubing_algs.algorithm import Algorithm
from cubing_algs.constants import ORIENTATION_FACE_MOVES
from cubing_algs.constants import ORIENTATIONS
from cubing_algs.exceptions import CubingAlgsError
from cubing_algs.parsing import parse_moves
from cubing_algs.transform.invert import invert_moves
from cubing_algs.transform.translate import translate_moves
from cubing_algs.vcube import VCube

from term_timer_clients.argparser import ArgumentParser
from term_timer_clients.argparser import parse_stream_endpoint
from term_timer_clients.config import Config
from term_timer_clients.config import configured_cube
from term_timer_clients.config import configured_endpoint
from term_timer_clients.config import load_config
from term_timer_clients.protocol import PROTOCOL_VERSION

# Where a cube is rehearsed when term-timer configured no publisher:
# a port of its own, so a session left running is never talked over
FALLBACK_ENDPOINT = 'tcp://127.0.0.1:5556'

ORIENTATION_SETTING = 'orientation'

# The topics of the rehearsal, and they are all of the hardware plane:
# what only term-timer knows is published by term-timer. They are
# written here rather than read from the protocol module because a
# publisher names what it emits: a client subscribes to a prefix, this
# one has to spell every topic out.
LINK_TOPIC = 'cube.link'

HARDWARE_TOPIC = 'cube.hardware'

BATTERY_TOPIC = 'cube.battery'

FACELETS_TOPIC = 'cube.facelets'

MOVE_TOPIC = 'cube.move'

# What the cube says of itself once connected: enough for a client to
# have something to show, and nothing a rehearsal has a use for
SOURCE = 'solve'

HARDWARE_NAME = 'GANi3'

# A cube counts its own milliseconds, a script counts in seconds.
MILLISECONDS = 1000.0

BATTERY_LEVEL = 80

# The state the cube introduces itself in: a solved one, as a cube
# taken out of the box, and what is typed is what it was turned by
# before it connected
SETUP = ''

ALGORITHM = "R U R' U'"

# What a window already waiting is given to finish subscribing, once
# and outside the loop. Binding is not connecting: a subscriber that
# started first is retrying every hundred milliseconds, and a PUB
# drops what it publishes to a peer whose subscription has not reached
# it yet - so the link sent in the microsecond after the bind goes
# nowhere, and the first cycle alone lights its core on the facelets.
SETTLE = 0.2

# The pauses of one cycle, in the order they are waited. Each is an
# argument of its own: what is being debugged is never the same moment
# twice, and a rehearsal that cannot be slowed down on the one moment
# looked at is a rehearsal watched by luck.
SILENCE = 3.0

CONNECTION = 2.0

GATHERING = 1.0

PACE = 0.35

WATCHING = 2.0


@dataclass(frozen=True)
class Pauses:
    """What the rehearsal waits, at each of the moments it has."""

    silence: float
    connection: float
    gathering: float
    pace: float
    watching: float

    @classmethod
    def from_options(cls, options: Namespace) -> Self:
        """
        Read the cadence the command line was given.

        Args:
            options: The arguments the script was called with.

        Returns:
            The pauses of one cycle.

        """
        return cls(
            silence=options.silence,
            connection=options.connection,
            gathering=options.gathering,
            pace=options.pace,
            watching=options.watching,
        )


class Publisher:
    """
    The socket term-timer publishes on, and the counter of the stream.

    It binds, as every publisher of this protocol does, so the order
    the two sides are started in never matters: a client connected
    first waits, and one started later finds the socket already there.
    """

    def __init__(self, endpoint: str) -> None:
        """
        Bind the endpoint, under a session of this process alone.

        The identifier is drawn at every run rather than fixed: a
        client tells a publisher that restarted from the one it was
        already listening to by that field, and a rehearsal always
        answering the same one would never be seen to start over.

        Args:
            endpoint: The ZeroMQ endpoint to bind.

        """
        self.endpoint = endpoint
        self.session = uuid.uuid4().hex[:8]
        self.seq = 0

        self.socket: zmq.Socket[bytes] = zmq.Context.instance().socket(
            zmq.PUB,
        )
        self.socket.bind(endpoint)

    def envelope(
            self,
            topic: str,
            data: dict[str, object],
    ) -> dict[str, object]:
        """
        Wrap a payload the way every message of the stream is wrapped.

        Args:
            topic: The topic the message is published under.
            data: The payload, always an object.

        Returns:
            The envelope, ready to be written.

        """
        return {
            'v': PROTOCOL_VERSION,
            'seq': self.seq,
            'ts': time.time(),
            'src': SOURCE,
            'sid': self.session,
            'topic': topic,
            'data': data,
        }

    def send(self, topic: str, data: dict[str, object]) -> None:
        """
        Publish one message, topic frame then payload frame.

        Args:
            topic: The topic the message is published under.
            data: The payload, always an object.

        """
        envelope = self.envelope(topic, data)
        self.seq += 1

        self.socket.send_multipart(
            [topic.encode(), json.dumps(envelope).encode()],
        )
        print(f'  { topic }')

    def close(self) -> None:
        """Close the socket, once what it still holds has gone out."""
        self.socket.close()


def parse_algorithm(value: str) -> Algorithm:
    """
    Read the moves an algorithm argument is made of.

    Args:
        value: The argument, as it was typed.

    Returns:
        The algorithm it names.

    Raises:
        ArgumentTypeError: When the argument names no algorithm a cube
            could play. The parser reads more than a cube turns, so it
            is the cube that is asked here: an algorithm refused after
            the socket is bound would leave a window waiting on a
            publisher that has already died.

    """
    try:
        algorithm = parse_moves(value)
        VCube().rotate(algorithm)
    except CubingAlgsError as error:
        msg = f'"{ value }" is not an algorithm: { error }'
        raise ArgumentTypeError(msg) from error

    return algorithm


def parse_pause(value: str) -> float:
    """
    Read the seconds a pause argument is written in.

    Args:
        value: The argument, as it was typed.

    Returns:
        The pause, in seconds.

    Raises:
        ArgumentTypeError: When the argument names no duration. A
            negative one is refused rather than taken for zero: what
            was meant by it is unknowable, and a cadence nobody typed
            is exactly what a rehearsal is watched against.

    """
    try:
        pause = float(value)
    except ValueError as error:
        msg = f'"{ value }" is not a number of seconds'
        raise ArgumentTypeError(msg) from error

    if pause < 0:
        msg = f'"{ value }" is a negative pause'
        raise ArgumentTypeError(msg)

    return pause


def build_parser(config: Config) -> ArgumentParser:
    """
    Describe what the rehearsal takes on its command line.

    The configuration is handed over rather than read here, as it is in
    every client: it is what the defaults are made of, and a parser
    built on an empty one is the rehearsal with nothing configured
    anywhere.

    Args:
        config: The configuration of term-timer, as it was read.

    Returns:
        The parser of the ``phantom_cube.py`` arguments.

    """
    parser = ArgumentParser(
        description='Publish the frames of a cube that is not there.',
        epilog=(
            'Examples:\n'
            '  phantom_cube.py\n'
            '  phantom_cube.py -s "F R U2" -a "R U R2" -o DF\n'
            '  phantom_cube.py --gathering 10 --pace 0.05\n'
        ),
    )

    endpoint = configured_endpoint(config) or FALLBACK_ENDPOINT
    orientation = configured_cube(config, ORIENTATION_SETTING)

    # Read by what every client reads its own with - an endpoint is
    # spelled the same way whether it is bound or connected to - but
    # declared here rather than by add_endpoint_argument(): that one
    # says "connect to", which is the one thing a publisher does not
    # do, and its help is exactly what it exists to keep identical
    # everywhere.
    parser.add_argument(
        '-e', '--endpoint',
        default=endpoint,
        type=parse_stream_endpoint,
        metavar='ENDPOINT',
        help=(
            'Bind this ZeroMQ endpoint, the one term-timer would.\n'
            f'Default: { endpoint }.'
        ),
    )
    parser.add_argument(
        '-s', '--setup',
        default=SETUP,
        type=parse_algorithm,
        metavar='SETUP',
        help=(
            'Connect on the state these moves leave, written from\n'
            'the point of view of the hands.\n'
            'Default: a solved cube.'
        ),
    )
    parser.add_argument(
        '-a', '--algorithm',
        default=ALGORITHM,
        type=parse_algorithm,
        metavar='ALGORITHM',
        help=(
            'Turn these moves once connected, written from\n'
            'the point of view of the hands.\n'
            f'Default: { ALGORITHM }.'
        ),
    )
    parser.add_argument(
        '-o', '--orientation',
        default=orientation,
        choices=sorted(ORIENTATIONS),
        metavar='ORIENTATION',
        help=(
            'Hold the cube by these two faces, e.g. DF: what is\n'
            'published is what a cube held that way would report.\n'
            'Default: '
            f'{ orientation or "the faces of the hardware" }.'
        ),
    )

    pauses = parser.add_argument_group(
        'pauses',
        'What the rehearsal waits, in seconds, at each of the '
        'moments of one cycle.',
    )

    pauses.add_argument(
        '--silence',
        default=SILENCE,
        type=parse_pause,
        metavar='SECONDS',
        help=(
            'Publish nothing at all between two cycles, a client\n'
            'having no cube to show.\n'
            f'Default: { SILENCE }.'
        ),
    )
    pauses.add_argument(
        '--connection',
        default=CONNECTION,
        type=parse_pause,
        metavar='SECONDS',
        help=(
            'Wait between the link and the state, a cube connected\n'
            'that has not described itself yet.\n'
            f'Default: { CONNECTION }.'
        ),
    )
    pauses.add_argument(
        '--gathering',
        default=GATHERING,
        type=parse_pause,
        metavar='SECONDS',
        help=(
            'Wait between the state and the first move.\n'
            f'Default: { GATHERING }.'
        ),
    )
    pauses.add_argument(
        '--pace',
        default=PACE,
        type=parse_pause,
        metavar='SECONDS',
        help=(
            'Wait between two moves, the cadence the hands turn at.\n'
            f'Default: { PACE }.'
        ),
    )
    pauses.add_argument(
        '--watching',
        default=WATCHING,
        type=parse_pause,
        metavar='SECONDS',
        help=(
            'Wait between the last move and the link that drops.\n'
            f'Default: { WATCHING }.'
        ),
    )

    return parser


def hardware_frame(orientation: str) -> Callable[[Algorithm], Algorithm]:
    """
    Build what writes an algorithm the way the hardware reports it.

    A cube has no idea how it is held: its sensors name the face they
    sit on and nothing else, so an algorithm played by hands holding it
    in ``DF`` reaches the stream turned the other way round - and it is
    the client, given the same orientation, that turns it back for the
    window. Publishing what was typed would hand it a frame already in
    the point of view of the hands, and the window would translate it
    once too many.

    So the very translation the client undoes is done here first, with
    the conjugate rotations: what is typed is what is seen, and what is
    published is what a cube would have said of it.

    Args:
        orientation: The two faces the cube is held by, empty for an
            algorithm already written in the frame of the hardware.

    Returns:
        A transform from the point of view of the hands to the one of
        the hardware.

    """
    transform: Callable[[Algorithm], Algorithm] = translate_moves(
        invert_moves(
            parse_moves(
                ORIENTATION_FACE_MOVES[orientation] if orientation else '',
            ),
        ),
    )

    return transform


def watch_command(options: Namespace, config: Config) -> str:
    """
    Write the ``cube-cast`` command this rehearsal is watched with.

    What the configuration already says is left out of it: an option
    printed here is one the window needs to be told, and one it does
    not is noise between the two commands to be typed.

    Args:
        options: The arguments the script was called with.
        config: The configuration of term-timer, as it was read.

    Returns:
        The command line to open a window on this rehearsal.

    """
    command = 'cube-cast'

    if options.endpoint != configured_endpoint(config):
        command += f' -e { options.endpoint }'

    if options.orientation != configured_cube(config, ORIENTATION_SETTING):
        command += f' -o { options.orientation }'

    return command


def rehearse(
        publisher: Publisher,
        setup: Algorithm,
        moves: Algorithm,
        pauses: Pauses,
) -> None:
    """
    Play a cube connecting, turning and going away, over and over.

    Args:
        publisher: What the messages are published by.
        setup: What the cube describes itself in, in the frame of the
            hardware.
        moves: What it turns once connected, in the same frame.
        pauses: What is waited at each moment of the cycle.

    """
    serial = 1

    while True:
        cube = VCube()
        cube.rotate(setup)

        print('The cube connects')
        publisher.send(LINK_TOPIC, {'connected': True, 'reason': 'opened'})

        print(
            f'Silence for { pauses.connection }s: '
            'connected, describing nothing',
        )
        time.sleep(pauses.connection)

        publisher.send(HARDWARE_TOPIC, {'hardware_name': HARDWARE_NAME})
        publisher.send(BATTERY_TOPIC, {'level': BATTERY_LEVEL})
        publisher.send(
            FACELETS_TOPIC,
            {
                'facelets': cube.state,
                'serial': serial,
            },
        )

        print(f'Gathering for { pauses.gathering }s')
        time.sleep(pauses.gathering)

        for move in moves:
            serial += 1
            # Stamped on a clock of its own, as a cube stamps: it is
            # what a client reads to tell how old a move already is by
            # the time it hears of it, and a phantom publishing none
            # would rehearse everything but the delay a real one has.
            publisher.send(
                MOVE_TOPIC,
                {
                    'move': str(move),
                    'serial': serial,
                    'cube_timestamp': time.monotonic() * MILLISECONDS,
                },
            )
            time.sleep(pauses.pace)

        print(f'Watching for { pauses.watching }s')
        time.sleep(pauses.watching)

        print('The cube goes away')
        publisher.send(LINK_TOPIC, {'connected': False, 'reason': 'lost'})

        print(f'Silence for { pauses.silence }s: the core alone')
        time.sleep(pauses.silence)


def main() -> int:
    """
    Bind the socket term-timer publishes on, and rehearse on it.

    Returns:
        Exit code, always 0: a rehearsal ends when it is stopped.

    """
    # Read before the arguments: what term-timer was configured with is
    # where the rehearsal is held, and the command line is what says
    # otherwise
    config = load_config()
    options = build_parser(config).parse_args(sys.argv[1:])

    translate = hardware_frame(options.orientation)
    setup = translate(options.setup)
    moves = translate(options.algorithm)
    pauses = Pauses.from_options(options)

    publisher = Publisher(options.endpoint)

    print(f'Publishing on { options.endpoint }')
    print(f'Session { publisher.session }, watch it with: '
          f'{ watch_command(options, config) }')
    print(f'Connecting on { setup or "a solved cube" }, turning { moves }')

    time.sleep(SETTLE)

    try:
        rehearse(publisher, setup, moves, pauses)
    except KeyboardInterrupt:
        # A client outlives this publisher, and a cube that stopped
        # being published without a word would stay whole in its
        # window: what is quit here is a link like any other, and it
        # says so before the process goes. The wait is the one the
        # socket needs to write the frame out - a message published and
        # closed upon in the same breath never leaves.
        print()
        print('The cube goes away for good')
        publisher.send(LINK_TOPIC, {'connected': False, 'reason': 'closed'})
        time.sleep(SETTLE)
    finally:
        publisher.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
