"""The colors of the stream, and what decides they are worn."""
import os
from typing import IO
from typing import Final

# The escapes are written here and nowhere else: a rendering that
# builds its own would be a rendering the tests cannot read, and every
# assertion of the suite is made against unpainted text.
RESET: Final = '\x1b[0m'

BOLD: Final = '\x1b[1m'

# 256 colors rather than the sixteen basic ones: the palette a terminal
# is themed with owns those, and a blue that a theme turned into its
# own blue would say a field name where a value is meant. Only what is
# said here is worn. Chosen for a debugging tool rather than for a
# prose reading: every one of them has to survive being glanced at in
# a stream that scrolls, which a muted tone does not.
FRAME: Final = '\x1b[38;5;244m'

ID: Final = '\x1b[38;5;118m'

TIME: Final = '\x1b[38;5;39m'

# The two gaps of the header are a cadence, not an instant, and read
# as one only when they are not mistaken for the date next to them.
# They are told apart from one another too: the second only ever
# shows up next to the first, and the same color on both would read
# as one gap said twice instead of two different measures
DELTA: Final = '\x1b[38;5;84m'

TOPIC_DELTA: Final = '\x1b[38;5;178m'

CUBE_PLANE: Final = '\x1b[38;5;51m'

SESSION_PLANE: Final = '\x1b[38;5;201m'

FIELD: Final = '\x1b[38;5;111m'

# What tells one cube from another, worn like a move: a value looked
# for on its own rather than read as a number among the others
SERIAL: Final = '\x1b[38;5;135m'

NUMBER: Final = '\x1b[38;5;214m'

STRING: Final = '\x1b[38;5;255m'

TRUE: Final = '\x1b[38;5;46m'

FALSE: Final = '\x1b[38;5;196m'

NOTHING: Final = '\x1b[38;5;240m'

BREAK: Final = '\x1b[38;5;208m'

ALERT: Final = '\x1b[38;5;198m'

# What the eye looks for in a stream that scrolls: the state a session
# is in, and the move a cube reports
HIGHLIGHT: Final = '\x1b[38;5;226m'

# The variable every tool that paints reads, whatever it paints with
COLOR_VARIABLE: Final = 'NO_COLOR'


class Paint:
    """
    What wears a color, and whether anything does at all.

    A disabled instance hands its text back untouched rather than
    returning a color nobody sees: the rendering asks for colors the
    same way in both cases, and nothing above knows which one it holds.
    """

    def __init__(self, *, enabled: bool = True) -> None:
        """
        Prepare a painter, wearing colors or not.

        Args:
            enabled: Whether the colors are worn.

        """
        self.enabled = enabled

    def __call__(self, text: str, *codes: str) -> str:
        """
        Wear the codes over a piece of text.

        Args:
            text: What is painted.
            codes: The escapes it is painted with.

        Returns:
            The text, painted or as it came.

        """
        if not self.enabled or not codes or not text:
            return text

        return f'{ "".join(codes) }{ text }{ RESET }'


def build_paint(stream: IO[str], *, colorless: bool) -> Paint:
    """
    Decide whether this run of the client wears colors.

    Three things say no, and any one of them is enough: the command
    line, the ``NO_COLOR`` of the environment, and an output that is
    not a terminal. The last one is what makes a piped client readable
    at all - escapes in a file are what a reader has to strip before
    reading anything.

    Args:
        stream: Where the client writes.
        colorless: Whether the command line refused the colors.

    Returns:
        The painter the rendering is given.

    """
    if colorless or os.environ.get(COLOR_VARIABLE):
        return Paint(enabled=False)

    # A stream may answer nothing at all about itself, and what cannot
    # say it is a terminal is taken for a file
    return Paint(enabled=bool(getattr(stream, 'isatty', bool)()))
