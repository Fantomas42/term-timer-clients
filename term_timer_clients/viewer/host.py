"""The window of the viewer, named after the cube feeding it."""
from dataclasses import dataclass
from dataclasses import field

from cubing_algs.display.gl.constants import HELP_MOUSE
from cubing_algs.display.gl.constants import HELP_WINDOW
from cubing_algs.display.gl.constants import HelpEntry
from cubing_algs.display.gl.constants import help_block
from cubing_algs.display.gl.constants import viewer_entries
from cubing_algs.display.gl.host import GlfwHost

from term_timer_clients.viewer.assembly import Assembly
from term_timer_clients.viewer.client import CubeCast
from term_timer_clients.viewer.framing import DEMO_VIEW
from term_timer_clients.viewer.framing import USER_VIEW
from term_timer_clients.viewer.framing import Framing

# What the window answers, written when it opens. The lines are asked
# of cubing-algs rather than copied out of it: the gestures and the keys
# belong to the window the library opens, and a list recopied here is a
# list that says what that window answered the day it was written. What
# this client owns of it is the three view keys and the name at the top
# - and `moves=False`, which is what takes the keys turning a cube out
# of the list as it takes them out of the window.
VIEWER_SHORTCUTS = help_block(
    'cube-cast',
    (
        *viewer_entries(HELP_MOUSE),
        HelpEntry('1', 'Frame the cube the way an algorithm is read'),
        HelpEntry('2', 'Frame the cube the way the hand holding it sees it'),
        HelpEntry('3', 'Pass behind the cube, and come back'),
        *viewer_entries(HELP_WINDOW),
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
        import glfw  # noqa: PLC0415

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
