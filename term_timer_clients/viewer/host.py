"""The window of the viewer, named after the cube feeding it."""
from dataclasses import dataclass
from dataclasses import field

from cubing_algs.display.gl.host import GlfwHost

from term_timer_clients.viewer.client import CubeView

# What the window answers, written when it opens. The list cubing-algs
# ships names the keys turning the cube, and a cube turned elsewhere
# has none of them: what is left is what only looks at it.
VIEWER_SHORTCUTS = """\
cube-view
  Drag             Orbit the cube
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


@dataclass
class CubeViewHost(GlfwHost):
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
    """

    view: CubeView = field(kw_only=True)

    # Redeclared rather than passed in: the keys held back are held back
    # by this class, so the list saying so belongs to it too.
    shortcuts: str = VIEWER_SHORTCUTS

    def frame(self, delta: float) -> None:
        """
        Draw one frame, the title of the window brought up to date.

        Args:
            delta: Seconds gone by since the last frame.

        """
        self.retitle()

        super().frame(delta)

    def retitle(self) -> None:
        """
        Write what the cube says about itself in the title bar.

        In debug mode the host writes its measurements there several
        times a second, on top of this very title: what is set here is
        the base they are appended to, so the two never fight.
        """
        title = self.view.title

        if title == self.title:
            return

        self.title = title

        if self.window is None:
            return

        import glfw  # noqa: PLC0415

        glfw.set_window_title(self.window, title)

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
        exploded view, the axes and the screenshot.

        Args:
            key: The glfw code of the key.

        Returns:
            Always True: what the window answers itself is settled
            before this, and what is left is a move nobody plays.

        """
        import glfw  # noqa: PLC0415

        if key != glfw.KEY_BACKSPACE:
            super().on_viewer_key(key)

        return True
