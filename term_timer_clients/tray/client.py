"""What the icon says of the stream, and what a click on it does."""
import logging
from dataclasses import dataclass
from dataclasses import field

from term_timer_clients.link import CubeLink
from term_timer_clients.tray.cast import Popup

logger = logging.getLogger(__name__)

# What the bar calls this client, and how the cube is spelled out under
# it. The name is the one the window wears, written again rather than
# imported from it: reaching into the viewer for a string would drag
# cubing-algs and an OpenGL stack into a process that draws an icon.
TRAY_TITLE = 'Cubecast'

TRAY_SEPARATOR = ' · '

# What is said of a cube that has not introduced itself, and of a
# stream where there is none. The first is a real state and not a
# fallback: a session joined in the middle has a cube talking and has
# heard nothing of its name.
TRAY_CONNECTED = 'Cube connected'

TRAY_OFFLINE = 'No cube connected'

# What is said of a stream nothing has been heard from yet: the source
# is carried by every envelope, so this is a real absence rather than
# a fallback for one that failed to say it.
TRAY_NO_SOURCE = 'No source yet'

# What the menu offers, in the order it offers it. The identifiers are
# what a click comes back as, so they are written down rather than
# counted: an entry added tomorrow must not turn Quit into Show. The
# separators are numbered like the rest and **never left at zero**,
# which is the identifier of the root of the menu itself: a line
# sharing it is a line a shell is free to take for the whole menu.
TOGGLE_ITEM = 1

AUTO_ITEM = 2

FIRST_RULE_ITEM = 3

STATUS_ITEM = 4

SOURCE_ITEM = 5

SECOND_RULE_ITEM = 6

QUIT_ITEM = 7

SHOW_LABEL = 'Show the cube'

HIDE_LABEL = 'Hide the cube'

AUTO_LABEL = 'Follow the cube'

QUIT_LABEL = 'Quit'

# How long a cube that left is given before its window is taken away.
# `cube-cast` blows the cube apart when the link drops, and that blast
# is the whole of what a window has to say about a cube that is gone:
# hiding on the very message that ended the link is hiding the one
# picture worth showing. The duration lives here as a number rather
# than as an import - reaching into the viewer for it would drag
# cubing-algs and an OpenGL stack into a process that draws an icon -
# so it is written above the blast rather than on it, and nothing
# breaks the day the animation is retimed. Above it by a frame and no
# more: what exceeds the blast is a graphite core breathing in a window
# that is about to be taken away, which says nothing about the cube
# that left and delays the only thing the gesture is waited on for.
BLAST_DELAY = 0.8


@dataclass(frozen=True, slots=True)
class MenuEntry:
    """
    One line of the menu the icon drops, as a menu knows it.

    Written here rather than in the bus: what the menu offers and what
    a click on it does is the whole of the client, and the protocol
    carrying it is a translation. It is also what makes the menu
    assertable without a bus to talk to.
    """

    identifier: int
    label: str
    enabled: bool = True
    separator: bool = field(default=False, kw_only=True)

    # None and not False: a line that carries no checkbox at all is not
    # a line carrying an empty one, and what is not sent is what a
    # shell draws with its own defaults. Sending a cleared checkmark on
    # every other line would indent the whole menu behind a column of
    # nothing.
    checked: bool | None = field(default=None, kw_only=True)


class CubeTray(CubeLink):
    """
    The cube as a bar shows it: an icon, a tooltip and a menu.

    What it holds of the stream is the link every client showing a cube
    reads, and nothing else: an icon says whether there is a cube, and
    a cube is exactly what ``CubeLink`` answers for. No move is played
    here and no state is read - the window is what shows those, and it
    is a process of its own.

    Nothing here talks to a bus and nothing opens a window: the popup
    is handed over, the way a tail is handed its writer, so that what a
    click does is asserted without either. What a click does is *show*
    a window and never open one - the window is opened with the icon
    and hidden behind it, which is what makes it a window that has
    heard the whole session rather than one that starts on silence.
    """

    def __init__(self, popup: Popup, *, auto: bool = False) -> None:
        """
        Bind an icon to the window a click on it shows.

        Args:
            popup: The window shown under the icon.
            auto: Whether the window follows the cube by itself.

        """
        super().__init__()

        self.popup = popup
        self.auto = auto
        self.stopped = False

        # What the link was at the turn before, and it is held here
        # rather than read off `connected` because **what the window
        # follows is the transition and never the level**: a cube that
        # is there says so tens of times a second, and showing a window
        # on each of them is showing a window that is already up. It is
        # also what leaves a hand free between two of them - a window
        # put away by a click stays away until the cube truly comes or
        # goes.
        self.linked = False

        # When the window of a cube that left is to be taken away, zero
        # for nothing waiting. Read on the clock of whoever ticks
        # rather than on one of its own: nothing here has a thread, and
        # a delay measured by the caller is one a test can walk through
        # without waiting for it.
        self.hide_at = 0.0

    @property
    def label(self) -> str:
        """
        Tell what the icon says of the cube, in one line.

        Returns:
            The cube as it introduced itself, or the plain state of the
            link until it has.

        """
        if not self.connected:
            return TRAY_OFFLINE

        return TRAY_SEPARATOR.join(self.parts) or TRAY_CONNECTED

    @property
    def entries(self) -> list[MenuEntry]:
        """
        Write out the menu the icon drops on a right click.

        The state and the source are a footer, answering no click: what
        the window would have shown in its bar is what an icon has
        nowhere else to say, but it is read far less often than the
        gesture above it is clicked, so it trails the menu instead of
        opening it. The source is its own line rather than joining
        ``label``, which a prefixed command such as ``term-timer
        train`` would otherwise stretch past what a bar reads
        comfortably. Neither is shown at all when there is no cube to
        report on: a footer saying ``No cube connected`` would be one
        more thing to read for what the icon already says by itself.

        The following is a checkbox under the gesture rather than a
        third word in it: what it changes is who clicks that gesture
        from now on, so it belongs next to it and reads as the standing
        answer to a question the line above answers once.

        Returns:
            The lines of the menu, in the order they are shown.

        """
        entries = [
            MenuEntry(
                TOGGLE_ITEM,
                HIDE_LABEL if self.popup.shown else SHOW_LABEL,
            ),
            MenuEntry(AUTO_ITEM, AUTO_LABEL, checked=self.auto),
            MenuEntry(FIRST_RULE_ITEM, '', separator=True),
        ]

        if self.connected:
            entries += [
                MenuEntry(STATUS_ITEM, self.label, enabled=False),
                MenuEntry(
                    SOURCE_ITEM,
                    self.source or TRAY_NO_SOURCE,
                    enabled=False,
                ),
                MenuEntry(SECOND_RULE_ITEM, '', separator=True),
            ]

        entries.append(MenuEntry(QUIT_ITEM, QUIT_LABEL))

        return entries

    @property
    def state(self) -> tuple[bool, str, str, bool, bool]:
        """
        Tell everything the bar is showing, in one comparable thing.

        The icon is redrawn and the menu written again only when this
        changes: a gyroscope publishing tens of times a second would
        otherwise have the bar redrawn tens of times a second, for a
        picture that says the same thing.

        Returns:
            What the icon wears, what it says, what publishes it,
            whether the window is up, and who is putting it there.

        """
        return (
            self.connected,
            self.label,
            self.source,
            self.popup.shown,
            self.auto,
        )

    def toggle(self) -> None:
        """
        Show the window under the icon, or take away the one that is up.

        **This is the gesture of a hand, and it is the only one that
        stops the following.** Whoever asks by hand for a window is
        asking for that window rather than for the next cube, so the
        box is cleared and the icon says who is deciding from now on -
        a checkbox left ticked over a window the cube is about to take
        back is a checkbox that lied.

        Which is exactly why the automatic side never comes through
        here: it shows and hides the window itself, and a following
        that cleared its own box would last one cube.
        """
        self.auto = False
        self.hide_at = 0.0

        self.popup.toggle()

    def watch(self) -> None:
        """
        Follow the cube from now on, or stop following it.

        A box just ticked brings the window where the cube already is,
        rather than waiting for it to come or go: the cube is plugged
        in far more often than it is unplugged, and a following that
        said nothing until the next connection would be one nothing
        answered.
        """
        self.auto = not self.auto
        self.hide_at = 0.0

        if not self.auto:
            return

        if self.connected:
            self.popup.show()
        else:
            self.popup.hide()

    def follow(self, now: float) -> None:
        """
        Bring the window where the cube is, when it is being followed.

        The link is read at the turn of whoever ticks and never in the
        stream, which is the arrangement of this whole client: the
        thread reading the stream only ever writes state down, and what
        acts on it acts on its own thread. It is also what makes a
        delay a comparison rather than a timer.

        Args:
            now: What the clock of the caller stands at.

        """
        if self.connected != self.linked:
            self.linked = self.connected

            if self.auto:
                if self.connected:
                    # A cube coming back cancels the farewell of the
                    # one before it: the window is wanted now, and the
                    # blast it would have shown never happened
                    self.hide_at = 0.0
                    self.popup.show()
                else:
                    self.hide_at = now + BLAST_DELAY

        if self.hide_at and now >= self.hide_at:
            self.hide_at = 0.0

            self.popup.hide()

    def activate(self, identifier: int) -> None:
        """
        Answer a click on one line of the menu.

        An identifier this client knows nothing about is ignored rather
        than guessed at, which is what it does with a topic it does not
        know.

        Args:
            identifier: The line that was clicked.

        """
        if identifier == TOGGLE_ITEM:
            self.toggle()
        elif identifier == AUTO_ITEM:
            self.watch()
        elif identifier == QUIT_ITEM:
            self.stop()

    def stop(self) -> None:
        """Take the window down, and let the bar go."""
        logger.info('Closing the tray')

        self.popup.close()
        self.stopped = True

    def settle(self) -> bool:
        """
        Bring the icon up to date with a window that is no longer there.

        The window is put away rather than closed by its own keys, so
        one that is gone is one that crashed or that somebody took
        away: nothing is following the stream any more, and the next
        click has a window to open again.

        Returns:
            True when the window went away on its own.

        """
        if not self.popup.settle():
            return False

        logger.info('The window went away')

        return True
