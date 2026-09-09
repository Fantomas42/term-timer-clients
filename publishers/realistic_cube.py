"""
A cube that solves, at the pace and the payload of a real one.

``phantom_cube.py`` rehearses the shape of the stream; this rehearses
its *weight*. Every cycle draws a fresh WCA-style scramble, connects on
it, and solves it back to a plain cube - the solve being the exact
inverse of the scramble, so the cube lands solved every single time
without a solver of its own to carry. Moves are not metronomed: the
hand pauses to look ahead, bursts through what it has already read,
and a double turn reaches the stream as the two quarter clicks a
sensor actually feels rather than as one event nothing wearing a cube
would ever report. The gyroscope never stops either, awake between
moves as it is caught up in one - the two together, together with
every field ``PROTOCOL.md`` lists for a driver event, is what makes a
capture of this rehearsal worth mistaking for a capture of a hand.

    python publishers/realistic_cube.py
    cube-cast
    tt-tail

``--orientation`` holds the cube the way ``--setup``/``--algorithm``
do on ``phantom_cube.py``: the scramble is generated in the frame of
the hands, and turned into the frame of the hardware before it ever
reaches the wire.

    python publishers/realistic_cube.py -o DF
    cube-cast -o DF

``--tps`` is the average of the hand, not a metronome reading: a
cycle solved slower or faster is a cycle whose pauses shrink or grow
with it, never one where every move takes the very same beat.

    python publishers/realistic_cube.py --tps 4
"""
# A debug script rather than a client: it writes the stream instead of
# reading it, nothing imports it, and its prints are its whole output.
# `random` paces moves and wobbles a quaternion, never anything a
# security boundary rests on, and the raw driver bytes this phantom
# stands in for are hashed for a stable placeholder rather than kept
# secret from anybody.
# ruff: file-ignore[implicit-namespace-package, print]
# ruff: file-ignore[suspicious-non-cryptographic-random-usage]
# ruff: file-ignore[hashlib-insecure-hash-function]
import hashlib
import json
import random
import sys
import time
import uuid
from argparse import ArgumentTypeError
from argparse import Namespace
from collections.abc import Callable

import zmq
from cubing_algs.algorithm import Algorithm
from cubing_algs.constants import ORIENTATION_FACE_MOVES
from cubing_algs.constants import ORIENTATIONS
from cubing_algs.display.gl.transforms import Quat
from cubing_algs.display.gl.transforms import Vec3
from cubing_algs.move import Move
from cubing_algs.parsing import parse_moves
from cubing_algs.scrambler.nxn import scramble
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

# Where a cube is rehearsed when term-timer configured no publisher,
# the very one phantom_cube.py falls back on: two rehearsals of the
# same protocol have no reason to be watched on two different ports.
FALLBACK_ENDPOINT = 'tcp://127.0.0.1:5556'

ORIENTATION_SETTING = 'orientation'

# Topics, spelled out rather than read off the protocol module for the
# reason phantom_cube.py already gives: a publisher names what it
# emits, a client subscribes to a prefix.
LINK_TOPIC = 'cube.link'

HARDWARE_TOPIC = 'cube.hardware'

CONFIG_TOPIC = 'cube.config'

BATTERY_TOPIC = 'cube.battery'

FACELETS_TOPIC = 'cube.facelets'

MOVE_TOPIC = 'cube.move'

GYRO_TOPIC = 'cube.gyro'

SOLVED_TOPIC = 'cube.solved'

SOURCE = 'solve'

HARDWARE_NAME = 'GANi3'

HARDWARE_VERSION = '1.2'

SOFTWARE_VERSION = '4.2.20240115'

MILLISECONDS = 1000.0

BATTERY_LEVEL = 80

CHARGING_STATE = 'none'

CUBE_SIZE = 3

# The faces as a real driver numbers them, confirmed against every
# capture this repository carries: never a double among them, a
# sensor only ever feeling a quarter turn at a time.
FACE_INDEXES = {
    'U': 0,
    'R': 1,
    'F': 2,
    'D': 3,
    'L': 4,
    'B': 5,
}

# What a window already waiting is given to finish subscribing, the
# same settle phantom_cube.py opens on and for the same reason.
SETTLE = 0.2

# The pauses either side of a solve, in the order they are waited.
SILENCE = 3.0

CONNECTION = 1.0

GATHERING = 3.0

WATCHING = 1.5

# The average cadence a solve is turned at - a mean the pacing below
# argues with move by move, never the beat every move lands on.
TPS = 6.5

# How wide a single move's delay is allowed to wander around the beat
# ``--tps`` sets, and how often that delay grows into a longer pause -
# a hand reading ahead of its fingers rather than typing blind.
PACE_SPREAD = (0.55, 1.6)

PAUSE_CHANCE = 0.1

PAUSE_RANGE = (0.3, 0.8)

# The gap between the two quarter turns a double reaches the stream
# as: closer together than two distinct moves, being one continuous
# turn of the hand rather than two.
SPLIT_GAP_RANGE = (0.05, 0.11)

# How often the gyroscope speaks while it is being watched, and by how
# much two ticks may drift apart - both read off the idle stretches of
# this repository's own captures.
GYRO_INTERVAL = 0.075

GYRO_JITTER = 0.03

# How far a quaternion is nudged on one tick, at rest and mid turn,
# and how long a move keeps the reading in its "mid turn" state.
IDLE_WOBBLE = 0.01

ACTIVE_WOBBLE = 0.12

ACTIVITY_DECAY = 0.25

# The angular velocity a tick reports, at rest and mid turn - a hand
# holding still is a hand reading almost always zero, not a hand
# reading small numbers.
IDLE_AXIS_VALUES = (0, 0, 0, 0, 1, -1)

ACTIVE_AXIS_SPREAD = 6


class Publisher:
    """
    The socket term-timer publishes on, and the counter of the stream.

    The very same shape as ``phantom_cube.py``'s: it binds, so the
    order the two sides are started in never matters, and a session
    identifier drawn at every run is what lets a client tell this
    rehearsal restarting from one still running.
    """

    def __init__(self, endpoint: str) -> None:
        """
        Bind the endpoint, under a session of this process alone.

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

    def send(
            self,
            topic: str,
            data: dict[str, object],
            *,
            announce: bool = True,
    ) -> None:
        """
        Publish one message, topic frame then payload frame.

        The gyroscope ticks tens of times a second, and printing every
        one of them would bury the phases of the cycle it is meant to
        illustrate under noise - the very reason ``tt-tail`` has a
        ``QUIET_TOPICS`` of its own.

        Args:
            topic: The topic the message is published under.
            data: The payload, always an object.
            announce: Whether this message is worth a line on its own.

        """
        envelope = self.envelope(topic, data)
        self.seq += 1

        self.socket.send_multipart(
            [topic.encode(), json.dumps(envelope).encode()],
        )

        if announce:
            print(f'  { topic }')

    def close(self) -> None:
        """Close the socket, once what it still holds has gone out."""
        self.socket.close()


def parse_pause(value: str) -> float:
    """
    Read the seconds a pause argument is written in.

    Args:
        value: The argument, as it was typed.

    Returns:
        The pause, in seconds.

    Raises:
        ArgumentTypeError: When the argument names no duration.

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


def parse_tps(value: str) -> float:
    """
    Read the turns per second a cadence argument is written in.

    Args:
        value: The argument, as it was typed.

    Returns:
        The cadence, in turns per second.

    Raises:
        ArgumentTypeError: When the argument names no positive cadence.

    """
    try:
        tps = float(value)
    except ValueError as error:
        msg = f'"{ value }" is not a number of turns per second'
        raise ArgumentTypeError(msg) from error

    if tps <= 0:
        msg = f'"{ value }" is not a positive cadence'
        raise ArgumentTypeError(msg)

    return tps


def build_parser(config: Config) -> ArgumentParser:
    """
    Describe what the rehearsal takes on its command line.

    Args:
        config: The configuration of term-timer, as it was read.

    Returns:
        The parser of the ``realistic_cube.py`` arguments.

    """
    parser = ArgumentParser(
        description=(
            'Publish a solve of a cube that is not there, at the pace '
            'and the payload of one that is.'
        ),
        epilog=(
            'Examples:\n'
            '  realistic_cube.py\n'
            '  realistic_cube.py -o DF\n'
            '  realistic_cube.py --tps 4\n'
        ),
    )

    endpoint = configured_endpoint(config) or FALLBACK_ENDPOINT
    orientation = configured_cube(config, ORIENTATION_SETTING)

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
    parser.add_argument(
        '--tps',
        default=TPS,
        type=parse_tps,
        metavar='TPS',
        help=(
            'Solve at this average of turns per second - a mean the\n'
            'pacing wanders around, never a beat every move lands on.\n'
            f'Default: { TPS }.'
        ),
    )

    pauses = parser.add_argument_group(
        'pauses',
        'What the rehearsal waits, in seconds, either side of a solve.',
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
            'Wait between the state and the first move, a scramble\n'
            'being inspected before it is solved.\n'
            f'Default: { GATHERING }.'
        ),
    )
    pauses.add_argument(
        '--watching',
        default=WATCHING,
        type=parse_pause,
        metavar='SECONDS',
        help=(
            'Wait between the solved report and the link that drops.\n'
            f'Default: { WATCHING }.'
        ),
    )

    return parser


def hardware_frame(orientation: str) -> Callable[[Algorithm], Algorithm]:
    """
    Build what writes an algorithm the way the hardware reports it.

    The very transform ``phantom_cube.py`` opens on: a cube has no
    idea how it is held, so what is typed in the frame of the hands is
    turned into the frame of the hardware before it reaches the wire,
    with the client undoing exactly that on the way back in.

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


def stamp() -> dict[str, object]:
    """
    Read the two clocks a driver event always travels with.

    ``clock`` stands for the free-running counter a driver reads its
    own off - this phantom has none of its own to read, so it borrows
    the monotonic clock of the process, in the same unit the captures
    of this repository's own suite carry theirs in.

    Returns:
        The ``clock`` and ``timestamp`` fields of one driver event.

    """
    return {
        'clock': time.monotonic_ns(),
        'timestamp': time.time(),
    }


def raw_state(facelets: str) -> str:
    """
    Stand in for the raw bytes a real driver reports next to a state.

    This phantom parses no bytes off a cube, so nothing here is a
    decoded telemetry frame - it is derived from the facelets it sits
    next to instead of fabricated whole cloth, so a ``state`` worth
    the name changes exactly when the facelets next to it do.

    Args:
        facelets: The 54 characters the state is read off.

    Returns:
        A stand-in raw state, stable for one given facelets string.

    """
    return hashlib.sha1(facelets.encode()).hexdigest()[:20]


def split_move(move: Move) -> list[Move]:
    """
    Break a half turn into the two quarter turns hardware reports.

    A GAN's face sensor only ever feels a quarter at a time: a 180°
    turn played by the hand in one motion still reaches the stream as
    two identical quarter turns, and no capture this repository holds
    ever carries a double - ``FACE_INDEXES`` was built by reading
    every one of them.

    Args:
        move: The move to report, in the frame of the hardware.

    Returns:
        The move alone, or the two quarter turns making up a double.

    """
    if not move.is_double:
        return [move]

    quarter = Move(move.base_move)

    return [quarter, quarter]


def move_delay(tps: float) -> float:
    """
    Draw how long a hand waits before its next move lands.

    Wandering around the beat ``tps`` sets rather than sitting on it,
    and occasionally growing into a longer pause - a hand reading
    ahead of its fingers between one look and the next, not a
    metronome nothing wearing a cube would ever be turned by.

    Args:
        tps: The average cadence the solve is turned at.

    Returns:
        The delay before the next move, in seconds.

    """
    delay = (1.0 / tps) * random.uniform(*PACE_SPREAD)

    if random.random() < PAUSE_CHANCE:
        delay += random.uniform(*PAUSE_RANGE)

    return delay


class CubeClock:
    """
    The cube's own millisecond counter, running since it woke up.

    Drawn at random rather than started at zero: a real cube has
    already been running for a while by the time it connects, and
    ``MoveClock`` on the other end reads the *jitter* of this counter
    against the arrival of what it stamps, never its origin.
    """

    def __init__(self) -> None:
        """Wake the cube up somewhere past its own boot."""
        self.base = random.uniform(3_000.0, 600_000.0)
        self.started = time.monotonic()

    def read(self) -> float:
        """
        Tell the time on the cube's own clock, right now.

        Returns:
            The cube's clock, in milliseconds.

        """
        return self.base + (time.monotonic() - self.started) * MILLISECONDS


class GyroSimulator:
    """
    A hand that never quite holds the cube still.

    One quaternion is carried from tick to tick and nudged a little
    further every time, a small turn around a random axis composed
    onto the last one - a random walk rather than a fixed jitter,
    which is what an idle stretch of every capture this repository
    holds looks like under a microscope. ``stir()`` is what a move
    calls to widen that nudge and the velocity read alongside it for
    ``ACTIVITY_DECAY`` seconds, the cube caught mid turn rather than
    merely held.
    """

    def __init__(self) -> None:
        """Start the cube held still, in an orientation of its own."""
        self.pose = Quat.identity()
        self.active_until = 0.0

    def stir(self) -> None:
        """Mark the cube as being turned, starting right now."""
        self.active_until = time.monotonic() + ACTIVITY_DECAY

    def tick(self) -> tuple[Quat, tuple[int, int, int]]:
        """
        Read the next quaternion and angular velocity off the cube.

        Returns:
            The pose after this tick, and the velocity it was read
            with.

        """
        active = time.monotonic() < self.active_until
        wobble = ACTIVE_WOBBLE if active else IDLE_WOBBLE

        axis = Vec3(
            random.uniform(-1, 1),
            random.uniform(-1, 1),
            random.uniform(-1, 1),
        )
        nudge = Quat.from_axis_angle(
            axis, random.uniform(-wobble, wobble),
        )
        self.pose = (nudge * self.pose).normalized()

        if active:
            velocity = (
                random.randint(-ACTIVE_AXIS_SPREAD, ACTIVE_AXIS_SPREAD),
                random.randint(-ACTIVE_AXIS_SPREAD, ACTIVE_AXIS_SPREAD),
                random.randint(-ACTIVE_AXIS_SPREAD, ACTIVE_AXIS_SPREAD),
            )
        else:
            velocity = (
                random.choice(IDLE_AXIS_VALUES),
                random.choice(IDLE_AXIS_VALUES),
                random.choice(IDLE_AXIS_VALUES),
            )

        return self.pose, velocity


def publish_gyro(publisher: Publisher, gyro: GyroSimulator) -> None:
    """
    Publish one gyroscope tick, on behalf of a hand holding the cube.

    Args:
        publisher: What the message is published by.
        gyro: What the tick is read off.

    """
    quaternion, velocity = gyro.tick()

    publisher.send(
        GYRO_TOPIC,
        {
            'quaternion': {
                'w': quaternion.w,
                'x': quaternion.x,
                'y': quaternion.y,
                'z': quaternion.z,
            },
            'velocity': {
                'x': velocity[0],
                'y': velocity[1],
                'z': velocity[2],
            },
            **stamp(),
        },
        announce=False,
    )


def settle(
        publisher: Publisher,
        gyro: GyroSimulator,
        duration: float,
) -> None:
    """
    Wait out a pause, feeding the gyroscope while it lasts.

    A cube in hand never falls silent on that plane alone: every pause
    of the cycle but the one nothing is connected in - a plain
    ``time.sleep()``, never this - is spent ticking the gyroscope at
    its own cadence instead of sleeping through it whole, which is
    what makes the rest of a solve - the look-ahead, the inspection -
    as much a rehearsal of the stream as a move is.

    Args:
        publisher: What a gyroscope tick is published by.
        gyro: What is ticked.
        duration: How long the pause lasts, in seconds.

    """
    deadline = time.monotonic() + duration

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return

        step = min(
            remaining,
            GYRO_INTERVAL + random.uniform(0, GYRO_JITTER),
        )
        time.sleep(step)
        publish_gyro(publisher, gyro)


class Telemetry:
    """
    What a phantom cube carries for the life of one connection.

    Its gyroscope and its own clock - the two things a hand does not
    stop feeding between two moves, kept together because ``rehearse()``
    starts them together, at the very moment the link comes up, and
    lets them go together when it drops.
    """

    def __init__(self) -> None:
        """Wake the cube's gyroscope and its own clock up together."""
        self.gyro = GyroSimulator()
        self.clock = CubeClock()


def play_solve(
        publisher: Publisher,
        telemetry: Telemetry,
        moves: Algorithm,
        serial: int,
        tps: float,
) -> tuple[int, float]:
    """
    Turn a solve out at the cadence of a hand, and never a metronome.

    Every double is split before it is played, so what reaches the
    stream is exactly what a sensor would report - two quarter turns
    rather than one event a real cube never publishes - and the
    gyroscope is stirred the moment each of them lands, an idle wobble
    turning into the wider one of a cube caught mid turn for the
    ``ACTIVITY_DECAY`` seconds that follow.

    Args:
        publisher: What every message is published by.
        telemetry: The gyroscope stirred by a landing move and ticked
            between two, and the cube's own clock, read at every move.
        moves: The solve, already in the frame of the hardware.
        serial: The serial of the last message published before this
            solve, so the count carries on from the state that opened
            it rather than starting over.
        tps: The average cadence the solve is turned at.

    Returns:
        The serial after the last move, and the cube's own clock the
        moment it landed - what a ``cube.solved`` right behind it is
        stamped with.

    """
    gyro, clock = telemetry.gyro, telemetry.clock
    last_stamp = clock.read()

    for move in moves:
        for index, quarter in enumerate(split_move(move)):
            delay = (
                random.uniform(*SPLIT_GAP_RANGE)
                if index
                else move_delay(tps)
            )
            settle(publisher, gyro, delay)

            serial += 1
            gyro.stir()
            last_stamp = clock.read()

            fields = stamp()
            publisher.send(
                MOVE_TOPIC,
                {
                    'move': str(quarter),
                    'serial': serial,
                    'face': FACE_INDEXES[quarter.base_move],
                    'direction': 0 if quarter.is_clockwise else 1,
                    'cube_timestamp': last_stamp,
                    'local_timestamp': fields['timestamp'],
                    **fields,
                },
            )

    return serial, last_stamp


def rehearse(
        publisher: Publisher,
        translate: Callable[[Algorithm], Algorithm],
        tps: float,
        pauses: dict[str, float],
) -> None:
    """
    Play a cube connecting, solving and going away, over and over.

    A fresh scramble every cycle, and a solve that is exactly its
    inverse: the cube always lands solved, with no solver of its own
    to carry, and no two cycles ever turn the same moves at the same
    pace.

    Args:
        publisher: What the messages are published by.
        translate: What turns a move from the frame of the hands into
            the one of the hardware.
        tps: The average cadence a solve is turned at.
        pauses: What is waited at each moment of the cycle, keyed by
            name.

    """
    while True:
        algorithm = scramble(CUBE_SIZE)
        setup = translate(algorithm)
        solve = translate(invert_moves(algorithm))

        cube = VCube()
        cube.rotate(setup)

        print(f'Scrambled on { algorithm }')

        print('The cube connects')
        publisher.send(LINK_TOPIC, {'connected': True, 'reason': 'opened'})

        telemetry = Telemetry()

        print(
            f'Silence for { pauses["connection"] }s: '
            'connected, describing nothing',
        )
        settle(publisher, telemetry.gyro, pauses['connection'])

        publisher.send(
            HARDWARE_TOPIC,
            {
                'hardware_name': HARDWARE_NAME,
                'hardware_version': HARDWARE_VERSION,
                'software_version': SOFTWARE_VERSION,
                'gyroscope_enabled': True,
                'gyroscope_ready': True,
                **stamp(),
            },
        )
        publisher.send(
            CONFIG_TOPIC,
            {
                'gyroscope_enabled': True,
                'gyroscope_ready': True,
                **stamp(),
            },
        )
        publisher.send(
            BATTERY_TOPIC,
            {
                'level': BATTERY_LEVEL,
                'charging_state': CHARGING_STATE,
                **stamp(),
            },
        )

        serial = 1
        facelets = cube.state
        publisher.send(
            FACELETS_TOPIC,
            {
                'facelets': facelets,
                'serial': serial,
                'state': raw_state(facelets),
                **stamp(),
            },
        )

        print(f'Gathering for { pauses["gathering"] }s: reading the scramble')
        settle(publisher, telemetry.gyro, pauses['gathering'])

        print(f'Solving { len(solve) } moves at ~{ tps } tps')
        serial, last_stamp = play_solve(
            publisher, telemetry, solve, serial, tps,
        )

        print('The cube reports solved')
        publisher.send(
            SOLVED_TOPIC,
            {
                'cube_timestamp': last_stamp,
                **stamp(),
            },
        )

        print(f'Watching for { pauses["watching"] }s')
        settle(publisher, telemetry.gyro, pauses['watching'])

        print('The cube goes away')
        publisher.send(LINK_TOPIC, {'connected': False, 'reason': 'lost'})

        print(f'Silence for { pauses["silence"] }s: the core alone')
        time.sleep(pauses['silence'])


def main() -> int:
    """
    Bind the socket term-timer publishes on, and rehearse on it.

    Returns:
        Exit code, always 0: a rehearsal ends when it is stopped.

    """
    config = load_config()
    options = build_parser(config).parse_args(sys.argv[1:])

    translate = hardware_frame(options.orientation)
    pauses = {
        'silence': options.silence,
        'connection': options.connection,
        'gathering': options.gathering,
        'watching': options.watching,
    }

    publisher = Publisher(options.endpoint)

    print(f'Publishing on { options.endpoint }')
    print(f'Session { publisher.session }, watch it with: '
          f'{ watch_command(options, config) }')

    time.sleep(SETTLE)

    try:
        rehearse(publisher, translate, options.tps, pauses)
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
