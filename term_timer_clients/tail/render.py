"""What a message of the stream looks like, read out loud."""
import shutil
import textwrap
from collections.abc import Mapping
from collections.abc import Sequence
from datetime import UTC
from datetime import datetime
from typing import Any
from typing import Final

from term_timer_clients.protocol import CUBE_PREFIX
from term_timer_clients.protocol import Envelope
from term_timer_clients.tail import ansi
from term_timer_clients.tail.ansi import Paint

BLOCK_OPEN: Final = '┌'

BLOCK_BODY: Final = '│'

BLOCK_CLOSE: Final = '└'

RULE: Final = '─'

SEPARATOR: Final = ' · '

ALERT_MARK: Final = '⚠'

INDENT: Final = '  '

# What separates a field name from what it carries, and what an inlined
# mapping is read by: two spaces, so that a value never touches the
# name of the next one
GAP: Final = '  '

DEFAULT_WIDTH: Final = 80

# Under this, a wrapped value is more indentation than text, and the
# block reads as one column anyway
MINIMUM_WIDTH: Final = 40

# Digits kept of a float the stream carries. A quaternion writes
# seventeen of them, and four of those on one line is a line nobody
# reads: what a tail is for is seeing the cube turn, not weighing it
PRECISION: Final = 6

FACES: Final = 6

# Fields naming an instant of the stream itself. The day is the day the
# client is running, so only the time of it is shown
CLOCK_FIELDS: Final = frozenset({'ts', 'timestamp', 'local_timestamp'})

# Fields naming an instant that is not now: a solve of yesterday, a
# card due next week
DATE_FIELDS: Final = frozenset({'date', 'due'})

MILLISECOND_FIELDS: Final = frozenset({'cube_timestamp'})

# The solve times of the session plane, in nanoseconds, as the session
# file spells them. The three of a record are named after what a record
# is rather than after what it holds, and are times all the same: a
# personal best written in nanoseconds is a personal best nobody reads
NANOSECOND_FIELDS: Final = frozenset({
    'time', 'value', 'previous', 'delta',
})

FACELETS_FIELDS: Final = frozenset({'facelets'})

HIGHLIGHT_FIELDS: Final = frozenset({'move'})

# What tells one cube from another, in a payload otherwise counted in
# numbers: read as an identity rather than as a quantity
SERIAL_FIELDS: Final = frozenset({'serial'})

# The nine states a solve goes through. Read off the value rather than
# off the field name: a "state" is also what a cube describes itself
# with, and what a trainer calls a card
SOLVE_STATES: Final = frozenset({
    'configure', 'init', 'scrambling', 'scrambled', 'inspecting',
    'inspected', 'solving', 'stop', 'saving',
})

# What ended a link or a session, and the one field the stream names
# it under. Read off the value like a state is, but only under that
# name: a reason is never anything else here, where a "state" is what
# a solve, a cube and a card all call themselves
REASON_FIELDS: Final = frozenset({'reason'})

REASON_COLORS: Final = {
    'opened': ansi.TRUE,
    'closed': ansi.HIGHLIGHT,
    'interrupted': ansi.BREAK,
    'lost': ansi.ALERT,
    'crashed': ansi.ALERT,
}

STATE_COLORS: Final = {
    'scrambling': ansi.BREAK,
    'inspecting': ansi.BREAK,
    'solving': ansi.TRUE,
    'stop': ansi.ALERT,
}

SCALARS: Final = (str, int, float, bool, type(None))

Painted = tuple[str, tuple[str, ...]]


def format_float(value: float) -> str:
    """
    Write a float short enough to be read at a glance.

    Args:
        value: The number, as the stream carries it.

    Returns:
        The number, without the zeros it ends on.

    """
    text = format(value, f'.{ PRECISION }f').rstrip('0').rstrip('.')

    return text or '0'


def format_time(value: float) -> str:
    """
    Write an instant of the stream as the time of day it happened at.

    Args:
        value: The instant, in epoch seconds.

    Returns:
        The time, to the millisecond, where the client is running.

    """
    stamp = datetime.fromtimestamp(value, tz=UTC).astimezone()

    return stamp.strftime('%H:%M:%S.%f')[:-3]


def format_date(value: float) -> str:
    """
    Write an instant that is not now, day included.

    Args:
        value: The instant, in epoch seconds.

    Returns:
        The date and the time, where the client is running.

    """
    stamp = datetime.fromtimestamp(value, tz=UTC).astimezone()

    return stamp.strftime('%Y-%m-%d %H:%M:%S')


def format_seconds(value: float) -> str:
    """
    Write a duration in the unit a solve is counted in.

    Args:
        value: The duration, in seconds.

    Returns:
        The duration, to the millisecond.

    """
    return f'{ format(value, ".3f") } s'


def format_gap(value: float) -> str:
    """
    Write the time between two messages.

    Args:
        value: The gap, in seconds.

    Returns:
        The gap, to the millisecond.

    """
    return f'{ format(value, ".3f") }s'


def format_facelets(value: str) -> str:
    """
    Space a state of the cube out into the faces it is made of.

    Args:
        value: The facelets, as the cube spells them.

    Returns:
        The facelets, one group per face, or as they came when they
        describe no cube whose faces divide evenly.

    """
    size, remainder = divmod(len(value), FACES)

    if remainder or not size:
        return value

    return ' '.join(
        value[index:index + size]
        for index in range(0, len(value), size)
    )


def text_codes(key: str, value: object) -> tuple[str, ...]:
    """
    Give a value written as text the color of what it says.

    Args:
        key: Name of the field it came under.
        value: The value itself.

    Returns:
        The colors it is painted with.

    """
    if key in HIGHLIGHT_FIELDS:
        return (ansi.HIGHLIGHT, ansi.BOLD)

    if key in REASON_FIELDS and value in REASON_COLORS:
        return (REASON_COLORS[str(value)], ansi.BOLD)

    if value in SOLVE_STATES:
        return (STATE_COLORS.get(str(value), ansi.HIGHLIGHT), ansi.BOLD)

    return (ansi.STRING,)


def scalar_codes(key: str, value: object) -> tuple[str, ...]:
    """
    Give a value the color of what it is.

    Args:
        key: Name of the field it came under.
        value: The value itself.

    Returns:
        The colors it is painted with.

    """
    if value is None:
        return (ansi.NOTHING,)

    if isinstance(value, bool):
        return (ansi.TRUE,) if value else (ansi.FALSE,)

    if isinstance(value, int | float):
        if key in SERIAL_FIELDS:
            return (ansi.SERIAL, ansi.BOLD)

        return (ansi.NUMBER,)

    return text_codes(key, value)


def is_scalar(value: object) -> bool:
    """
    Say whether a value is one this client writes on a single line.

    Args:
        value: The value, as the payload carries it.

    Returns:
        True when the value carries nothing else.

    """
    return isinstance(value, SCALARS)


class Renderer:
    """
    What turns an envelope into the lines it is printed as.

    It holds nothing of the stream, only what the picture is drawn
    with: the painter, and the width to wrap on. Nothing here reads a
    socket and nothing here writes - lines come out, and what becomes
    of them is the business of the client.

    The shape of a value is decided on the name of its field and on its
    type rather than on the topic it arrived under, which is what makes
    a topic added tomorrow readable today. A tail that only knew the
    topics of its own release would go blind on the very message worth
    looking at.
    """

    def __init__(self, paint: Paint, width: int = 0) -> None:
        """
        Prepare a renderer, over a terminal or over a given width.

        Args:
            paint: What wears the colors, or does not.
            width: Columns to wrap on, zero to follow the terminal.

        """
        self.paint = paint
        self.fixed = width
        self.width = width or DEFAULT_WIDTH

    def measure(self) -> None:
        """Read the width of the terminal again."""
        if self.fixed:
            return

        columns = shutil.get_terminal_size((DEFAULT_WIDTH, 0)).columns

        self.width = max(columns, MINIMUM_WIDTH)

    def rule(self, text: str, *codes: str) -> str:
        """
        Draw a line across the terminal, with a word on it.

        Args:
            text: What the line says.
            codes: The colors it is drawn with.

        Returns:
            The line, painted.

        """
        head = f'{ RULE * 2 } { text } '
        tail = RULE * max(self.width - len(head), 0)

        return self.paint(f'{ head }{ tail }', *codes)

    def session(self, envelope: Envelope) -> str:
        """
        Announce the session the messages that follow belong to.

        The identifier of a session and the command that opened it ride
        in every envelope rather than in a handshake, so nothing but a
        line of their own would ever show them.

        Args:
            envelope: The first message of the session.

        Returns:
            The line the session opens on.

        """
        self.measure()

        session_id = str(envelope.get('sid', ''))
        source = str(envelope.get('src', ''))

        text = SEPARATOR.join(
            part
            for part in (f'session { session_id }'.strip(), source)
            if part
        )

        return self.rule(text, ansi.BREAK)

    def farewell(self, envelope: Envelope) -> str:
        """
        Close the session the messages before belonged to.

        A stream that is over and one where nothing is happening look
        alike from here - both say nothing more - and the farewell is
        the only thing that ever tells them apart. So it is drawn
        across the terminal rather than left to scroll by with the
        block it comes from, the way the session was opened.

        Args:
            envelope: The ``session.end`` message.

        Returns:
            The line the session closes on.

        """
        self.measure()

        session_id = str(envelope.get('sid', ''))
        data = envelope.get('data')
        reason = (
            str(data.get('reason', ''))
            if isinstance(data, Mapping)
            else ''
        )

        text = SEPARATOR.join(
            part
            for part in (f'end of session { session_id }'.strip(), reason)
            if part
        )

        return self.rule(text, REASON_COLORS.get(reason, ansi.BREAK))

    def loss(self, count: int) -> str:
        """
        Say that messages were published and never read.

        Args:
            count: How many of them the sequence numbers skipped.

        Returns:
            The line the loss is reported on.

        """
        plural = '' if count == 1 else 's'

        return self.paint(
            f'{ ALERT_MARK } { count } message{ plural } lost',
            ansi.ALERT,
        )

    @staticmethod
    def plane_codes(topic: str) -> str:
        """
        Give a topic the color of the plane it belongs to.

        Args:
            topic: The topic, as the envelope names it.

        Returns:
            The color of its plane.

        """
        if topic.startswith(CUBE_PREFIX):
            return ansi.CUBE_PLANE

        return ansi.SESSION_PLANE

    def header(
            self,
            envelope: Envelope,
            gap: float,
            topic_gap: float,
    ) -> str:
        """
        Open a block, and say when and what it is.

        The two gaps are what the cadence of a solve is read from: one
        since the message before, one since the message before of the
        same topic. The second is left out when it is the same message,
        which is what a stream saying only one thing looks like.

        Args:
            envelope: The message the block is about.
            gap: Seconds since the message printed before, negative
                when there was none.
            topic_gap: Seconds since the message printed before under
                the same topic, negative when there was none.

        Returns:
            The line the block opens on.

        """
        topic = str(envelope.get('topic', ''))
        stamp = envelope.get('ts')

        parts = []

        sequence = envelope.get('seq')
        if isinstance(sequence, int):
            parts.append(self.paint(f'#{ sequence }', ansi.ID, ansi.BOLD))

        parts.extend((
            self.paint(topic, self.plane_codes(topic), ansi.BOLD),
            self.paint(
                format_time(stamp)
                if isinstance(stamp, int | float)
                else '--:--:--.---',
                ansi.TIME,
            ),
        ))

        if gap >= 0:
            parts.append(self.paint(f'+{ format_gap(gap) }', ansi.DELTA))

        if topic_gap >= 0 and topic_gap != gap:
            parts.append(
                self.paint(
                    f'Δ{ topic } { format_gap(topic_gap) }',
                    ansi.TOPIC_DELTA,
                ),
            )

        opening = self.paint(BLOCK_OPEN, ansi.FRAME)

        return f'{ opening } { SEPARATOR.join(parts) }'

    def scalar_text(self, key: str, value: object) -> str:
        """
        Write a value of the payload as it is best read.

        Args:
            key: Name of the field it came under.
            value: The value itself.

        Returns:
            The value, in the unit and the shape its name calls for.

        """
        if value is None:
            return 'null'

        if isinstance(value, bool):
            return 'true' if value else 'false'

        if isinstance(value, int | float):
            return self.number_text(key, value)

        text = str(value)

        if key in FACELETS_FIELDS:
            return format_facelets(text)

        return text

    @staticmethod
    def number_text(key: str, value: float) -> str:
        """
        Write a number in the unit the field it came under counts in.

        Args:
            key: Name of the field it came under.
            value: The number itself.

        Returns:
            The number, converted to what a reader counts in.

        """
        if key in CLOCK_FIELDS:
            return format_time(value)

        if key in DATE_FIELDS:
            return format_date(value)

        if key in MILLISECOND_FIELDS:
            return format_seconds(value / 1_000)

        if key in NANOSECOND_FIELDS:
            return format_seconds(value / 1_000_000_000)

        if isinstance(value, float):
            return format_float(value)

        return str(value)

    def scalar(self, key: str, value: object) -> Painted:
        """
        Write a value, and say what it is painted with.

        The text is handed over bare: escapes are counted as columns by
        anything that counts characters, and a line wrapped on them
        wraps nowhere near where it looks like it should.

        Args:
            key: Name of the field it came under.
            value: The value itself.

        Returns:
            The value as it reads, and the colors it wears.

        """
        return self.scalar_text(key, value), scalar_codes(key, value)

    def listing(self, key: str, values: Sequence[Any]) -> Painted:
        """
        Write a sequence of scalars as the list it is.

        Args:
            key: Name of the field it came under.
            values: The values, as the payload carries them.

        Returns:
            The list as it reads, and the colors it wears.

        """
        pairs = [self.scalar(key, value) for value in values]

        text = ', '.join(text for text, _ in pairs)
        codes = {codes for _, codes in pairs}

        # A list of one kind of thing is worn as that kind of thing,
        # and a mixed one is worn as text: there is no color for two
        return (
            f'[{ text }]',
            codes.pop() if len(codes) == 1 else (ansi.STRING,),
        )

    def inline(self, data: Mapping[str, Any]) -> tuple[str, str]:
        """
        Write a mapping of scalars on one line.

        Args:
            data: The mapping, as the payload carries it.

        Returns:
            The line as it reads, and the line as it is printed.

        """
        bare = []
        painted = []

        for key, value in data.items():
            text, codes = self.scalar(str(key), value)
            bare.append(f'{ key } { text }')
            painted.append(
                f'{ self.paint(str(key), ansi.FIELD) } '
                f'{ self.paint(text, *codes) }',
            )

        return GAP.join(bare), GAP.join(painted)

    def prefix(self, key: str, pad: int, depth: int) -> tuple[str, int]:
        """
        Open the line a field is written on.

        Args:
            key: Name of the field.
            pad: Width the names of its neighbours are aligned on.
            depth: How deep in the payload it sits.

        Returns:
            The opening of the line, and the column its value starts
            at once the escapes are taken out.

        """
        body = self.paint(BLOCK_BODY, ansi.FRAME)
        margin = INDENT * depth
        name = self.paint(key.ljust(pad), ansi.FIELD)

        return (
            f'{ body } { margin }{ name }{ GAP }',
            len(f'{ BLOCK_BODY } { margin }') + pad + len(GAP),
        )

    def wrap(self, text: str, codes: tuple[str, ...], column: int) -> list[str]:
        """
        Lay a value out under the name it belongs to.

        A value too wide for the terminal is broken and its pieces hang
        under the first one, so that a scramble stays one field rather
        than becoming a paragraph the next field is lost in.

        Args:
            text: The value as it reads, which the width is counted on.
            codes: The colors it wears.
            column: Where the value starts on the line.

        Returns:
            The value painted, one entry per line it takes. The first
            one is what the opening of the field is completed with.

        """
        room = max(self.width - column, MINIMUM_WIDTH // 2)

        if len(text) <= room:
            return [self.paint(text, *codes)]

        # Broken bare and painted after: what is cut here is the text,
        # and every piece wears the color whole
        pieces = textwrap.wrap(text, width=room) or [text]

        body = self.paint(BLOCK_BODY, ansi.FRAME)
        hanging = ' ' * (column - len(f'{ BLOCK_BODY } '))

        lines = [self.paint(pieces[0], *codes)]
        lines.extend(
            f'{ body } { hanging }{ self.paint(piece, *codes) }'
            for piece in pieces[1:]
        )

        return lines

    def field(
            self,
            key: str,
            value: object,
            pad: int,
            depth: int,
    ) -> list[str]:
        """
        Write one field of a payload, whatever it carries.

        Args:
            key: Name of the field.
            value: What it carries.
            pad: Width the names of its neighbours are aligned on.
            depth: How deep in the payload it sits.

        Returns:
            The lines the field takes.

        """
        if isinstance(value, Mapping):
            return self.mapping(key, value, pad, depth)

        if isinstance(value, list):
            return self.sequence(key, value, pad, depth)

        opening, column = self.prefix(key, pad, depth)
        text, codes = self.scalar(key, value)
        lines = self.wrap(text, codes, column)

        return [f'{ opening }{ lines[0] }', *lines[1:]]

    def mapping(
            self,
            key: str,
            value: Mapping[str, Any],
            pad: int,
            depth: int,
    ) -> list[str]:
        """
        Write a field that carries a mapping of its own.

        A mapping of scalars short enough is written on the line of its
        own name: a quaternion is one value in four parts, and four
        lines would make it look like four things.

        Args:
            key: Name of the field.
            value: The mapping it carries.
            pad: Width the names of its neighbours are aligned on.
            depth: How deep in the payload it sits.

        Returns:
            The lines the field takes.

        """
        opening, column = self.prefix(key, pad, depth)

        if not value:
            return [f'{ opening }{ self.paint("{}", ansi.NOTHING) }']

        if all(is_scalar(item) for item in value.values()):
            bare, painted = self.inline(value)

            if column + len(bare) <= self.width:
                return [f'{ opening }{ painted }']

        return [opening.rstrip(), *self.fields(value, depth + 1)]

    def sequence(
            self,
            key: str,
            value: Sequence[Any],
            pad: int,
            depth: int,
    ) -> list[str]:
        """
        Write a field that carries a list.

        A list of anything but scalars becomes a sub-block per entry:
        the steps of a solve are things in their own right, and a list
        of them on one line is a line nobody can find a step in.

        Args:
            key: Name of the field.
            value: The list it carries.
            pad: Width the names of its neighbours are aligned on.
            depth: How deep in the payload it sits.

        Returns:
            The lines the field takes.

        """
        opening, column = self.prefix(key, pad, depth)

        if not value:
            return [f'{ opening }{ self.paint("[]", ansi.NOTHING) }']

        if all(is_scalar(item) for item in value):
            lines = self.wrap(*self.listing(key, value), column)

            return [f'{ opening }{ lines[0] }', *lines[1:]]

        body = self.paint(BLOCK_BODY, ansi.FRAME)
        margin = INDENT * (depth + 1)
        lines = [opening.rstrip()]

        for index, item in enumerate(value, start=1):
            entry = self.paint(f'[{ index }]', ansi.FIELD)
            lines.append(f'{ body } { margin }{ entry }')

            if isinstance(item, Mapping):
                lines.extend(self.fields(item, depth + 2))
            else:
                lines.extend(self.field(key, item, pad, depth + 2))

        return lines

    def fields(self, data: Mapping[str, Any], depth: int = 0) -> list[str]:
        """
        Write every field of a payload, names aligned.

        Args:
            data: The payload, or one of the mappings it carries.
            depth: How deep in the payload it sits.

        Returns:
            The lines the payload takes.

        """
        if not data:
            return []

        pad = max(len(str(key)) for key in data)

        lines: list[str] = []

        for key, value in data.items():
            lines.extend(self.field(str(key), value, pad, depth))

        return lines

    def block(
            self,
            envelope: Envelope,
            gap: float,
            topic_gap: float,
    ) -> list[str]:
        """
        Write the whole of one message.

        Args:
            envelope: The message.
            gap: Seconds since the message printed before.
            topic_gap: Seconds since the one before of the same topic.

        Returns:
            The lines the message takes, closing line included.

        """
        self.measure()

        data = envelope.get('data')

        lines = [self.header(envelope, gap, topic_gap)]

        if isinstance(data, Mapping):
            lines.extend(self.fields(data))
        elif data is not None:
            # A payload is always an object, so one that is not says
            # something about the publisher rather than about the cube
            lines.extend(self.fields({'data': data}))

        lines.append(self.paint(BLOCK_CLOSE, ansi.FRAME))

        return lines
