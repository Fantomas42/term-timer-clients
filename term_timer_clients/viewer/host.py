"""The window of the viewer, named after the cube feeding it."""
from dataclasses import dataclass
from dataclasses import field

from cubing_algs.display.gl.host import GlfwHost

from term_timer_clients.viewer.assembly import Assembly
from term_timer_clients.viewer.client import CubeCast
from term_timer_clients.viewer.framing import DEMO_VIEW
from term_timer_clients.viewer.framing import USER_VIEW
from term_timer_clients.viewer.framing import Framing

# What is answered whatever the window is, the two mouse lines
# included: the gestures themselves belong to cubing-algs, and what is
# written here is only the half of its list this client leaves standing.
# `ShortcutsTestCase` is what keeps the two from drifting apart.
WINDOW_SHORTCUTS = """\
  Wheel            Zoom in and out
  Space            Frame the cube again
  Tab              Open the cube up, and put it back together
  F2               Show the X/Y/Z axes, red green blue
  F3               Monitor the rendering performance
  F4               Print a performance report
  F5               Turn the vsync on and off
  F12              Write a screenshot
  Esc, Q           Close the window\
"""

# What the window answers, written when it opens. The list cubing-algs
# ships names the keys turning the cube, and a cube turned elsewhere
# has none of them: what is left is what only looks at it.
VIEWER_SHORTCUTS = f"""\
cube-cast
  Drag             Orbit the cube
  Ctrl Drag        Carry the window across the screen
  1                Frame the cube the way an algorithm is read
  2                Frame the cube the way the hand holding it sees it
  3                Pass behind the cube, and come back
{ WINDOW_SHORTCUTS }"""


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
    """

    view: CubeCast = field(kw_only=True)

    # Where the camera stands, and what the 1, 2 and 3 keys move it
    # between. The window opens on whatever the viewer was built with,
    # so a host handed no framing at all is one whose keys frame the
    # cube the way cubing-algs frames it.
    framing: Framing = field(default_factory=Framing)

    # Redeclared rather than passed in: the keys held back are held back
    # by this class, so the list saying so belongs to it too.
    shortcuts: str = VIEWER_SHORTCUTS

    # Where the pieces of the cube stand between the core and the far
    # end of their rays. It starts blown apart: a window opens on a
    # stream that has said nothing yet, and a cube nobody has described
    # is a cube that is not there.
    assembly: Assembly = field(init=False, default_factory=Assembly)

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
        Answer a key the viewer holds the state of, and swallow the rest.

        The cube drawn here is the one being turned somewhere else, and
        the stream is the only thing entitled to move it: a face turned
        from the keyboard would take the window away from the hardware
        with nothing ever bringing the two back together. So every key
        the host leaves unanswered is claimed here, which is what keeps
        ``on_key()`` from reading it as a move, and backspace goes with
        them - a cube put back together is a state the stream never
        published either, and the drift it opens is the same one.

        What is left is what only looks at the cube: the framing, the
        exploded view, the axes and the screenshot. The three view
        keys are of that kind and are answered here rather than in the
        viewer, cubing-algs having no notion of a view to stand in.

        Args:
            key: The glfw code of the key.

        Returns:
            Always True: what the window answers itself is settled
            before this, and what is left is a move nobody plays.

        """
        import glfw  # noqa: PLC0415

        views = {glfw.KEY_1: DEMO_VIEW, glfw.KEY_2: USER_VIEW}

        if key in views:
            self.framing.show(views[key])
            self.reframe()
        elif key == glfw.KEY_3:
            self.framing.flip()
            self.reframe()
        elif key != glfw.KEY_BACKSPACE:
            super().on_viewer_key(key)

        return True
