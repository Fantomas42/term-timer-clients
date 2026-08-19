"""The cube assembling itself around its core, and falling apart again."""
import math
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace

from cubing_algs.display.gl.constants import CORE_COLOR
from cubing_algs.display.gl.constants import Look
from cubing_algs.display.gl.geometry import Cubie
from cubing_algs.display.gl.scene import CubieInstance
from cubing_algs.display.gl.scene import Scene
from cubing_algs.display.gl.transforms import Mat4
from cubing_algs.display.gl.transforms import Quat
from cubing_algs.display.gl.transforms import Vec3

# How far below the cube the floor lies, counted in the reach of the
# cube itself: a piece resting there is out of the frame whatever the
# size of the cube, and what is left in the window is the ball core
# alone. Measured rather than fixed, so that a zoom of a notch or two
# does not bring the pieces back into view.
FLOOR_DEPTH = 3.0

# Seconds a cube takes to gather itself, and to fall back down. The
# fall is the shorter of the two: a magnet takes its time, gravity
# does not.
MAGNET_DURATION = 1.4
FALL_DURATION = 1.0

# Share of the animation spent handing the pieces their turn, the rest
# being what a single piece takes to travel. It is what makes the cube
# build up from the floor instead of arriving in one block.
STAGGER = 0.65

# How far a piece flies past its place before settling back onto it,
# as the coefficient of a back easing rather than a distance: the
# overshoot is a small share of the travel, which is what keeps the
# snap of a magnet from turning into a bounce.
MAGNET_BACK = 0.5

# How much a piece is turned away from its place while it flies, in
# radians. It is spent on the way up, so a piece lands square.
TUMBLE = 1.2

# The core of a cube nobody is connected to: an obsidian ball, all but
# out. It takes the color of a core back as the pieces gather around
# it, and loses it again as they let go - the one thing left in the
# window has to say for itself whether there is a cube behind it.
DORMANT_CORE: tuple[float, float, float] = (0.04, 0.04, 0.05)

# What the breath carries that ball to and back from: a dark red, the
# ember of something on standby. Two colors nobody could take for the
# blue green of a live core, which is what keeps waiting from being
# read as running.
PULSE_CORE: tuple[float, float, float] = (0.38, 0.05, 0.06)

# Seconds of one full breath of a core left on its own, in and back
# out. A ball sitting perfectly still says nothing about whether the
# window is waiting or has stopped: the wait is what has to be seen,
# and a slow swell is what shows it without ever asking to be looked
# at.
PULSE_PERIOD = 2.6

# How much the rim light around a waiting core swells with the same
# breath, as a share of the strength the look gives it. The color says
# the ball is on standby and the light says it is waiting, which is
# why the breath is spent on both rather than on either.
PULSE_RIM = 1.4

# Seconds the ball core takes to light up once the link is up. Short,
# and above all its own: the link and the state are two events, and a
# cube that has just connected stays silent about its colors for as
# long as it pleases - a core waiting for the facelets would have the
# window say nothing happened for all that time. It goes out on the
# fall of the pieces instead, the departure being one gesture where
# the arrival is two.
CORE_DURATION = 0.5


def clamp(value: float) -> float:
    """
    Hold a value inside the unit interval.

    Args:
        value: The value to bound.

    Returns:
        The value, brought back between zero and one.

    """
    return min(1.0, max(0.0, value))


def magnet(phase: float) -> float:
    """
    Ease a piece onto its place, a hair past it and back.

    A back easing: the overshoot is a share of the travel and not a
    distance of its own, which is what keeps the snap of a magnet from
    growing with the height a piece was picked up from.

    Args:
        phase: How far along its own travel the piece is.

    Returns:
        How much of the distance it has covered, briefly past one.

    """
    lag = phase - 1.0

    return 1.0 + lag * lag * ((MAGNET_BACK + 1.0) * lag + MAGNET_BACK)


def gravity(phase: float) -> float:
    """
    Ease a piece towards the floor, faster and faster.

    Read backwards, as the fall is: the phase runs down from one, and
    the distance left grows as the square of the time spent falling,
    which is the whole of what gravity does.

    Args:
        phase: How far along its own travel the piece is.

    Returns:
        How much of the distance it has covered.

    """
    lag = 1.0 - phase

    return 1.0 - lag * lag


def breath(elapsed: float) -> float:
    """
    Tell how far into its breath a core left alone stands.

    A cosine rather than a triangle: the swell has no corner at either
    end of it, and a wait that never snaps is what keeps the effect
    from reading as a blink. It is read at none of itself when no time
    has passed, so a core just left on its own is the very obsidian it
    is described by.

    Args:
        elapsed: Seconds gone by since the viewer opened, wrapped on a
            period.

    Returns:
        How much of the breath is in, from none of it to all of it.

    """
    return (1.0 - math.cos(2.0 * math.pi * elapsed / PULSE_PERIOD)) / 2.0


def waiting_core(elapsed: float) -> tuple[float, float, float]:
    """
    Paint the core of a cube nobody is connected to, breathing.

    Obsidian to a dark red and back, the ember of something on
    standby: what is waiting must not be mistaken for what is running,
    so the breath is spent between two colors the live core is nowhere
    near.

    Args:
        elapsed: Seconds gone by since the viewer opened, wrapped on a
            period.

    Returns:
        The color the ball core is painted with while it waits.

    """
    share = breath(elapsed)

    return (
        DORMANT_CORE[0] + (PULSE_CORE[0] - DORMANT_CORE[0]) * share,
        DORMANT_CORE[1] + (PULSE_CORE[1] - DORMANT_CORE[1]) * share,
        DORMANT_CORE[2] + (PULSE_CORE[2] - DORMANT_CORE[2]) * share,
    )


def core_color(share: float, elapsed: float) -> tuple[float, float, float]:
    """
    Mix the waiting core and the live one, channel by channel.

    The breath lives in the waiting end of the mix alone, which is what
    makes it fade of itself as the pieces gather: a cube barely started
    has already lost most of its breath, and a cube whole has none of
    it at all.

    Args:
        share: How much of the live color to take, from none of it to
            all of it.
        elapsed: Seconds gone by since the viewer opened, wrapped on a
            period.

    Returns:
        The color the ball core is painted with.

    """
    dormant = waiting_core(elapsed)

    return (
        dormant[0] + (CORE_COLOR[0] - dormant[0]) * share,
        dormant[1] + (CORE_COLOR[1] - dormant[1]) * share,
        dormant[2] + (CORE_COLOR[2] - dormant[2]) * share,
    )


def tumble_axis(cubie: Cubie) -> Vec3:
    """
    Pick the axis one piece turns around while it is off its place.

    Derived from where the piece belongs rather than drawn at random:
    the same cube falls the same way twice, which is what makes the
    effect testable at all, and no two neighbours turn quite alike.

    Args:
        cubie: The piece to turn.

    Returns:
        The axis it turns around, of no particular length.

    """
    seed = float(cubie.x * 7 + cubie.y * 13 + cubie.z * 23)

    return Vec3(
        math.sin(seed),
        math.cos(seed * 1.7),
        math.sin(seed * 2.3 + 1.0),
    )


@dataclass(frozen=True, slots=True)
class Flight:
    """
    The frame one moment of the effect moves its pieces through.

    Everything a piece needs to be placed, measured once for the whole
    of a frame: where the floor lies, how the cube is held, and how far
    along the assembly stands. A piece is then placed knowing nothing
    of the assembly it belongs to.
    """

    world: Mat4
    unworld: Mat4
    floor: float
    reach: float
    progress: float
    rising: bool

    def phase(self, height: float) -> float:
        """
        Tell how far along its own travel a piece stands.

        The pieces are handed their turn by their height **on the
        screen**, and that single rule reads both ways: gathering, the
        lowest go first and the cube builds up from the floor; letting
        go, the highest are the first to be left behind and the cube
        caves in from the top. One rule rather than two is also what
        lets a link that flickers reverse mid-flight without a piece
        ever jumping.

        Args:
            height: Where the piece stands on the screen, in world
                units above the center of the cube.

        Returns:
            How far along its own travel the piece is.

        """
        rank = clamp((height / self.reach + 1.0) / 2.0)

        return clamp((self.progress - rank * STAGGER) / (1.0 - STAGGER))

    def place(self, instance: CubieInstance) -> CubieInstance:
        """
        Move one piece to where this moment of the effect has it stand.

        The drop is composed **around** the orientation, and the
        tumble **into** the model: the first is a fall down the window,
        which the frame of the cube would tilt, and the second is a
        piece turning on itself, which is the frame of the cube and
        nothing else.

        Args:
            instance: The piece to place, as the scene drew it.

        Returns:
            The very same piece, taken to where it flies right now.

        """
        height = self.world.transform_point(instance.cubie.center).y
        phase = self.phase(height)
        settled = (magnet if self.rising else gravity)(phase)

        if settled >= 1.0:
            return instance

        left = 1.0 - settled

        lift = Mat4.translation(
            Vec3(0.0, -(self.floor + height) * left, 0.0),
        )
        tumble = Quat.from_axis_angle(
            tumble_axis(instance.cubie), TUMBLE * left,
        ).to_matrix()

        return replace(
            instance,
            model=(
                self.unworld @ lift @ self.world @ instance.model @ tumble
            ),
        )


@dataclass
class Assembly:
    """
    A cube gathering around its core, or letting go of it.

    The whole of the effect, and none of it touches the viewer: a scene
    comes in and a scene comes out, its pieces moved. ``progress`` is
    where the pieces stand, kept from a frame to the next, zero for a
    cube lying on the floor and one for a cube whole; ``glow`` is where
    the core stands, on the link alone; ``elapsed`` is the clock the
    core left alone in the window breathes on.

    **The core and the pieces are two effects on two events**, and
    that is the whole of why there are two progressions: a cube
    announces its link and describes its colors seconds apart, the
    core answers the first and the pieces the second. One progression
    shared would have the ball wait for the facelets and the window
    show nothing at all of a cube that has already connected.

    **The floor is the floor of the screen, not of the cube.** The
    shader draws a piece at ``world * model``, ``world`` being how the
    gyroscope holds the cube, so a drop written into the model alone
    would fall towards the D face and land sideways whenever the cube
    is held at an angle. The drop is therefore framed by the
    orientation and undone by its conjugate, and the pieces fall down
    the window however the cube is being held.
    """

    progress: float = 0.0
    rising: bool = False

    # How much of the live color the ball core carries, from the
    # obsidian of a cube nobody is connected to, to the blue green of
    # a core running. It is moved by the link and by nothing else,
    # which is what lets it be lit while the pieces are still lying on
    # the floor waiting for a state.
    glow: float = 0.0

    # Where the breath of a waiting core stands, in seconds wrapped on
    # its own period: an effect nobody ever closes the window on would
    # otherwise count the seconds of a whole night into a float, and
    # lose the precision the swell is made of. It runs behind a
    # connected cube too - the breath is worth nothing then, the mix
    # having none of it left, and a link that drops picks it up where
    # it stands rather than starting it over on a jump.
    elapsed: float = 0.0

    # The distance of the farthest piece from the center of the cube,
    # which the floor and the ranking are both measured in. Read off a
    # scene rather than given: the geometry of a viewer is built once
    # and never changes, so measuring it once is measuring it for good.
    reach: float = field(init=False, default=0.0)

    # The cube with no piece at all, kept rather than rebuilt: it is
    # what a viewer with no cube draws frame after frame, and a
    # renderer skips the upload of a scene it recognizes by identity.
    hidden: Scene | None = field(init=False, default=None)

    def measure(self, scene: Scene) -> float:
        """
        Tell how far the cube reaches, measuring it once.

        Args:
            scene: The cube being drawn.

        Returns:
            The distance from the center of the cube to the center of
            its farthest piece.

        """
        if not self.reach:
            self.reach = max(
                instance.cubie.center.length()
                for instance in scene.instances
            )

        return self.reach

    def empty(self, scene: Scene) -> Scene:
        """
        Hand a cube with no piece at all over.

        Nothing is drawn away from the window and hoped to be out of
        it: the pieces are simply not handed to the renderer, and the
        ball core, which is drawn on its own before them, is left alone
        in the window.

        Args:
            scene: The cube being drawn.

        Returns:
            The very same cube, its pieces held back.

        """
        if self.hidden is None:
            self.hidden = replace(scene, instances=())

        return self.hidden

    def settle(self, *, present: bool, linked: bool, delta: float) -> None:
        """
        Move the assembly towards the cube being there, or being gone.

        A fixed pace rather than the exponential approach the opening
        of the cube travels by: an effect that has to be seen through
        cannot be forever arriving, and the two directions are timed
        apart because they are not the same gesture.

        The core is moved on the link and the pieces on the state,
        each at its own pace: the ball lights up the moment the stream
        says there is a cube, and the pieces gather when the cube has
        said what it looks like. A link that is up with nothing
        described yet is exactly the moment the two are told apart.

        Args:
            present: Whether there is a cube to show.
            linked: Whether the link with the cube is up.
            delta: Seconds gone by since the last frame.

        """
        self.rising = present
        self.elapsed = (self.elapsed + max(delta, 0.0)) % PULSE_PERIOD

        elapsed = max(delta, 0.0)

        step = elapsed / (MAGNET_DURATION if present else FALL_DURATION)

        if present:
            self.progress = min(1.0, self.progress + step)
        else:
            self.progress = max(0.0, self.progress - step)

        # The fall is shared with the pieces and the rise is not: a
        # cube goes away in one gesture, the ball going out as the
        # pieces cave in, where it arrives in two.
        lit = elapsed / (CORE_DURATION if linked else FALL_DURATION)

        if linked:
            self.glow = min(1.0, self.glow + lit)
        else:
            self.glow = max(0.0, self.glow - lit)

    def apply(self, scene: Scene, orientation: Quat) -> Scene:
        """
        Place every piece where the assembly has it stand right now.

        A cube whole hands the very same scene back, so the effect
        costs nothing at all once it is over - which is the state a
        viewer spends its life in, and the one the instance buffer is
        cached on.

        Args:
            scene: The cube being drawn.
            orientation: How the whole cube is held, the frame the fall
                is taken out of.

        Returns:
            The cube, its pieces moved to where they fly right now.

        """
        if self.progress >= 1.0:
            return scene

        if self.progress <= 0.0:
            return self.empty(scene)

        reach = self.measure(scene)

        flight = Flight(
            world=orientation.to_matrix(),
            unworld=orientation.conjugate().to_matrix(),
            floor=FLOOR_DEPTH * reach,
            reach=reach,
            progress=self.progress,
            rising=self.rising,
        )

        return replace(
            scene,
            instances=tuple(
                flight.place(instance)
                for instance in scene.instances
            ),
        )

    def tint(self, look: Look) -> Look:
        """
        Paint the ball core for how much of a cube stands around it.

        The one thing left in the window when nothing is connected has
        to say so for itself: an obsidian ball is waiting, a blue green
        one is running. It travels on the link and not with the
        pieces, so the ball answers the cube connecting rather than
        the state it takes its time to describe - a core still on
        standby while the stream has already said there is a cube
        would have the picture say the opposite of what was published.

        A ball alone in the window breathes on top of that, colour and
        rim light together: a still picture says nothing of whether the
        viewer is waiting for a cube or has stopped, and the swell is
        what tells the two apart. Both halves are weighed by what is
        missing of the *core*, so the breath goes out exactly as the
        color comes in rather than lingering under a ball already lit.

        The very look is handed back once the core is lit, so a
        connected viewer draws the picture cubing-algs describes and
        nothing of the effect is left in it.

        Args:
            look: How the light falls on the cube, as the viewer holds
                it.

        Returns:
            The same look, its core painted for the moment.

        """
        if self.glow >= 1.0:
            return look

        waiting = breath(self.elapsed) * (1.0 - self.glow)

        return replace(
            look,
            core_color=core_color(self.glow, self.elapsed),
            core_rim_strength=look.core_rim_strength * (
                1.0 + PULSE_RIM * waiting
            ),
        )

    def advance(
            self,
            scene: Scene,
            orientation: Quat,
            *,
            present: bool,
            linked: bool,
            delta: float,
    ) -> Scene:
        """
        Let time pass, and hand the picture it leads to over.

        Args:
            scene: The cube being drawn.
            orientation: How the whole cube is held.
            present: Whether there is a cube to show.
            linked: Whether the link with the cube is up.
            delta: Seconds gone by since the last frame.

        Returns:
            The cube to draw right now.

        """
        self.settle(present=present, linked=linked, delta=delta)

        return self.apply(scene, orientation)
