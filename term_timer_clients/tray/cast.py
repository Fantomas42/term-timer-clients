"""The window behind the icon, and the process it really is."""
import logging
import shutil
import signal
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from collections.abc import Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

# The client this one shows, and the options it is opened with. A cube
# laid on the desktop is what a popup is: no decoration to take room, no
# background under it, and floating above whatever it is glanced at
# over. It is one flag because cubing-algs makes it one.
CAST_PROGRAM = 'cube-cast'

TRANSPARENT_FLAG = '--transparent'

ENDPOINT_FLAG = '--endpoint'

WINDOW_SIZE_FLAG = '--window-size'

# How small the cube is glanced at. A popup is looked at over whatever
# it was opened above, and a window big enough to work in is one that
# covers it: the working window is `cube-cast` itself, one command away.
DEFAULT_POPUP_SIZE = (280, 280)

SIZE_SEPARATOR = 'x'

# How long a window is given to close itself before it is taken down.
# It is asked the way a terminal asks, and it answers the way it
# answers a Ctrl-C: a window that hangs on its driver is still a window
# the next click has to be able to reopen.
CLOSING_TIMEOUT = 2.0


def cast_program() -> str:
    """
    Tell what runs the window, wherever this client was installed from.

    The client next to the interpreter running this one wins over the
    one on the path: a tray installed in a virtualenv opens the window
    of that virtualenv, where the path may well name another one - or
    an older one, which is worse than none.

    Returns:
        The program to run, its plain name when nothing else is found.

    """
    beside = Path(sys.executable).parent / CAST_PROGRAM

    if beside.exists():
        return str(beside)

    return shutil.which(CAST_PROGRAM) or CAST_PROGRAM


def cast_command(
        endpoint: str,
        size: tuple[int, int],
        extra: Sequence[str] = (),
        program: str = '',
) -> list[str]:
    """
    Write out the command line the popup is opened with.

    What was typed after ``--`` is appended last, and appended whole:
    it is the command line of ``cube-cast`` itself, so a palette, a
    view or a beat is argued with where it is documented rather than
    through an option copied here that would drift from it. Coming last
    is what lets it argue with the size, and with the transparency too.

    Args:
        endpoint: The stream the window listens to.
        size: Width and height of the popup, in pixels.
        extra: What was typed for the window itself.
        program: What runs the window, found on its own when empty.

    Returns:
        The command, ready to be run.

    """
    width, height = size

    return [
        program or cast_program(),
        ENDPOINT_FLAG, endpoint,
        TRANSPARENT_FLAG,
        WINDOW_SIZE_FLAG, f'{ width }{ SIZE_SEPARATOR }{ height }',
        *extra,
    ]


class Popup:
    """
    The window the icon opens, held as the process it is.

    Two processes rather than one, and the reason is that they are two
    loops: glfw wants the thread that opened its window, and the bus
    wants one of its own. A window opened aside is a window this client
    never has to host, and what the two share is the stream they both
    subscribe to - which is exactly what a publisher binding for
    everybody is for.

    The window is its own to close: ``Q``, ``Escape`` and the reason a
    process has to go away are answered by ``cube-cast`` alone, and
    ``settle()`` is how the icon hears about it.
    """

    def __init__(self, command: Sequence[str]) -> None:
        """
        Prepare a popup, opening nothing yet.

        Args:
            command: What is run to open the window.

        """
        self.command = list(command)
        self.process: subprocess.Popen[bytes] | None = None

    @property
    def shown(self) -> bool:
        """
        Tell whether the window is open.

        Returns:
            True while a window is up.

        """
        return self.process is not None

    def show(self) -> None:
        """
        Open the window, unless one is already up.

        A window that cannot be opened is reported and nothing else:
        the icon is what is left, and it is still the one thing saying
        whether a cube is there.
        """
        if self.process is not None:
            return

        try:
            self.process = subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]
                self.command,
            )
        except OSError as error:
            logger.error(  # ruff: ignore[error-instead-of-exception]
                'Cannot open the window: %s', error,
            )

    def hide(self) -> None:
        """
        Close the window, and wait for it to be gone.

        It is asked the way a terminal asks - the very signal a Ctrl-C
        sends - so the window closes through the same path it closes by
        hand, its stream stopped and its socket given back. Only a
        window that will not go is taken down.
        """
        process, self.process = self.process, None

        if process is None:
            return

        process.send_signal(signal.SIGINT)

        try:
            process.wait(timeout=CLOSING_TIMEOUT)
        except subprocess.TimeoutExpired:
            logger.warning('The window did not close, taking it down')
            process.kill()
            process.wait()

    def toggle(self) -> None:
        """Open the window, or close the one that is up."""
        if self.shown:
            self.hide()
        else:
            self.show()

    def settle(self) -> bool:
        """
        Notice a window that was closed from the window itself.

        A popup is closed by clicking the icon again, but it is also a
        window: ``Q`` closes it, and so does anything that takes a
        process away. The icon has to hear about it, or the next click
        would try to close a window that is already gone.

        Returns:
            True when the window went away on its own.

        """
        process = self.process

        if process is None or process.poll() is None:
            return False

        self.process = None

        return True

    def close(self) -> None:
        """Take the window down, the tray going away with it."""
        self.hide()
