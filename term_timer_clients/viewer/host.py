"""The window of the viewer, named after the cube feeding it."""
from dataclasses import dataclass
from dataclasses import field

from cubing_algs.display.gl.constants import HELP_CLOSE
from cubing_algs.display.gl.constants import HELP_MOUSE
from cubing_algs.display.gl.constants import HELP_WINDOW
from cubing_algs.display.gl.constants import HelpEntry
from cubing_algs.display.gl.constants import help_block
from cubing_algs.display.gl.constants import viewer_entries
from cubing_algs.display.gl.host import GlfwHost

from term_timer_clients.orders import CLOSE_ORDER
from term_timer_clients.orders import HIDE_ORDER
from term_timer_clients.orders import SHOW_ORDER
from term_timer_clients.viewer.assembly import Assembly
from term_timer_clients.viewer.client import CubeCast
from term_timer_clients.viewer.framing import DEMO_VIEW
from term_timer_clients.viewer.framing import USER_VIEW
from term_timer_clients.viewer.framing import Framing

# What the window calls itself at the top of the list it prints.
CAST_NAME = 'cube-cast'

# What the window answers, written when it opens. The lines are asked
# of cubing-algs rather than copied out of it: the gestures and the keys
# belong to the window the library opens, and a list recopied here is a
# list that says what that window answered the day it was written. What
# this client owns of it is the three view keys and the name at the top
# - and `moves=False`, which is what takes the keys turning a cube out
# of the list as it takes them out of the window.
VIEWER_ENTRIES: tuple[HelpEntry, ...] = (
    *viewer_entries(HELP_MOUSE),
    HelpEntry('1', 'Frame the cube the way an algorithm is read'),
    HelpEntry('2', 'Frame the cube the way the hand holding it sees it'),
    HelpEntry('3', 'Pass behind the cube, and come back'),
    *viewer_entries(HELP_WINDOW),
)

VIEWER_SHORTCUTS = help_block(CAST_NAME, VIEWER_ENTRIES)

# The same list for a window somebody else shows, with the keys that
# close a window **taken out rather than reworded**: whether the window
# is on the screen is held by whoever shows it, and a key putting it
# away behind that back would be a second answer to the one question -
# an icon left offering to hide a window that is already gone, with
# nothing on the pipe for the window to say otherwise with. So the
# window answers them by doing nothing, and the list says so by not
# offering them. **The line is found by the keys the library names**
# and never by the words it happened to be written with, so a gesture
# reworded upstream costs nothing here.
MANAGED_SHORTCUTS = help_block(
    CAST_NAME,
    tuple(
        entry
        for entry in VIEWER_ENTRIES
        if entry.keys != HELP_CLOSE
    ),
)


@dataclass
class CubeCastHost(GlfwHost):
    """
    The glfw host of cubing-algs, titled by the stream it listens to.

    ``frame()`` is the seam the host documents for a consumer layering
    something on the cube, and a title written from the stream is what
    this one layers on it, the keyboard moves taken back off: the loop,
    the timing and the frame counter are inherited untouched.

    The title is written here rather than by the reader thread on
    purpose: glfw wants its window handled from the thread that opened
    it, so the stream only ever changes what the title says, and the
    window learns it at the next frame.

    ``transparent`` and ``msaa`` are **inherited**, and so is the mouse
    that goes with them: laying a cube on the desktop is a window
    losing its background, its decoration and its place in the stack,
    the offscreen detour a transparent visual imposes on the
    antialiasing, and the Ctrl drag that carries a window with no bar
    left to grab - none of which knows anything about a cube or a
    stream. What is passed here is the two flags, and what this client
    still owns of it is the *title*, which a window with no bar has
    nowhere to show: it is written all the same, a taskbar and an
    alt-tab reading it.

    ``assembly`` is where the pieces of the cube stand between the
    core and the far end of their rays: a cube nobody is connected to
    is blown out of the window and leaves the ball core alone in it,
    and one that has described itself implodes around it. The core
    is moved by the link instead, and the two are handed over apart -
    a cube announces itself long before it says what it looks like,
    and the ball is what answers the link while the pieces wait for a
    state. The
    effect is layered on the very seam the viewer documents for it, so
    a frame with no cube to show costs a scene with no piece in it.

    ``framing`` is where the camera stands, and the 1, 2 and 3 keys
    are what move it: a rotation string is hard to type and impossible
    to guess, and the two framings anybody ever wants - the cube read
    the way an algorithm is written, and the cube seen the way the
    hand holding it sees it - are one key each, the third passing
    behind whichever of them is being watched.

    ``managed`` is a window opened for **somebody else to show**: it
    opens hidden, takes its orders on its standard input, and the end
    of that pipe is the end of the window. It is what makes a window
    worth keeping rather than reopening - a client that follows the
    stream from the start is a client that has heard the cube describe
    itself, where one opened in the middle of a session has heard
    nothing and shows a core alone until the cube connects again. The
    orders arrive on the reader thread and a window belongs to the
    thread that opened it, so ``order()`` only ever writes down what
    was asked and ``obey()`` does it at the next turn of the loop -
    the very arrangement the title travels by.

    Such a window answers **no key of its own** about being on the
    screen: whoever shows it is the one holding whether it is, and a
    key that hid or closed it behind that back would be a second
    answer to the one question.
    """

    view: CubeCast = field(kw_only=True)

    # Where the camera stands, and what the 1, 2 and 3 keys move it
    # between. The window opens on whatever the viewer was built with,
    # so a host handed no framing at all is one whose keys frame the
    # cube the way cubing-algs frames it.
    framing: Framing = field(default_factory=Framing)

    # The stream is the only thing entitled to turn this cube: a face
    # played from the keyboard - or a `Backspace` putting the cube back
    # together - would drift the window away from the hardware with
    # nothing to bring the two back together. The library refuses them
    # at the door and takes them out of the list it prints; what is
    # written below is that list with the three view keys added.
    moves: bool = False

    # Redeclared rather than passed in: the keys this window adds are
    # added by this class, so the list saying so belongs to it too.
    shortcuts: str = VIEWER_SHORTCUTS

    # Whether this window is opened for another process to show. It is
    # one flag and not three because the three hold together: a window
    # nobody has shown yet has to open hidden, one shown from outside
    # is hidden from outside, and one that is only ever put away is one
    # somebody else closes.
    managed: bool = False

    # What was last asked of the window, and nothing has yet. Written
    # by whoever reads the orders and read by the loop: a string and
    # not a queue, the orders being answers to the same question -
    # whether the window is on the screen - so the last one asked is
    # the only one that means anything.
    wanted: str = field(init=False, default='')

    # Where the window stood the moment it was last hidden, and
    # nothing until then. ``hide()`` withdraws the window rather than
    # merely unmapping it, and a withdrawn window remapped is one most
    # compositors place afresh, exactly as a window just opened is -
    # so what glfw would otherwise forget is kept here, for the next
    # ``show()`` to hand back.
    position: tuple[int, int] | None = field(init=False, default=None)

    # Where the pieces of the cube stand between the core and the far
    # end of their rays. It starts blown apart: a window opens on a
    # stream that has said nothing yet, and a cube nobody has described
    # is a cube that is not there.
    assembly: Assembly = field(init=False, default_factory=Assembly)

    def __post_init__(self) -> None:
        """
        Settle what a window driven from outside opens as.

        A window shown by another process opens hidden - there is
        nothing else it could open as, the process that shows it not
        having asked yet - and the keys that close a window put it away
        instead. The list it prints says so: what a window answers and
        what it offers are one decision, and they were two copies of it
        for as long as the list was written out by hand.
        """
        if not self.managed:
            return

        self.visible = False
        self.shortcuts = MANAGED_SHORTCUTS

        # A managed window shows itself on its own cadence - the tray
        # following a link rather than a click - so its ``show()`` must
        # not drag the keyboard away from whatever the desk was doing:
        # a cube appearing to say a link came up is not a cube asking
        # to be typed into.
        self.focus_on_show = False

    def order(self, order: str) -> None:
        """
        Write down what was just asked of the window.

        Called from the thread reading the orders, which is why it
        writes and does nothing: glfw wants its window handled from
        the thread that opened it.

        Args:
            order: What is asked of the window.

        """
        self.wanted = order

    def obey(self) -> None:
        """
        Do what was asked of the window, on the thread that owns it.

        An order nobody here knows is ignored rather than guessed at,
        which is what this client does with a topic it does not know.
        """
        wanted, self.wanted = self.wanted, ''

        if wanted == SHOW_ORDER:
            self.show()
            self.restore_position()
        elif wanted == HIDE_ORDER:
            self.remember_position()
            self.hide()
        elif wanted == CLOSE_ORDER:
            # The one order that truly ends the window, and it reaches
            # the host rather than `on_close()`: what the keys do here
            # is put the window away, and this is the process that
            # opened it saying there is no more window to put away.
            super().on_close()

    def remember_position(self) -> None:
        """
        Read where the window stands, before it is taken off the screen.

        Called ahead of ``hide()`` rather than after: a withdrawn
        window can no longer be trusted to report where it stood.
        """
        import glfw  # ruff: ignore[import-outside-top-level]

        if self.window is not None:
            self.position = glfw.get_window_pos(self.window)

    def restore_position(self) -> None:
        """
        Put the window back where it stood before it was last hidden.

        Nothing to do the first time a window is shown: it has never
        been hidden by this client, and the compositor's own placement
        is the only one there is yet.
        """
        import glfw  # ruff: ignore[import-outside-top-level]

        if self.window is not None and self.position is not None:
            glfw.set_window_pos(self.window, *self.position)

    def tick(self) -> None:
        """Play one frame, whatever was asked of the window first."""
        self.obey()

        super().tick()

    def idle(self) -> None:
        """Play one turn of a hidden window, orders read first."""
        self.obey()

        super().idle()

    def on_close(self) -> None:
        """
        Answer the keys asking for the window to go, or refuse them.

        A window shown by another process is **not the one deciding**
        whether it is on the screen: that process holds the answer, and
        it is the answer an icon writes in its menu. A key hiding the
        window behind its back would leave it offering to hide what is
        already gone, and a key closing it would take away the very
        thing it was kept open for - a client that has followed the
        stream from the start. So they are answered by doing nothing,
        and the list this window prints does not offer them.

        Closing it is that process saying so: the ``close`` order, or
        the end of the pipe the orders arrive on.
        """
        if self.managed:
            return

        super().on_close()

    def frame(self, delta: float) -> None:
        """
        Draw one frame, the title of the window brought up to date.

        Args:
            delta: Seconds gone by since the last frame.

        """
        # What the cube says about itself, pushed on every frame: the
        # stream only ever moves the string, a window belonging to the
        # thread that opened it, and the host writes nothing when it
        # has not changed. In debug mode the counter appends its
        # numbers to whatever it names, so the two never fight.
        self.set_title(self.view.title)

        self.draw_cube(delta)

    def draw_cube(self, delta: float) -> None:
        """
        Draw the cube, its pieces where the state has them stand.

        The frame of the parent is taken apart rather than called: the
        viewer documents ``advance()`` and ``draw()`` as the seam an
        effect slips between, and describing the picture to ``draw()``
        is what keeps the effect out of the viewer itself - nothing is
        written and put back, so nothing can leak into the camera the
        mouse writes to, nor compound from one frame to the next.

        Args:
            delta: Seconds gone by since the last frame.

        """
        drawn = self.assembly.advance(
            self.viewer.advance(delta),
            present=self.view.present,
            linked=self.view.connected,
            delta=delta,
        )

        # Read after the time has passed, and on its own line: the core
        # is painted for the very moment the pieces were just placed in.
        look = self.assembly.tint(self.viewer.look)

        self.viewer.draw(scene=drawn, look=look)

    def reframe(self) -> None:
        """
        Build the camera again, where the framing now has it stand.

        The view is written into the viewer rather than into the
        camera: ``rotation`` is what ``reset_camera()`` reads, so
        Space comes back to the view being watched rather than to the
        one the window happened to open on.
        """
        self.viewer.rotation = self.framing.rotation
        self.viewer.reset_camera()

    def on_viewer_key(self, key: int) -> bool:
        """
        Answer the three keys this window adds to the ones it inherits.

        The framing is what they move, and they are answered here
        rather than in the viewer because cubing-algs has no notion of
        a view to stand in: it knows the rotation string a camera is
        built from, and which of them is worth a key is a matter for
        the window showing the cube.

        Everything else is the window of the library: the keys turning
        a cube are refused by ``moves``, and what only looks at it -
        the opening, the axes, the screenshot - is answered upstream.

        Args:
            key: The glfw code of the key.

        Returns:
            True when the key was one of them, or one the host answers.

        """
        import glfw  # ruff: ignore[import-outside-top-level]

        views = {glfw.KEY_1: DEMO_VIEW, glfw.KEY_2: USER_VIEW}

        if key in views:
            self.framing.show(views[key])
            self.reframe()
        elif key == glfw.KEY_3:
            self.framing.flip()
            self.reframe()
        else:
            return super().on_viewer_key(key)

        return True
