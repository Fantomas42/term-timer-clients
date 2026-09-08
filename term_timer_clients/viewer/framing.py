"""Where the camera stands, and the views a key moves it between."""
from dataclasses import dataclass
from typing import Self

from cubing_algs.display.constants import ROTATION
from cubing_algs.display.rotation import turned_rotation

# The three quarter view of cubing-algs: three faces at once and none
# of them straight on, which is the framing an algorithm is read in and
# the one every window the library opens starts from. It is taken from
# the library rather than written down here - a demo view drifting away
# from the framing it is the demo of is the one thing it may not do -
# and `--rotation` is what replaces it, an angle typed by hand being
# this very view written out.
DEMO_VIEW = 'demo'

# The cube as the hand holding it sees it: F straight ahead, U in
# perspective above it, and nothing turned around the vertical. What
# turns around it is the cube itself, under the gyroscope, so a yaw
# here would be a permanent disagreement between the window and the
# hands. The elevation is the one of the library framing, and it is
# written out all the same: what this view names is a way of holding a
# cube, about which a library changing its three quarter view has
# nothing to say.
USER_VIEW = 'user'
USER_ROTATION = 'x-34'

# The views, and what a window opens on when nothing says otherwise.
# Looking from behind is not one of them: it is something done to the
# view one is in, so it is a flag over these two rather than a third
# name they would each need their own version of.
DEFAULT_VIEW = DEMO_VIEW

VIEWS = (DEMO_VIEW, USER_VIEW)

# What passing behind the cube costs, in degrees around the vertical.
HALF_TURN = 180


def flipped(rotation: str) -> str:
    """
    Turn a framing half a turn around the vertical.

    The arithmetic of a framing belongs to cubing-algs, which owns the
    grammar it is written in: what is said here is only that passing
    behind a cube is half a turn of the yaw and nothing else - the
    elevation is what makes the view, and it is kept.

    Args:
        rotation: The framing to pass behind, as the axis and angle
            parts of the SVG backend.

    Returns:
        The framing looking at the cube from the other side, at the
        very same height.

    """
    return turned_rotation(rotation, yaw=HALF_TURN)


@dataclass
class Framing:
    """
    Which view the camera stands in, and whether it is behind the cube.

    Two views and a flag, because that is what looking from behind is:
    a way of looking at the view one is in, not a view of its own. So
    it applies to either of them rather than to the one it would have
    been written against, it survives a change of view - someone
    watching a back and reframing is asking for the back of that
    framing - and there is one place saying what passing behind means
    instead of one per view.

    What comes out is a rotation string and never a camera: the viewer
    is what builds one, and ``rotation`` is also what it reframes on,
    so the view being watched is the view Space comes back to.
    """

    # What the demo view frames the cube from. It is a field rather
    # than a constant because `--rotation` redefines it: an angle typed
    # on the command line is the demo view written by hand, and it
    # stays reachable once another view has been stood in.
    demo: str = ROTATION

    view: str = DEMO_VIEW
    mirrored: bool = False

    @classmethod
    def opened_on(
            cls,
            view: str = DEFAULT_VIEW,
            rotation: str = '',
            *,
            mirrored: bool = False,
    ) -> Self:
        """
        Build the framing a window opens on.

        Args:
            view: The view named on the command line.
            rotation: The angle typed on the command line, empty for
                the framing of cubing-algs.
            mirrored: Whether the window opens behind the cube.

        Returns:
            The framing, standing where it was asked to stand.

        """
        return cls(
            demo=rotation or ROTATION,
            view=view,
            mirrored=mirrored,
        )

    @property
    def rotation(self) -> str:
        """
        Tell the angle the camera is to be built from.

        Returns:
            The framing of the view being watched, passed behind the
            cube when that is where it is being watched from.

        """
        base = USER_ROTATION if self.view == USER_VIEW else self.demo

        if not self.mirrored:
            return base

        return flipped(base)

    def show(self, view: str) -> None:
        """
        Stand in a view, from wherever the camera stands now.

        Whether the cube is being watched from behind is left exactly
        as it was, and that is the whole of what makes it a flag:
        someone watching the back of a cube and reframing it is asking
        for the back of that framing.

        Args:
            view: The view to stand in.

        """
        self.view = view

    def flip(self) -> None:
        """Pass behind the cube, or come back in front of it."""
        self.mirrored = not self.mirrored
