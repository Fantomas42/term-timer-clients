"""
The pieces of news a window tells, replayed over and over.

Nothing else in ``publishers/`` publishes the session plane, and two
publishers cannot bind the same endpoint: settling the breath a window
blows on an attempt being over, and the one it blows on a scramble
being laid, takes a script saying both planes at once. This
is that publisher of its own.

It rehearses no honest attempt - ``realistic_cube.py`` already does
that for the cube plane - it **replays the two moments in a loop**,
which is what a duration, a reach, a curve and two hues are settled
with:

    cube.link · cube.hardware · cube.battery · cube.facelets

    over and over:
      session.state  scrambling
      cube.facelets  the scramble laid on the cube
      session.state  scrambled            <- the cold breath
      session.state  inspecting, solving
      a few cube.move, putting it back together
      session.state  stop                 <- the warm breath

Both breaths are values of ``session.state``, which is the whole of
why this script exists: nothing of the cube plane says either, and
``cube.solved`` is not published at all - a window reads nothing of
it, and a bench publishing it would be settling nothing.

It binds where term-timer binds, so a window opens on it with nothing
typed either side:

    python publishers/flare_cube.py
    cube-cast

Every pause of the loop is an argument of its own, so each of the two
breaths is watched for as long as it is being settled:

    python publishers/flare_cube.py --stop 6 --scrambled 1

Everything is published in the frame of the hardware, which is what a
cube reports in: a window watching this with ``-o`` turns it back the
way it turns a real one.
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
from dataclasses import dataclass
from typing import Self

import zmq
from cubing_algs.algorithm import Algorithm
from cubing_algs.exceptions import CubingAlgsError
from cubing_algs.parsing import parse_moves
from cubing_algs.transform.invert import invert_moves
from cubing_algs.vcube import VCube

from term_timer_clients.argparser import ArgumentParser
from term_timer_clients.argparser import parse_stream_endpoint
from term_timer_clients.config import Config
from term_timer_clients.config import configured_endpoint
from term_timer_clients.config import load_config
from term_timer_clients.protocol import PROTOCOL_VERSION

# Where the two breaths are settled when term-timer configured no
# publisher: a port of its own, so a session left running is never
# talked over
FALLBACK_ENDPOINT = 'tcp://127.0.0.1:5556'

# The topics of the loop, of both planes, and they are written out
# here rather than read from the protocol module for the reason
# ``phantom_cube.py`` writes its own out: a client subscribes to a
# prefix, a publisher names every topic it emits.
LINK_TOPIC = 'cube.link'

HARDWARE_TOPIC = 'cube.hardware'

BATTERY_TOPIC = 'cube.battery'

FACELETS_TOPIC = 'cube.facelets'

MOVE_TOPIC = 'cube.move'

STATE_TOPIC = 'session.state'

# The states of a solve this loop walks through, in the order
# term-timer publishes them. Only two of them are news to a window -
# the scramble being laid, and the attempt being over - and the others
# are here because a state is published with the one before it, and a
# window has to be seen staying quiet on them.
SCRAMBLING_STATE = 'scrambling'

SCRAMBLED_STATE = 'scrambled'

INSPECTING_STATE = 'inspecting'

SOLVING_STATE = 'solving'

STOP_STATE = 'stop'

# What a session says it is, on every envelope it publishes. A timed
# solve, a training session ending on the very same `stop`.
SOURCE = 'solve'

HARDWARE_NAME = 'GANi3'

BATTERY_LEVEL = 80

# A cube counts its own milliseconds, a script counts in seconds.
MILLISECONDS = 1000.0

# What the cube is turned by while the scramble is being laid, written
# the way the hands write it. The solve is its inverse, so the cube
# truly is solved when the `stop` arrives - the window is being
# settled on a solve landing, and a cube left scrambled at the end of
# it would be settling it on something else.
SCRAMBLE = "R U R' U' F R2 U'"

# What a window already waiting is given to finish subscribing, once
# and outside the loop. Binding is not connecting: a PUB drops what it
# publishes to a peer whose subscription has not reached it yet.
SETTLE = 0.2

# The pauses of one cycle, in the order they are waited. Each is an
# argument of its own, and that is the whole point of this script: a
# breath is settled by being watched, and the two of them are watched
# one at a time.
SCRAMBLING = 1.0

SCRAMBLED = 3.0

INSPECTING = 1.0

PACE = 0.3

STOP = 4.0


@dataclass(frozen=True)
class Pauses:
    """What the loop waits, at each of the moments it has."""

    scrambling: float
    scrambled: float
    inspecting: float
    pace: float
    stop: float

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
            scrambling=options.scrambling,
            scrambled=options.scrambled,
            inspecting=options.inspecting,
            pace=options.pace,
            stop=options.stop,
        )


class Publisher:
    """
    The socket term-timer publishes on, and the counter of the stream.

    The very same shape as ``phantom_cube.py``'s: it binds, so the
    order the two sides are started in never matters, and a session
    identifier drawn at every run is what lets a client tell this
    loop restarting from one still running.
    """

    def __init__(self, endpoint: str, source: str) -> None:
        """
        Bind the endpoint, under a session of this process alone.

        Args:
            endpoint: The ZeroMQ endpoint to bind.
            source: What the session says it is, on every envelope.

        """
        self.endpoint = endpoint
        self.source = source
        self.session = uuid.uuid4().hex[:8]
        self.seq = 0
        self.state = ''

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
            'src': self.source,
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

    def announce(self, state: str) -> None:
        """
        Say what the session is now doing, and what it was doing before.

        The previous state is kept here rather than written out at
        every call: a state is read against the one before it, and a
        loop spelling both out by hand is a loop that will disagree
        with itself the day a step is inserted.

        Args:
            state: The state the session enters.

        """
        self.send(
            STATE_TOPIC,
            {
                'state': state,
                'previous': self.state,
                'at': time.monotonic_ns(),
            },
        )

        self.state = state

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
            could play. An algorithm refused after the socket is bound
            would leave a window waiting on a publisher that has
            already died.

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
            is exactly what an effect is settled against.

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
    Describe what the loop takes on its command line.

    The configuration is handed over rather than read here, as it is in
    every client: it is what the defaults are made of, and a parser
    built on an empty one is the loop with nothing configured
    anywhere.

    Args:
        config: The configuration of term-timer, as it was read.

    Returns:
        The parser of the ``flare_cube.py`` arguments.

    """
    parser = ArgumentParser(
        description='Publish the pieces of news a window tells.',
        epilog=(
            'Examples:\n'
            '  flare_cube.py\n'
            '  flare_cube.py --stop 6 --scrambled 1\n'
            '  flare_cube.py -s "R U R2 F\' L" --pace 0.1\n'
        ),
    )

    endpoint = configured_endpoint(config) or FALLBACK_ENDPOINT

    # Read by what every client reads its own with - an endpoint is
    # spelled the same way whether it is bound or connected to - but
    # declared here rather than by add_endpoint_argument(): that one
    # says "connect to", which is the one thing a publisher does not
    # do.
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
        '-s', '--scramble',
        default=SCRAMBLE,
        type=parse_algorithm,
        metavar='SCRAMBLE',
        help=(
            'Lay this scramble on the cube, and solve it back with\n'
            'its inverse: the cube truly is solved at the stop.\n'
            f'Default: { SCRAMBLE }.'
        ),
    )
    pauses = parser.add_argument_group(
        'pauses',
        'What the loop waits, in seconds, at each of the moments of '
        'one cycle.',
    )

    pauses.add_argument(
        '--scrambling',
        default=SCRAMBLING,
        type=parse_pause,
        metavar='SECONDS',
        help=(
            'Wait while the scramble is being laid on the cube.\n'
            f'Default: { SCRAMBLING }.'
        ),
    )
    pauses.add_argument(
        '--scrambled',
        default=SCRAMBLED,
        type=parse_pause,
        metavar='SECONDS',
        help=(
            'Watch the cold breath, the scramble being laid.\n'
            f'Default: { SCRAMBLED }.'
        ),
    )
    pauses.add_argument(
        '--inspecting',
        default=INSPECTING,
        type=parse_pause,
        metavar='SECONDS',
        help=(
            'Wait between the inspection and the first move.\n'
            f'Default: { INSPECTING }.'
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
        '--stop',
        default=STOP,
        type=parse_pause,
        metavar='SECONDS',
        help=(
            'Watch the warm breath, the attempt being over.\n'
            f'Default: { STOP }.'
        ),
    )

    return parser


def watch_command(options: Namespace, config: Config) -> str:
    """
    Write the ``cube-cast`` command this loop is watched with.

    Args:
        options: The arguments the script was called with.
        config: The configuration of term-timer, as it was read.

    Returns:
        The command line to open a window on this loop.

    """
    command = 'cube-cast'

    if options.endpoint != configured_endpoint(config):
        command += f' -e { options.endpoint }'

    return command


def connect(publisher: Publisher, cube: VCube, serial: int) -> None:
    """
    Play the cube connecting and describing itself, once for the run.

    It is done once and outside the loop on purpose: what is being
    settled here is the two breaths and not the implosion, and a cube
    that came and went between two of them would blow itself apart
    over the very picture being looked at.

    Args:
        publisher: What the messages are published by.
        cube: The cube as it stands when the link comes up.
        serial: Counter the driver stamps its states with.

    """
    print('The cube connects')
    publisher.send(LINK_TOPIC, {'connected': True, 'reason': 'opened'})
    publisher.send(HARDWARE_TOPIC, {'hardware_name': HARDWARE_NAME})
    publisher.send(BATTERY_TOPIC, {'level': BATTERY_LEVEL})
    publisher.send(
        FACELETS_TOPIC,
        {'facelets': cube.state, 'serial': serial},
    )


def play(publisher: Publisher, moves: Algorithm, serial: int,
         pace: float) -> int:
    """
    Turn the cube one move at a time, at the pace of a hand.

    Args:
        publisher: What the messages are published by.
        moves: What the cube is turned by.
        serial: Counter the driver stamps its moves with.
        pace: Seconds waited between two moves.

    Returns:
        The counter, where the last move left it.

    """
    for move in moves:
        serial += 1
        publisher.send(
            MOVE_TOPIC,
            {
                'move': str(move),
                'serial': serial,
                # Stamped on a clock of its own, as a cube stamps: it
                # is what a client reads to tell how old a move
                # already is by the time it hears of it.
                'cube_timestamp': time.monotonic() * MILLISECONDS,
            },
        )
        time.sleep(pace)

    return serial


def replay(
        publisher: Publisher,
        scramble: Algorithm,
        pauses: Pauses,
) -> None:
    """
    Play a scramble being laid and an attempt ending, over and over.

    The moments are one cycle rather than one run of the script each,
    for the reason the pauses are arguments: what a hue and a duration
    are settled against is the other one arriving a few seconds later,
    and two windows side by side would be settled against two cubes.

    Args:
        publisher: What the messages are published by.
        scramble: What the cube is scrambled by, the solve being its
            inverse.
        pauses: What is waited at each moment of the cycle.

    """
    solve = scramble.transform(invert_moves)
    serial = 1

    connect(publisher, VCube(), serial)

    while True:
        cube = VCube()

        print('The scramble is laid on the cube')
        publisher.announce(SCRAMBLING_STATE)
        time.sleep(pauses.scrambling)

        cube.rotate(scramble)
        serial += 1
        publisher.send(
            FACELETS_TOPIC,
            {'facelets': cube.state, 'serial': serial},
        )

        print(f'The cold breath, watched for { pauses.scrambled }s')
        publisher.announce(SCRAMBLED_STATE)
        time.sleep(pauses.scrambled)

        publisher.announce(INSPECTING_STATE)
        time.sleep(pauses.inspecting)

        print(f'Solving { len(solve) } moves back')
        publisher.announce(SOLVING_STATE)
        serial = play(publisher, solve, serial, pauses.pace)

        print(f'The warm breath, watched for { pauses.stop }s')
        publisher.announce(STOP_STATE)
        time.sleep(pauses.stop)


def main() -> int:
    """
    Bind the socket term-timer publishes on, and replay the two breaths.

    Returns:
        Exit code, always 0: a loop ends when it is stopped.

    """
    # Read before the arguments: what term-timer was configured with is
    # where the loop is held, and the command line is what says
    # otherwise
    config = load_config()
    options = build_parser(config).parse_args(sys.argv[1:])

    pauses = Pauses.from_options(options)
    publisher = Publisher(options.endpoint, SOURCE)

    print(f'Publishing on { options.endpoint } as a { SOURCE } session')
    print(f'Session { publisher.session }, watch it with: '
          f'{ watch_command(options, config) }')
    print(f'Scrambling with { options.scramble }')

    time.sleep(SETTLE)

    try:
        replay(publisher, options.scramble, pauses)
    except KeyboardInterrupt:
        # A client outlives this publisher, and a cube that stopped
        # being published without a word would stay whole in its
        # window: what is quit here is a link like any other, and it
        # says so before the process goes.
        print()
        print('The cube goes away for good')
        publisher.send(LINK_TOPIC, {'connected': False, 'reason': 'closed'})
        time.sleep(SETTLE)
    finally:
        publisher.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
