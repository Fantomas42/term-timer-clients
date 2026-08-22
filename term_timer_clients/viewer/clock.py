"""How old a move already is by the time the window hears about it."""
from collections import deque

# What is granted to a move before anything is measured, in seconds: a
# cube reports a face once it has stopped turning, the report crosses a
# bluetooth link, and none of that is visible from here. It is the one
# part of the delay no arithmetic can recover - the minimum of the
# link hides inside the offset of the clocks - so it is stated rather
# than computed, and the command line is where it is argued with.
MOVE_LEAD = 0.05

# How many arrivals the offset of the two clocks is read on. The
# smallest delay observed over them is the best reading there is, and
# the window is what lets it be forgotten: a lucky packet would
# otherwise hold the offset down for the whole session and report every
# later move as late. Sixty four moves is several seconds of solving,
# far under the drift of a quartz over that span.
CLOCK_SPAN = 64

# A timestamp of the cube is written in milliseconds, a clock of the
# client counts in seconds.
MILLISECONDS = 1000.0


class CubeClock:
    """
    Where the clock of the cube stands next to the clock of the client.

    A cube stamps what it reports on a counter of its own, started when
    it was powered on and sharing no origin with anything here. Two
    clocks with no common origin still tell the same *durations*, and
    that is the whole of what is asked of them: the offset between the
    two is read as the smallest delay ever observed between a stamp and
    its arrival, and what a later arrival exceeds it by is the delay
    that move alone suffered.

    So what is measured is the **jitter** and never the latency: the
    minimum absorbs whatever the link costs every single time, and no
    reading from this side can tell a constant delay from a difference
    of origins. That constant is what ``lead`` stands for, and why it
    is a setting rather than a measurement.

    What it buys is the cadence of the fingers in place of the cadence
    of the radio: a bluetooth stack batching two moves into one packet
    hands them over at the very same instant, and the stamps the cube
    wrote are what puts them back where they happened.
    """

    def __init__(
            self,
            lead: float = MOVE_LEAD,
            ceiling: float = 0.0,
            span: int = CLOCK_SPAN,
    ) -> None:
        """
        Open a clock on a cube nothing has been heard from yet.

        Args:
            lead: What every move is aged by before anything is
                measured, in seconds.
            ceiling: The most a move may ever be aged by, in seconds,
                zero for no limit at all.
            span: How many arrivals the offset is read on.

        """
        self.lead = lead
        self.ceiling = ceiling
        self.span = span
        self.delays: deque[float] = deque(maxlen=span)

    def reset(self) -> None:
        """
        Forget the cube that was being timed.

        The offset belongs to the connection it was measured in: a cube
        that comes back has been counting all along, and a session that
        restarts may not even be the same cube. Keeping the reading
        would age every move of the new one by the drift of the old.
        """
        self.delays.clear()

    def age(self, stamp: float | None, now: float) -> float:
        """
        Tell how long ago the move carrying a stamp truly happened.

        Args:
            stamp: The clock of the cube when it reported the move, in
                milliseconds. None when it reported none, which is what
                a cube saying nothing of its own time looks like.
            now: The moment the move arrived, on the clock of the
                client, in seconds.

        Returns:
            The age of the move in seconds, never negative and never
            past the ceiling.

        """
        if stamp is None:
            return self.capped(self.lead)

        delay = now - stamp / MILLISECONDS
        self.delays.append(delay)

        return self.capped(self.lead + delay - min(self.delays))

    def capped(self, age: float) -> float:
        """
        Hold an age under what a turn can give away and stay one.

        An age reaching the beat starts the turn where it ends, and the
        face lands without ever being seen to move. It is also what a
        clock read wrong cannot get past - a cube whose counter jumped,
        a stamp from another origin - so a reading that makes no sense
        costs a snap and never a cube frozen in the future.

        Nothing holds the other end: an age is a delay measured against
        the smallest delay ever seen, so it cannot come out negative,
        and ``Viewer.push()`` answers for a lead typed below zero.

        Args:
            age: The age to hold, in seconds.

        Returns:
            The age, never past the ceiling.

        """
        if self.ceiling and age > self.ceiling:
            return self.ceiling

        return age
