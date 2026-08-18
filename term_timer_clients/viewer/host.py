"""The window of the viewer, named after the cube feeding it."""
import logging
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace

from cubing_algs.display.gl import Stage
from cubing_algs.display.gl.context import GLFWWindow
from cubing_algs.display.gl.context import has_glfw
from cubing_algs.display.gl.host import GlfwHost
from cubing_algs.display.gl.renderer import OffscreenTarget

from term_timer_clients.viewer.client import CubeCast

logger = logging.getLogger(__name__)

# The keys are the same whatever the window is, and so is the mouse:
# a plain drag orbits the cube in either of them. A window without
# decoration has no bar left to carry it by, and what replaces the bar
# is added to the drag rather than put in its place - a mode moving the
# one gesture the viewer is made of would cost more than the bar does.
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
cubecast
  Drag             Orbit the cube
  Ctrl drag        Carry the window across the screen
{ WINDOW_SHORTCUTS }"""

# The background of a window whose compositor is asked to let the
# desktop through, against the opaque grey the viewer clears with.
TRANSPARENT = (0.0, 0.0, 0.0, 0.0)

TRANSPARENCY_REFUSED = (
    'The compositor refused a transparent window: '
    'the cube is drawn on the background of the viewer'
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

    ``transparent`` turns the window into a cube laid on the desktop:
    no background, no decoration, and floating above everything. It is
    a mode rather than three options because the three hold together -
    a transparent window keeping its bar would show the desktop through
    a frame, and one dropping behind another would be lost. What it
    costs is the title: a window without a bar has nowhere to write the
    hardware and the battery any more.

    The mouse is the same in either mode: a drag orbits the cube, and
    Ctrl held down over it carries the window instead - a gesture a
    decorated window answers too, where it merely doubles its bar.

    ``msaa`` is what the cube is antialiased by, and turning it off is
    a way out of the offscreen detour a transparent window imposes:
    the cube is then drawn into the window itself, aliased but with
    nothing in between.
    """

    view: CubeCast = field(kw_only=True)
    transparent: bool = False
    msaa: bool = True

    # Redeclared rather than passed in: the keys held back are held back
    # by this class, so the list saying so belongs to it too.
    shortcuts: str = VIEWER_SHORTCUTS

    # Where the cube is drawn when the window itself cannot hold the
    # samples: it belongs to the transparent mode alone, and stays
    # None without it.
    target: OffscreenTarget | None = field(init=False, default=None)

    # What the window is carried by. A window is free to place itself
    # on every platform cubing-algs opens one on: a Wayland session is
    # given the X11 variant of glfw, moderngl having no way to read a
    # context off the other one, and a platform that stayed Wayland is
    # refused a window long before the mouse is of any interest.
    carrying: bool = field(init=False, default=False)
    anchor: tuple[float, float] = field(init=False, default=(0.0, 0.0))

    @property
    def offscreen(self) -> bool:
        """
        Tell whether the cube is drawn aside and copied to the window.

        Returns:
            True when the frame goes through a multisampled target,
            which a transparent visual leaves as the only way to
            antialias the cube.

        """
        return self.transparent and self.msaa

    def open(self) -> Stage:
        """
        Open the window, transparent when it was asked to be.

        The three hints a transparent window needs are posted before
        ``create_window()`` runs rather than passed to it, which is what
        keeps the whole of ``open()`` inherited: hints are a global glfw
        state read when a window is created, and ``create_window()``
        adds its own to whatever is already there instead of clearing
        them first.

        Returns:
            The stage the viewer now draws into.

        """
        # Let the parent raise: it is the one naming the extra a missing
        # glfw asks for, and an ``import glfw`` here would replace that
        # with a bare ModuleNotFoundError.
        if not self.transparent or not has_glfw():
            return self.open_window()

        import glfw  # noqa: PLC0415

        # Hints are settable once glfw is up, and starting it twice
        # costs nothing: the parent starts it again a few lines below.
        glfw.init()
        glfw.window_hint(glfw.TRANSPARENT_FRAMEBUFFER, glfw.TRUE)
        glfw.window_hint(glfw.DECORATED, glfw.FALSE)
        glfw.window_hint(glfw.FLOATING, glfw.TRUE)

        stage = self.open_window()

        # A compositor is free to refuse, and the stage keeps the grey
        # of the viewer when it does: a background cleared to nothing on
        # an opaque window shows whatever the driver left there.
        granted = glfw.get_window_attrib(
            self.window, glfw.TRANSPARENT_FRAMEBUFFER,
        )

        if granted:
            stage.background = TRANSPARENT
        else:
            logger.warning(TRANSPARENCY_REFUSED)

        return stage

    def open_window(self) -> Stage:
        """
        Open the window of the parent, asking for the samples it holds.

        The samples of the window are read off the look of the viewer,
        and the window is asked for none of them for either of two
        reasons: a multisampled window gets the transparency refused on
        this driver - the two are exclusive, and the cube is
        antialiased in the offscreen target instead - and ``msaa`` off
        asks for no antialiasing at all. The look is put back the
        moment the window is open, the offscreen target, F12 and F4
        reading their samples from it as well.

        Returns:
            The stage the viewer now draws into.

        """
        if not self.transparent and self.msaa:
            return super().open()

        look = self.viewer.look
        self.viewer.look = replace(look, samples=0)

        try:
            return super().open()
        finally:
            self.viewer.look = look

    def close(self) -> None:
        """
        Give the offscreen target back, and then the window.

        The target is released while the context is still alive, which
        is what the parent takes away.
        """
        if self.target is not None:
            self.target.release()
            self.target = None

        super().close()

    def refresh_target(self) -> None:
        """
        Keep the offscreen target the size of the window it lands in.

        The whole detour, in one field: the stage draws into a
        multisampled target instead of the window, and ``resolve()``
        brings it back, alpha and all. A window that can hold its own
        samples - or is asked for no antialiasing at all - needs none
        of it.
        """
        if not self.offscreen:
            return

        stage = self.viewer.require_stage()

        if self.target is not None and self.target.size == stage.size:
            return

        if self.target is not None:
            self.target.release()

        self.target = OffscreenTarget.create(
            stage.context, stage.size, self.viewer.look.samples,
        )
        stage.target = self.target.framebuffer

    def resolve(self) -> None:
        """
        Copy the offscreen frame to the window, samples resolved first.

        Nothing to do when the cube was drawn into the window itself:
        no target was ever built, and the frame is already where it
        belongs.
        """
        target = self.target

        if target is None:
            return

        context = self.viewer.require_stage().context

        context.copy_framebuffer(target.resolved, target.framebuffer)
        context.copy_framebuffer(context.screen, target.resolved)

    def frame(self, delta: float) -> None:
        """
        Draw one frame, the title of the window brought up to date.

        Args:
            delta: Seconds gone by since the last frame.

        """
        self.retitle()
        self.refresh_target()

        super().frame(delta)

        self.resolve()

    def retitle(self) -> None:
        """
        Write what the cube says about itself in the title bar.

        In debug mode the host writes its measurements there several
        times a second, on top of this very title: what is set here is
        the base they are appended to, so the two never fight.

        A transparent window has no bar to read it in, and the title is
        written all the same: it is what a taskbar and an alt-tab show,
        and it costs a call nobody sees.
        """
        title = self.view.title

        if title == self.title:
            return

        self.title = title

        if self.window is None:
            return

        import glfw  # noqa: PLC0415

        glfw.set_window_title(self.window, title)

    def carry(self, x: float, y: float) -> None:
        """
        Move the window by what the cursor gained on its anchor.

        The cursor is reported inside the window, so moving the window
        by that gain puts the cursor back on its anchor: the offset is
        measured afresh at every event, and nothing drifts. Counting
        the distance from the previous position instead would move the
        window twice.

        Args:
            x: Where the cursor stands, in pixels from the left.
            y: Where the cursor stands, in pixels from the top.

        """
        import glfw  # noqa: PLC0415

        anchor_x, anchor_y = self.anchor
        window_x, window_y = glfw.get_window_pos(self.window)

        glfw.set_window_pos(
            self.window,
            int(window_x + x - anchor_x),
            int(window_y + y - anchor_y),
        )

    def on_mouse_button(
            self,
            window: GLFWWindow,
            button: int,
            action: int,
            mods: int,
    ) -> None:
        """
        Take hold of the window, or of the cube, until the button goes.

        Which button orbits is what a mode may not change: the drag is
        the one gesture the viewer is made of, and a window looking
        different is no reason to go and find it elsewhere. So the
        carry a window with no bar needs is Ctrl held down at the
        moment of the press, and a decorated window answers it too,
        where it merely doubles the bar it still has.

        Ctrl let go halfway through carries the window all the same:
        glfw says nothing of a modifier changing, and the carry belongs
        to the button that began it.

        Args:
            window: The window the button was pressed in.
            button: The glfw code of the button.
            action: Whether the button was pressed or released.
            mods: The modifier keys held down with it.

        """
        import glfw  # noqa: PLC0415

        if button != glfw.MOUSE_BUTTON_LEFT:
            super().on_mouse_button(window, button, action, mods)
            return

        if action == glfw.PRESS and mods & glfw.MOD_CONTROL:
            self.carrying = True
            self.anchor = glfw.get_cursor_pos(window)
            return

        if self.carrying:
            self.carrying = False
            return

        super().on_mouse_button(window, button, action, mods)

    def on_cursor(self, _window: GLFWWindow, x: float, y: float) -> None:
        """
        Carry the window, or orbit the cube, as the mouse moves.

        The parent is called whatever happens: it is what remembers
        where the cursor stands, and the orbit reads its next move from
        there even when the window is the thing that moved.

        Args:
            _window: The window the mouse moved over, unused: the host
                carries the one it opened.
            x: Where the cursor stands, in pixels from the left.
            y: Where the cursor stands, in pixels from the top.

        """
        if self.carrying:
            self.carry(x, y)

        super().on_cursor(_window, x, y)

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
