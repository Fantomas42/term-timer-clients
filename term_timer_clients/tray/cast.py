"""The window behind the icon, and the process it really is."""
import logging
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

from term_timer_clients.argparser import write_size
from term_timer_clients.orders import HIDE_ORDER
from term_timer_clients.orders import SHOW_ORDER
from term_timer_clients.orders import write_order

logger = logging.getLogger(__name__)

# The client this one shows, and the options it is opened with. A cube
# laid on the desktop is what a popup is: no decoration to take room, no
# background under it, and floating above whatever it is glanced at
# over. It is one flag because cubing-algs makes it one.
CAST_PROGRAM = 'cube-cast'

TRANSPARENT_FLAG = '--transparent'

# What makes the window one this icon shows rather than one it opens:
# it comes up hidden and takes its orders on the pipe, which is the
# whole of why there is a window there at all before anybody asked for
# one. **A cube announces its departure and never its arrival**, and it
# describes itself once, when it connects: a window opened at the click
# has heard neither, and shows a core alone until the cube connects
# again - which, in the middle of a session, is never.
MANAGED_FLAG = '--managed'

ENDPOINT_FLAG = '--endpoint'

# How big the cube is glanced at is `DEFAULT_WINDOW_SIZE` and nothing
# of this client's own: the window it opens is `cube-cast`, and a popup
# sized here would be the same client showing the same cube at two
# sizes depending on which one opened it.
WINDOW_SIZE_FLAG = '--window-size'

# How long a window is given to close itself before it is taken down.
# It is asked by the end of its pipe, which is the last of the three
# orders it answers: a window that hangs on its driver is still a
# window the next click has to be able to reopen.
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
    return [
        program or cast_program(),
        ENDPOINT_FLAG, endpoint,
        TRANSPARENT_FLAG,
        MANAGED_FLAG,
        WINDOW_SIZE_FLAG, write_size(size),
        *extra,
    ]


class Popup:
    """
    The window the icon shows, held as the process it is.

    Two processes rather than one, and the reason is that they are two
    loops: glfw wants the thread that opened its window, and the bus
    wants one of its own. A window opened aside is a window this client
    never has to host, and what the two share is the stream they both
    subscribe to - which is exactly what a publisher binding for
    everybody is for.

    **It is opened once and shown many times**, and that is not an
    optimisation. A ``cube-cast`` started at the click has heard
    nothing of what came before: a cube announces its departure and
    never its arrival, and it describes itself when it connects, so a
    window opened in the middle of a session shows the ball core alone
    until the cube connects again. One opened with the icon has heard
    all of it, and showing it costs a line on a pipe rather than a
    process, a context and a first frame.

    The pipe is the whole of the coupling: three words go down it, and
    its end is the third. So a tray taken away by anything at all -
    including what leaves it no chance to close anything - closes the
    window it opened, where a window with a life of its own would be
    left on the desktop with nothing to reach it.
    """

    def __init__(self, command: Sequence[str]) -> None:
        """
        Prepare a popup, opening nothing yet.

        Args:
            command: What is run to open the window.

        """
        self.command = list(command)
        self.process: subprocess.Popen[str] | None = None
        self.shown = False

    @property
    def running(self) -> bool:
        """
        Tell whether there is a window behind the icon at all.

        Returns:
            True while the process is up, shown or not.

        """
        process = self.process

        return process is not None and process.poll() is None

    def launch(self) -> None:
        """
        Open the window, hidden, and leave it following the stream.

        Called with the icon rather than at the first click: what a
        window is worth showing depends on what it has heard, and it
        can only have heard what it was there for. A window that
        cannot be opened is reported and nothing else - the icon is
        what is left, and it is still the one thing saying whether a
        cube is there.
        """
        if self.running:
            return

        try:
            self.process = subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]
                self.command,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as error:
            logger.error(  # ruff: ignore[error-instead-of-exception]
                'Cannot open the window: %s', error,
            )
            self.process = None

    def order(self, order: str) -> bool:
        """
        Ask the window for one thing, if there is one to ask.

        Args:
            order: What is asked of it.

        Returns:
            True when the order was handed over.

        """
        process = self.process

        if process is None or process.stdin is None:
            return False

        return write_order(process.stdin, order)

    def show(self) -> None:
        """
        Put the window on the screen, opening one if there is none.

        A window is opened again where the one that was following the
        stream is gone - it crashed, or somebody took it away - and
        what comes up is then a window that has heard nothing. It is
        the honest answer to a click all the same: the alternative is
        an icon that stops showing anything at all.
        """
        self.launch()

        self.shown = self.order(SHOW_ORDER)

    def hide(self) -> None:
        """
        Take the window off the screen, and leave it following.

        Nothing is closed and nothing is given back: the window goes on
        reading the stream behind the icon, which is the whole of what
        the next click is quick and right about.
        """
        self.order(HIDE_ORDER)

        self.shown = False

    def toggle(self) -> None:
        """Show the window, or take away the one that is up."""
        if self.shown:
            self.hide()
        else:
            self.show()

    def settle(self) -> bool:
        """
        Notice a window whose process went away.

        A window is put away rather than closed by its own keys, so
        this is a window that crashed or that somebody took away. The
        icon has to hear about it: the next click has a window to open
        again, and there is nothing left following the stream in the
        meantime.

        Returns:
            True when the window went away on its own.

        """
        process = self.process

        if process is None or process.poll() is None:
            return False

        self.process = None
        self.shown = False

        return True

    def close(self) -> None:
        """
        Take the window down, the tray going away with it.

        The end of the pipe is what asks: it is the last of the three
        orders the window answers, and the only one that cannot be
        missed - a process taken away without a word closes its pipe
        all the same. Only a window that will not go is taken down.
        """
        process, self.process = self.process, None
        self.shown = False

        if process is None:
            return

        if process.stdin is not None:
            with suppress(OSError, ValueError):
                process.stdin.close()

        try:
            process.wait(timeout=CLOSING_TIMEOUT)
        except subprocess.TimeoutExpired:
            logger.warning('The window did not close, taking it down')
            process.kill()
            process.wait()
