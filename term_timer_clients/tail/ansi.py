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
# said here is worn.
FRAME: Final = '\x1b[38;5;240m'

TIME: Final = '\x1b[38;5;245m'

CUBE_PLANE: Final = '\x1b[38;5;44m'

SESSION_PLANE: Final = '\x1b[38;5;176m'

FIELD: Final = '\x1b[38;5;110m'

NUMBER: Final = '\x1b[38;5;180m'

STRING: Final = '\x1b[38;5;252m'

TRUE: Final = '\x1b[38;5;78m'

FALSE: Final = '\x1b[38;5;174m'

NOTHING: Final = '\x1b[38;5;240m'

BREAK: Final = '\x1b[38;5;179m'

ALERT: Final = '\x1b[38;5;203m'

# What the eye looks for in a stream that scrolls: the state a session
# is in, and the move a cube reports
HIGHLIGHT: Final = '\x1b[38;5;255m'

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
