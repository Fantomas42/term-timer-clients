"""A breath on the cube, when it has a piece of news to tell."""
from dataclasses import dataclass
from dataclasses import replace

from cubing_algs.display.gl.constants import Look
from cubing_algs.display.gl.constants import clamp
from cubing_algs.display.gl.scene import CubieInstance
from cubing_algs.display.gl.scene import Scene
from cubing_algs.display.gl.transforms import Mat4
from cubing_algs.display.gl.transforms import Quat
from cubing_algs.display.gl.transforms import Vec3

from term_timer_clients.viewer.assembly import tumble_axis

# Share of the breath spent rising, the rest being spent coming back
# down. A quarter, and never a half: what is being told is a piece of
# news, and news arrives - a swell taking as long to leave as it took
# to come beats like a metronome, which is the shape a wait is drawn
# with and the one thing an announcement may not be read as. The sharp
# attack is what the eye catches, and the long fall is what lets it
# read the cube again before the picture has settled.
ATTACK_SHARE = 0.25

# Share of the breath spent handing the shells their turn, the rest
# being what a single piece takes to travel. Read exactly as the
# ``SHOCKWAVE`` of the blast is: the pieces are ranked by their
# distance to the core, so the gust leaves the ball and runs outwards
# through the cube instead of lifting it in one block.
#
# It is what keeps the shells in order too, and that is arithmetic
# rather than luck: the lag it can open between two neighbouring
# shells is worth a fraction of the gap their radii already put
# between them, for any reach at or under one. So an inner piece never
# overtakes the piece covering it, however sharp the attack.
WAVEFRONT = 0.3

# How far the rim light of a flared cube reaches in, as a share of the
# glow it is lit by. The rim is the one light the breath is spent on,
# and the reason is the one the waiting core is drawn by: it
# **multiplies** the color, where the highlight is added on top of it
# and added white - a sheen swelling over the cube glows the color of
# the lamp and washes the fifty-four stickers out, where a rim
# brightening and reaching further in lights the cube in its own
# colors.
FLARE_HALO = 0.35

# The colors the four pieces of news are told in, and the whole of
# what tells them apart at a glance: warm amber for a cube that came
# back solved, cold blue for a scramble that has just been laid on it.
# Far enough apart on the wheel that no lighting and no palette can
# have one read as the other - what a window says of a solve landing
# must never have to be worked out.
SOLVED_HUE = Vec3(1.0, 0.62, 0.22)

SCRAMBLED_HUE = Vec3(0.22, 0.48, 1.0)

# The two ends of one attempt on a trained case, and **they are
# neighbours on the wheel where the amber and the blue are opposites**.
# That is the argument rather than what was left of it: the start and
# the end of a solve are two different things and are told as two,
# where a case that came out and a case that did not are two versions
# of the very same thing - a DNF is not the contrary of a case landed,
# it is its other end. So a violet a third of the wheel from either
# announcement, and a crimson a step from that violet.
TRAINED_HUE = Vec3(0.72, 0.36, 1.0)

FAILED_HUE = Vec3(0.95, 0.16, 0.34)

# The words the pieces of news travel under, from the client writing
# one down to the window playing it. Both sides are in this file for
# the reason both sides of an order are in ``orders.py``: one place
# saying what a word means, rather than two that will disagree the day
# one of them is reworded.
SOLVED_WORD = 'solved'

SCRAMBLED_WORD = 'scrambled'

TRAINED_WORD = 'trained'

FAILED_WORD = 'failed'


def smoothstep(share: float) -> float:
    """
    Ease a share between nothing and all of it, with no corner either end.

    The one curve the breath is written on, read forwards on the
    attack and backwards on the fall: it leaves and lands at a
    standstill, which is what makes a cube taken apart and put back
    never be seen to jump.

    Args:
        share: How far along, from none of the way to all of it.

    Returns:
        The eased share, from nothing to all of it.

    """
    bounded = clamp(share)

    return bounded * bounded * (3.0 - 2.0 * bounded)


def swell(phase: float) -> float:
    """
    Tell how far into its breath a flare stands.

    Two readings of one curve around ``ATTACK_SHARE``: a smoothstep
    over the first quarter, and the very same one read backwards over
    the rest. **It is worth exactly nothing at either end and exactly
    one at the top**, which is what makes the return to rest an
    equality rather than an approach - a cube that is not flaring is a
    cube handed back untouched, and the instance buffer of the
    renderer is cached on that identity.

    A sharp attack and a long fall, and that is the whole shape of the
    thing: what is being told is news, and news arrives. A swell
    taking as long to leave as it took to come beats like a metronome,
    which is what a *wait* is drawn with.

    Args:
        phase: How far along its own breath the flare is.

    Returns:
        How much of the breath is in, from none of it to all of it.

    """
    if phase <= 0.0 or phase >= 1.0:
        return 0.0

    if phase < ATTACK_SHARE:
        return smoothstep(phase / ATTACK_SHARE)

    return smoothstep((1.0 - phase) / (1.0 - ATTACK_SHARE))


@dataclass(frozen=True, slots=True)
class Flare:
    """
    The flavour of one piece of news, and the only thing two differ by.

    How long the breath lasts, how far it carries a piece, how much it
    turns it on the way, the color it is told in and how much light it
    is told with. Everything else - the curve, the wavefront, the ray
    a piece travels - is the breath itself and is shared by every one
    of them: two announcements made in two shapes would be two effects
    rather than one word said twice.

    **The color travels on the plastic and on the core, never on the
    stickers.** The fifty-four facelets keep what their palette gives
    them, which is the principle cubing-algs is built on: the color of
    a cube is what one reads to know where it stands, and a client
    moving it for the length of an animation makes the window lie
    about the state of the cube. What the gust uncovers as it pushes
    the pieces apart is the ball core, and what frames every sticker
    is the plastic - so the two of them carry the news, and the cube
    goes on saying what it truly is while they do.
    """

    # Seconds the whole of the breath lasts, from the cube at rest to
    # the cube at rest again.
    duration: float

    # How far a piece is pushed out along its own ray at the peak,
    # counted in its own distance to the core. Held under one, which
    # is what keeps the shells in the order the wavefront hands them
    # their turn in.
    reach: float

    # How much a piece is turned away from its place at the peak, in
    # radians. Spent and given back, so a piece lands square.
    tumble: float

    # The color the news is told in, on the plastic and on the core.
    hue: Vec3

    # How far the two of them are carried towards that color at the
    # peak. Two shares rather than one: the core is seen through the
    # gaps the gust opens and the plastic is seen whole, so the same
    # weight on both would have one shout and the other whisper.
    plastic: float
    core: float

    # What the breath adds to the rim light, as a share of what the
    # look already gives it. The light and the color are two halves of
    # one word: a cube that only changed color would read as a palette
    # swapped, and one that only brightened as a lamp moved.
    glow: float


# A cube that came back solved: the wide, warm one. It is the news a
# session is made of, so it is given the room to be seen - the longest
# breath here, the furthest reach, and the amber of something that has
# just finished rather than something about to start.
SOLVED_FLARE = Flare(
    duration=1.1,
    reach=0.34,
    tumble=0.45,
    hue=SOLVED_HUE,
    plastic=0.85,
    core=0.9,
    glow=1.1,
)

# A scramble laid on the cube: the short, dry one. What it announces
# is a beginning, and a beginning is acknowledged rather than
# celebrated - half the breath, two thirds of the reach, and the cold
# blue at the other end of the wheel from the solve.
SCRAMBLED_FLARE = Flare(
    duration=0.65,
    reach=0.22,
    tumble=0.3,
    hue=SCRAMBLED_HUE,
    plastic=0.7,
    core=0.8,
    glow=0.8,
)

# A case that came out: the wide, warm one of a training session. What
# it announces is an attempt that is over and worth something, which
# is the news a training session is made of exactly as the solve is
# the news a timed one is made of - so it is given the same room to be
# seen, and the violet is what says which of the two it is.
TRAINED_FLARE = Flare(
    duration=1.0,
    reach=0.30,
    tumble=0.42,
    hue=TRAINED_HUE,
    plastic=0.82,
    core=0.9,
    glow=1.0,
)

# A case that did not come out: the dull one. **What makes it dull is
# the glow**, the lowest of the four, rather than merely the shortest
# breath: the rim barely rises, so the cube gives a start instead of
# lighting up. A failure is told, never announced - what it is worth
# is the news that the attempt happened at all.
#
# Its reach and its tumble stay under everything else here for the
# reason ``WAVEFRONT`` documents: the shells keep their order for any
# reach at or under one, and a piece of news one regrets does not open
# the cube.
FAILED_FLARE = Flare(
    duration=0.45,
    reach=0.13,
    tumble=0.16,
    hue=FAILED_HUE,
    plastic=0.55,
    core=0.6,
    glow=0.3,
)

# The word one side writes down and the other plays, and the two sides
# are here together on purpose: a name spelled in the client and read
# in the window is one word, and one word lives in one file. A name
# nobody here knows is simply not in it, and what reads this ignores
# it - exactly what a client does with a topic it does not know.
FLARES: dict[str, Flare] = {
    SOLVED_WORD: SOLVED_FLARE,
    SCRAMBLED_WORD: SCRAMBLED_FLARE,
    TRAINED_WORD: TRAINED_FLARE,
    FAILED_WORD: FAILED_FLARE,
}


def flared(look: Look, flare: Flare) -> Look:
    """
    Describe the light a cube telling a piece of news stands in.

    Built **on the look it is handed** rather than written out whole,
    for the reason a dormant core is: what a flare changes is the
    color of the core and the reach of the rim, and every other term -
    the ambient, the grooves, the gloss of a sticker - is the one the
    viewer was built with. So the two looks differ by those terms
    alone, and reading all of them part of the way at once cannot move
    anything else.

    The rim and nothing else, of the lights: it multiplies the color,
    so a cube lit by it glows in the colors it is actually wearing,
    where the highlight is added on top and added white and would wash
    the palette out the moment it swelled.

    Args:
        look: How the light falls on the cube, as the viewer holds it.
        flare: The flavour of the news being told.

    Returns:
        The look the cube is drawn in at the top of its breath.

    """
    return replace(
        look,
        core_color=Vec3(*look.core_color).lerp(flare.hue, flare.core),
        rim_strength=look.rim_strength * (1.0 + flare.glow),
        rim_power=look.rim_power * (1.0 - FLARE_HALO),
        core_rim_strength=look.core_rim_strength * (1.0 + flare.glow),
        core_rim_power=look.core_rim_power * (1.0 - FLARE_HALO),
    )


@dataclass(frozen=True, slots=True)
class Gust:
    """
    The frame one moment of the breath moves its pieces through.

    Everything a piece needs to be pushed, measured once for the whole
    of a frame: how far the cube reaches, how far along the breath
    stands, and the flavour saying how far and how hard it pushes. A
    piece is then placed knowing nothing of the cube it belongs to.

    **A piece only ever travels its own ray**, the one that leaves the
    core and goes through where the piece belongs - the very rule the
    blast is written on, and for the very same reason: two rays
    leaving the same point never meet again, and the ball core sits at
    the point they leave. It is also what lets the two effects be
    composed at all, a breath arriving in the middle of an implosion
    pushing every piece further along the line it was already on.
    """

    reach: float
    spread: float
    flare: Flare

    def phase(self, radius: float) -> float:
        """
        Tell how far along its own breath a piece stands.

        The pieces are handed their turn by their **distance to the
        core**, so the gust leaves the ball and runs outwards through
        the cube rather than lifting it in one block: the centers
        first, the corners last.

        Args:
            radius: How far from the core the piece belongs.

        Returns:
            How far along its own breath the piece is.

        """
        rank = clamp(radius / self.reach)

        return clamp((self.spread - rank * WAVEFRONT) / (1.0 - WAVEFRONT))

    def place(self, instance: CubieInstance) -> CubieInstance:
        """
        Push one piece to where this moment of the breath has it stand.

        The push is composed **around** the model and the tumble
        **into** it, exactly as the blast composes them: the first
        takes the piece out along the ray of the cube it belongs to,
        the second is a piece turning on itself, which is its own
        frame and nothing else. Neither is held in the frame of the
        window - a breath leaves the core in every direction at once,
        so it says the same thing however the cube is being held.

        Nothing is scaled here, unlike the blast: a piece pushed a
        third of its own radius never comes near enough the camera to
        loom over anything, and a cube whose pieces shrank as they
        parted would read as a cube being taken away rather than one
        catching its breath.

        A piece the wavefront has not reached yet is handed back
        untouched, which is what lets a breath that has not started
        cost nothing at all.

        Args:
            instance: The piece to place, as the scene drew it.

        Returns:
            The very same piece, pushed to where it stands right now.

        """
        center = instance.cubie.center
        share = self.phase(center.length())

        if not share:
            return instance

        push = Mat4.translation(center.scaled(self.flare.reach * share))
        tumble = Quat.from_axis_angle(
            tumble_axis(instance.cubie), self.flare.tumble * share,
        ).to_matrix()

        return replace(instance, model=push @ instance.model @ tumble)


@dataclass
class Burst:
    """
    A cube catching its breath over a piece of news, or not catching it.

    The whole of the effect, and none of it touches the viewer: a
    scene comes in and a scene comes out, its pieces pushed and its
    plastic tinted. ``flare`` is the flavour being told and nothing at
    all the rest of the time, ``elapsed`` how far into it the window
    stands.

    **A cube that is not flaring costs exactly nothing**, and that is
    the hard constraint rather than an optimisation: ``apply()`` hands
    the very same scene back and ``tint()`` the very same look, so the
    renderer recognizes the scene by identity and uploads no instance
    buffer at all. It is the state the window spends its life in.

    It is layered **on top of** the assembly rather than beside it,
    and the order is what makes the two safe together: the assembly
    places the pieces, the breath pushes them out from where they
    stand. Both travel the ray leaving the core through the place a
    piece belongs to, so a breath arriving in the middle of an
    implosion adds to it without a piece ever meeting another.
    """

    # The flavour of the news being told, and nothing at all the rest
    # of the time. ``None`` rather than a flare at rest: a cube with
    # nothing to announce is the state everything here is written to
    # cost nothing in, and one field answering one question is what
    # says so plainly.
    flare: Flare | None = None

    # How far into the breath the window stands, in seconds. It is
    # never wrapped, unlike the clocks of a waiting core: a breath
    # ends, and what ends it is this counter reaching the duration of
    # the flavour being told.
    elapsed: float = 0.0

    @property
    def share(self) -> float:
        """
        Tell how much of the breath the cube is standing in right now.

        Returns:
            The swell of the moment, nothing at all when there is no
            news being told.

        """
        if self.flare is None:
            return 0.0

        return swell(self.elapsed / self.flare.duration)

    def fire(self, name: str) -> None:
        """
        Start telling the piece of news one word names.

        A word nobody here knows is ignored rather than guessed at,
        the empty one included, which is what a client does with a
        topic it does not know and what a window does with an order it
        does not know. A flare arriving over one already being told
        starts over: the news is what matters, and two breaths
        overlapping would be a cube shivering rather than answering.

        Args:
            name: What is being announced, empty for nothing at all.

        """
        flare = FLARES.get(name)

        if flare is None:
            return

        self.flare = flare
        self.elapsed = 0.0

    def settle(self, delta: float) -> None:
        """
        Let the breath run, and drop it the moment it is over.

        The flavour is let go rather than left standing at the end of
        its own curve: what says a cube has nothing to announce is the
        absence of a flare, and a flare kept at a swell of zero would
        be the same picture at a cost nobody is paying for.

        Args:
            delta: Seconds gone by since the last frame.

        """
        if self.flare is None:
            return

        self.elapsed += max(delta, 0.0)

        if self.elapsed >= self.flare.duration:
            self.flare = None
            self.elapsed = 0.0

    def apply(self, scene: Scene) -> Scene:
        """
        Push every piece where the breath has it stand, and tint it.

        The pieces and the plastic move together and are two halves of
        one word: the gust opens the cube and the color says what it
        is opening about. The stickers are left exactly as the palette
        painted them - what a cube is showing is how one reads where
        it stands, and a window repainting it for a second would be a
        window lying about the state of the cube.

        A cube with nothing to announce hands the very same scene
        back, so the effect costs nothing at all outside its own
        breath - which is the state a viewer spends its life in, and
        the one the instance buffer is cached on.

        Args:
            scene: The cube being drawn.

        Returns:
            The cube, its pieces pushed and its plastic tinted.

        """
        flare = self.flare
        spread = self.share

        if flare is None or not spread:
            return scene

        gust = Gust(
            reach=scene.geometry.reach,
            spread=spread,
            flare=flare,
        )

        return replace(
            scene.mapped(gust.place),
            plastic=Vec3(*scene.plastic).lerp(
                flare.hue, flare.plastic * spread,
            ),
        )

    def tint(self, look: Look) -> Look:
        """
        Paint the light the cube tells its piece of news in.

        One mix and never one per knob, exactly as a dormant core is
        mixed: the flared look differs from the one the viewer holds
        by the core and the rim alone, so every term can be read part
        of the way at once and nothing else can move. A knob added to
        a look tomorrow travels here without a line written for it.

        The core is in it because it is what the gust uncovers: the
        pieces part, the ball shows through the gaps, and it had
        better be saying the same thing the plastic around it is
        saying.

        Args:
            look: How the light falls on the cube, as the viewer holds
                it.

        Returns:
            The same look, lit for the news being told, and the very
            same object when there is none.

        """
        if self.flare is None:
            return look

        return look.blended(flared(look, self.flare), self.share)

    def advance(self, scene: Scene, *, delta: float) -> Scene:
        """
        Let time pass, and hand the picture it leads to over.

        Args:
            scene: The cube being drawn.
            delta: Seconds gone by since the last frame.

        Returns:
            The cube to draw right now.

        """
        self.settle(delta)

        return self.apply(scene)
