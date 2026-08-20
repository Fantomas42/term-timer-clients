"""The cube imploding around its core, and exploding away from it."""
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

# How far a piece is thrown away from the core, counted in its own
# distance to it: a piece blown out is out of the frame whatever the
# size of the cube, and what is left in the window is the ball core
# alone. Counted on the piece rather than fixed, which is also what
# keeps a zoom of a notch or two from bringing the pieces back into
# view.
BLAST_REACH = 3.0

# Seconds a cube takes to implode around its core, and to explode away
# from it. The blast is the shorter of the two: a cube gathers itself
# and a cube is torn apart, and the two are not the same gesture.
IMPLOSION_DURATION = 1.4
EXPLOSION_DURATION = 0.9

# Share of the animation spent handing the shells their turn, the rest
# being what a single piece takes to travel. It is what makes the
# blast run through the cube instead of moving it in one block.
SHOCKWAVE = 0.35

# How much a piece is turned away from its place while it flies, in
# radians. It is spent on the way in, so a piece lands square.
TUMBLE = 1.2

# The core of a cube nobody is connected to: graphite, a ball
# barely lit rather than a black one. Nearly out, and **not** out: the
# shader adds the highlight to the color instead of shading it, so a
# core taken down to black is a ball with nothing on it but that one
# spot of lamp - which is the plastic sphere of an old rendering and
# says nothing of a viewer waiting. Left a little of itself, the ball
# is read by its own volume, and its rim light exists at all: that one
# multiplies the color, and there is nothing to multiply on black. A
# breath of warmth away from neutral, so that the ember it breathes to
# is where the color already leans.
DORMANT_CORE: tuple[float, float, float] = (0.145, 0.138, 0.134)

# What the breath carries that ball to and back from: the ember of
# something on standby, banked rather than glowing. Sitting a step
# above the graphite instead of a leap - the swell has to be found by
# an eye resting on the window, never thrown at one crossing it - and
# nowhere near the blue green of a live core, which is what keeps
# waiting from being read as running. It is warmth rather than color:
# what swells is mostly the *light*, the hue barely leaning off the
# graphite, because a ball turning red says something happened where a
# ball brightening says something is waiting.
PULSE_CORE: tuple[float, float, float] = (0.225, 0.152, 0.132)

# Seconds of one full breath of a core left on its own, in and back
# out. A ball sitting perfectly still says nothing about whether the
# window is waiting or has stopped: the wait is what has to be seen,
# and a slow swell is what shows it without ever asking to be looked
# at. Slow is the whole of it - the breath of something at rest, taken
# over the seconds a sigh is taken over rather than the ones a pulse
# is counted in, and anything quicker reads as an alarm rather than as
# a wait.
PULSE_PERIOD = 6.0

# How the swell is weighed on top of the cosine. Above one, so that
# the ball spends the greater part of the period at the bottom of its
# breath and rises only briefly: a swell in and out over equal halves
# beats like a metronome, and what has to be shown is something at
# rest, not something counting.
BREATH_EASE = 1.6

# How the light around a waiting core swells with the same breath: the
# rim gains in strength and loses in tightness, so the edge of the ball
# both brightens and reaches further in. The color says the ball is on
# standby and the light says it is waiting, which is why the breath is
# spent on both rather than on either.
#
# The rim is the only light here the breath is allowed to touch, and
# the reason is in the shader: it **multiplies** the color, where the
# highlight is added on top of it and added white. A sheen opened up
# and raised over a whole ball glows, and it glows the color of the
# lamp - what swells is then a pale veil rather than an ember, and a
# ball washing out is neither discreet nor warm. So the highlight is
# taken matte and left there, still for the whole of the wait, and
# what breathes is a light wearing the color of the ball it lies on.
PULSE_RIM = 1.0
PULSE_HALO = 0.3

# What is left of the highlight of the core while nothing is connected,
# as a share of the strength and of the tightness the look gives it.
# The shader adds the highlight on top of the color rather than through
# it, so a spot of lamp on a nearly black ball is the one thing with
# any strength in it: kept whole it draws the hard, round glint of a
# rendering of thirty years ago, whatever the color underneath. Taken
# down and spread out, it becomes the sheen of something matte, and the
# ball is left to its own shape. Both come back with the link: the look
# is handed back untouched the moment the core is lit.
DORMANT_GLOSS = 0.12
DORMANT_GLOSS_SPREAD = 0.45

# Seconds the ball core takes to light up once the link is up. Short,
# and above all its own: the link and the state are two events, and a
# cube that has just connected stays silent about its colors for as
# long as it pleases - a core waiting for the facelets would have the
# window say nothing happened for all that time. It goes out on the
# blast of the pieces instead, the departure being one gesture where
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


def dimmed(value: float, share: float, missing: float) -> float:
    """
    Take one term of the light down to what a waiting core wears.

    Weighed by what the core is missing rather than by the breath: a
    ball on standby is matte for as long as it waits, where the swell
    is what says it is still waiting. So the term comes back exactly
    as the core lights up, and a lit one is handed the very light the
    look came with.

    Args:
        value: The term as the look gives it.
        share: How much of it a core with no cube behind it keeps.
        missing: How much of the live core is still to come.

    Returns:
        The term, taken down for the moment.

    """
    return value * (1.0 - (1.0 - share) * missing)


def shrink(scale: float) -> Mat4:
    """
    Build the matrix drawing a piece at a share of its own size.

    Args:
        scale: How much of itself the piece is drawn at.

    Returns:
        The matrix scaling a piece around its own center.

    """
    return Mat4.from_rows((
        (scale, 0.0, 0.0, 0.0),
        (0.0, scale, 0.0, 0.0),
        (0.0, 0.0, scale, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))


def blast(phase: float) -> float:
    """
    Ease a piece between its place and the far end of its ray.

    One cubic, and it is read both ways: gathering, a piece hangs out
    there and then rushes the last of the distance in, which is what a
    core pulling on it looks like; letting go, it is torn off at once
    and coasts the rest of the way out, which is what a blast looks
    like. The same curve travelled in the other direction, so a link
    that flickers reverses without a piece ever jumping.

    It never goes past one on either end: an overshoot would take a
    piece inside its own place, and inside a cube every place is
    already taken.

    Args:
        phase: How far along its own travel the piece is.

    Returns:
        How much of the distance it has covered.

    """
    return phase * phase * phase


def breath(elapsed: float) -> float:
    """
    Tell how far into its breath a core left alone stands.

    A cosine rather than a triangle: the swell has no corner at either
    end of it, and a wait that never snaps is what keeps the effect
    from reading as a blink. Weighed by ``BREATH_EASE`` on top of it,
    which is what keeps the two halves of the period from being worth
    the same: the ball lies at the bottom of its breath for the longer
    part of it and rises only briefly, where an even swell in and out
    beats like a metronome. It is read at none of itself when no time
    has passed, so a core just left on its own is the very graphite it
    is described by.

    Args:
        elapsed: Seconds gone by since the viewer opened, wrapped on a
            period.

    Returns:
        How much of the breath is in, from none of it to all of it.

    """
    swell = (1.0 - math.cos(2.0 * math.pi * elapsed / PULSE_PERIOD)) / 2.0

    return math.pow(swell, BREATH_EASE)


def waiting_core(elapsed: float) -> tuple[float, float, float]:
    """
    Paint the core of a cube nobody is connected to, breathing.

    Graphite to a banked ember and back: what is waiting must not be
    mistaken for what is running, so the breath is spent between two
    colors the live core is nowhere near, and over a stretch of
    seconds nobody could read as a pulse.

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
    the same cube blows apart the same way twice, which is what makes
    the effect testable at all, and no two neighbours turn quite alike.

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
    of a frame: how far the cube reaches, and how far along the blast
    stands. A piece is then placed knowing nothing of the cube it
    belongs to.

    **A piece only ever travels its own ray**, the one that leaves the
    core and goes through where the piece belongs, and that is the
    whole of why nothing collides: two rays leaving the same point
    never meet again, and the ball core sits at the point they leave.
    Nothing is ever driven through the middle of the cube, which no
    fall down the window could ever promise.
    """

    reach: float
    progress: float

    def phase(self, radius: float) -> float:
        """
        Tell how far along its own travel a piece stands.

        The pieces are handed their turn by their **distance to the
        core**, and that single rule reads both ways: imploding, the
        centers arrive first and the corners close the cube last;
        exploding, the corners are torn off first and the cube caves
        in from the outside. It is also what keeps the shells in
        order at every instant - an outer piece is never less thrown
        out than the piece it covers, so no shell is ever driven
        through another.

        Args:
            radius: How far from the core the piece belongs.

        Returns:
            How far along its own travel the piece is.

        """
        rank = clamp(radius / self.reach)

        return clamp((self.progress - rank * SHOCKWAVE) / (1.0 - SHOCKWAVE))

    def place(self, instance: CubieInstance) -> CubieInstance:
        """
        Move one piece to where this moment of the effect has it stand.

        The throw is composed **around** the model and the tumble
        **into** it: the first takes the piece out along the ray of
        the cube it belongs to, and the second is a piece turning on
        itself, which is its own frame and nothing else. Neither is
        held in the frame of the window: a blast leaves the core in
        every direction at once, so it says the same thing however the
        cube is being held.

        A piece is drawn at the very share of its travel it has
        covered, and that is not a taste: the ray of one piece points
        at the camera, and a piece thrown along it comes *closer*
        instead of going away - drawn whole it would loom over the
        core it is supposed to be leaving, and blink out of existence
        at the end of the blast. Going out as it goes away, it stays
        the size it is at rest wherever it is thrown, and there is
        nothing left to pop when it is finally dropped.

        Args:
            instance: The piece to place, as the scene drew it.

        Returns:
            The very same piece, taken to where it flies right now.

        """
        center = instance.cubie.center
        phase = self.phase(center.length())
        settled = blast(phase)

        if settled >= 1.0:
            return instance

        left = 1.0 - settled

        throw = Mat4.translation(center.scaled(BLAST_REACH * left))
        tumble = Quat.from_axis_angle(
            tumble_axis(instance.cubie), TUMBLE * left,
        ).to_matrix()

        return replace(
            instance,
            model=throw @ instance.model @ tumble @ shrink(phase),
        )


@dataclass
class Assembly:
    """
    A cube imploding around its core, or exploding away from it.

    The whole of the effect, and none of it touches the viewer: a scene
    comes in and a scene comes out, its pieces moved. ``progress`` is
    where the pieces stand, kept from a frame to the next, zero for a
    cube blown apart and one for a cube whole; ``glow`` is where the
    core stands, on the link alone; ``elapsed`` is the clock the core
    left alone in the window breathes on.

    **The core and the pieces are two effects on two events**, and
    that is the whole of why there are two progressions: a cube
    announces its link and describes its colors seconds apart, the
    core answers the first and the pieces the second. One progression
    shared would have the ball wait for the facelets and the window
    show nothing at all of a cube that has already connected.

    **The pieces move along the rays of the core, and along nothing
    else.** A drop down the window has pieces sliding past one another
    and through the ball they are supposed to be held by, whichever
    order they are handed their turn in; a blast has each of them
    leaving the core in its own direction, and rays that leave the
    same point never meet again. So no orientation is needed here
    either: the effect is drawn in the frame of the cube, and the
    shader holds that frame however the gyroscope turns it.
    """

    progress: float = 0.0

    # How much of the live color the ball core carries, from the
    # graphite of a cube nobody is connected to, to the blue green of
    # a core running. It is moved by the link and by nothing else,
    # which is what lets it be lit while the pieces are still out
    # there waiting for a state.
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
    # which the reach of the blast and the ranking are both measured
    # in. Read off a scene rather than given: the geometry of a viewer
    # is built once and never changes, so measuring it once is
    # measuring it for good.
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
        self.elapsed = (self.elapsed + max(delta, 0.0)) % PULSE_PERIOD

        elapsed = max(delta, 0.0)

        step = elapsed / (
            IMPLOSION_DURATION if present else EXPLOSION_DURATION
        )

        if present:
            self.progress = min(1.0, self.progress + step)
        else:
            self.progress = max(0.0, self.progress - step)

        # The blast is shared with the pieces and the rise is not: a
        # cube goes away in one gesture, the ball going out as the
        # pieces are thrown off, where it arrives in two.
        lit = elapsed / (CORE_DURATION if linked else EXPLOSION_DURATION)

        if linked:
            self.glow = min(1.0, self.glow + lit)
        else:
            self.glow = max(0.0, self.glow - lit)

    def apply(self, scene: Scene) -> Scene:
        """
        Place every piece where the assembly has it stand right now.

        A cube whole hands the very same scene back, so the effect
        costs nothing at all once it is over - which is the state a
        viewer spends its life in, and the one the instance buffer is
        cached on.

        Args:
            scene: The cube being drawn.

        Returns:
            The cube, its pieces moved to where they fly right now.

        """
        if self.progress >= 1.0:
            return scene

        if self.progress <= 0.0:
            return self.empty(scene)

        flight = Flight(
            reach=self.measure(scene),
            progress=self.progress,
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
        to say so for itself: a graphite ball is waiting, a blue green
        one is running. It is taken down and never put out: the
        highlight of the shader is added on top of the color, so a
        core painted black would be that one glint and nothing else -
        the plastic sphere of an old rendering, which is what a
        dimmed, spread out highlight on a ball with some body left
        takes the place of. It travels on the link and not with the
        pieces, so the ball answers the cube connecting rather than
        the state it takes its time to describe - a core still on
        standby while the stream has already said there is a cube
        would have the picture say the opposite of what was published.

        A ball alone in the window breathes on top of that, and the
        breath is spent on the light before it is spent on the hue: the
        rim brightens and reaches further in, and the ember it lies on
        barely leans off the graphite - a ball brightening says it is
        waiting where a ball turning red would say something happened.
        The rim and nothing else, because it multiplies the color where
        the highlight is added on top of it and added white: a sheen
        swelling over the ball washes it out instead of warming it, so
        the highlight is taken matte and held there for the whole of
        the wait. Every half of it is weighed by what is missing of the
        *core*, so the breath goes out exactly as the color comes in
        rather than lingering under a ball already lit.

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

        missing = 1.0 - self.glow
        waiting = breath(self.elapsed) * missing

        return replace(
            look,
            core_color=core_color(self.glow, self.elapsed),
            core_rim_strength=look.core_rim_strength * (
                1.0 + PULSE_RIM * waiting
            ),
            core_rim_power=look.core_rim_power * (
                1.0 - PULSE_HALO * waiting
            ),
            core_specular_strength=dimmed(
                look.core_specular_strength, DORMANT_GLOSS, missing,
            ),
            core_specular_power=dimmed(
                look.core_specular_power, DORMANT_GLOSS_SPREAD, missing,
            ),
        )

    def advance(
            self,
            scene: Scene,
            *,
            present: bool,
            linked: bool,
            delta: float,
    ) -> Scene:
        """
        Let time pass, and hand the picture it leads to over.

        Args:
            scene: The cube being drawn.
            present: Whether there is a cube to show.
            linked: Whether the link with the cube is up.
            delta: Seconds gone by since the last frame.

        Returns:
            The cube to draw right now.

        """
        self.settle(present=present, linked=linked, delta=delta)

        return self.apply(scene)
