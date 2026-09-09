"""The icon and its menu, as the bus of the desktop knows them."""
# **Every shape in this file is dictated by two specifications**, and
# the suppressions below are what that costs. The annotations of a
# service method are DBus signature strings and not Python types -
# 's' for a string, 'a(iiay)' for a list of pixmaps - which is where
# dbus-next reads the type of every argument, and there is nowhere
# else to write them; the `no_type_check` under each decorator says
# as much to mypy, which would read them as forward declarations. The
# arguments a method is handed are the ones the protocol sends whether
# or not there is anything to do with them, an interface answering for
# a constant holds no state to answer with, and a variant carries its
# value where it is given. None of the three is a shape this file is
# free to choose.
# ruff: file-ignore[unused-method-argument, no-self-use]
# ruff: file-ignore[boolean-positional-value-in-call]
import logging
import os
from typing import no_type_check

from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface
from dbus_next.service import dbus_property
from dbus_next.service import method
from dbus_next.service import signal
from dbus_next.signature import Variant

from term_timer_clients.tray.client import TRAY_TITLE
from term_timer_clients.tray.client import CubeTray
from term_timer_clients.tray.client import MenuEntry
from term_timer_clients.tray.icon import pixmaps

logger = logging.getLogger(__name__)

# What a tray icon is on the bus, and where this one puts itself. The
# names are the ones the specification fixed and every shell reads: an
# item at another path is an item nothing ever draws.
ITEM_INTERFACE = 'org.kde.StatusNotifierItem'

ITEM_PATH = '/StatusNotifierItem'

MENU_INTERFACE = 'com.canonical.dbusmenu'

MENU_PATH = '/MenuBar'

WATCHER_SERVICE = 'org.kde.StatusNotifierWatcher'

WATCHER_PATH = '/StatusNotifierWatcher'

# How the item is named on the bus: the interface, then the process it
# belongs to and which of its icons it is, so that two of them never
# collide.
ITEM_SERVICE = ITEM_INTERFACE

# What the item says it is: an application saying how it is doing,
# rather than something asking to be looked at now. A cube that
# connects is news, not an alarm.
ITEM_CATEGORY = 'ApplicationStatus'

ITEM_ID = 'cube-tray'

ITEM_STATUS = 'Active'

# Whether a left click is meant to drop the menu rather than reach the
# item. It says false because a click on this icon means to open the
# cube - and **on GNOME that buys nothing**: the AppIndicator extension
# never reads this property at all. It answers a plain left click by
# dropping the menu whenever there is one, and keeps `Activate` for a
# double click and `SecondaryActivate` for the middle button. It is
# said all the same, for the shells that do read it, and it is the
# whole reason the menu carries the show gesture itself: on the desktop
# this client was written for, the menu *is* the left click.
ITEM_IS_MENU = False

# The version of the menu protocol spoken, and the one thing a menu is
# read through: a shell asks for the layout and is handed a revision,
# and asks again when it hears the revision moved.
MENU_VERSION = 3

MENU_TEXT_DIRECTION = 'ltr'

MENU_STATUS = 'normal'

# The root of the menu, which is never drawn: what is drawn is its
# children, and it is the identifier a shell asks the layout for.
MENU_ROOT = 0

# What a line of the menu is made of, as a menu reads it. Everything
# else it may carry - an icon, a shortcut, a checkbox - is left out
# rather than sent empty: what is not there is what a shell draws with
# its own defaults.
LABEL_PROPERTY = 'label'

ENABLED_PROPERTY = 'enabled'

VISIBLE_PROPERTY = 'visible'

TYPE_PROPERTY = 'type'

SEPARATOR_TYPE = 'separator'

CLICKED_EVENT = 'clicked'

ICON_PIXMAP_PROPERTY = 'IconPixmap'

ICON_DESCRIPTION_PROPERTY = 'IconAccessibleDesc'

TOOLTIP_PROPERTY = 'ToolTip'


def entry_properties(entry: MenuEntry) -> dict[str, Variant]:
    """
    Write one line of the menu the way a menu carries it.

    Args:
        entry: The line, as the client describes it.

    Returns:
        The properties of the line, keyed as the protocol names them.

    """
    if entry.separator:
        return {TYPE_PROPERTY: Variant('s', SEPARATOR_TYPE)}

    return {
        LABEL_PROPERTY: Variant('s', entry.label),
        ENABLED_PROPERTY: Variant('b', entry.enabled),
        VISIBLE_PROPERTY: Variant('b', True),
    }


def selected(
        properties: dict[str, Variant],
        names: list[str],
) -> dict[str, Variant]:
    """
    Keep of a line only what was asked for.

    Args:
        properties: Everything the line carries.
        names: What the caller asked for, empty for all of it.

    Returns:
        The properties the caller wants.

    """
    if not names:
        return properties

    return {
        name: value
        for name, value in properties.items()
        if name in names
    }


class TrayItem(ServiceInterface):
    """
    The icon in the bar, as the desktop reads it off the bus.

    A translation and nothing else: what the icon wears and what a
    click does is decided by ``CubeTray``, and every method here hands
    a question to it or an answer back. That is what keeps the whole of
    the client assertable with no bus at all.
    """

    def __init__(self, tray: CubeTray) -> None:
        """
        Put a client on the bus as an icon.

        Args:
            tray: What the icon shows, and what a click reaches.

        """
        super().__init__(ITEM_INTERFACE)

        self.tray = tray

    @dbus_property(access=PropertyAccess.READ, name='Category')
    @no_type_check
    def category(self) -> 's':
        """
        Tell what kind of icon this is.

        Returns:
            The category, as the specification names it.

        """
        return ITEM_CATEGORY

    @dbus_property(access=PropertyAccess.READ, name='Id')
    @no_type_check
    def identifier(self) -> 's':
        """
        Tell what this icon is, across restarts of the bar.

        Returns:
            The identifier of the client.

        """
        return ITEM_ID

    @dbus_property(access=PropertyAccess.READ, name='Title')
    @no_type_check
    def title(self) -> 's':
        """
        Tell what this icon is called.

        Returns:
            The name of the client.

        """
        return TRAY_TITLE

    @dbus_property(access=PropertyAccess.READ, name='Status')
    @no_type_check
    def status(self) -> 's':
        """
        Tell how much the icon is asking to be looked at.

        Returns:
            Always active: a cube that comes and goes is news, and
            never an alarm.

        """
        return ITEM_STATUS

    @dbus_property(access=PropertyAccess.READ, name='IconName')
    @no_type_check
    def icon_name(self) -> 's':
        """
        Tell what icon of the theme is worn.

        Returns:
            None of them: the icon is drawn here, no theme having ever
            carried a cube.

        """
        return ''

    @dbus_property(access=PropertyAccess.READ, name='IconPixmap')
    @no_type_check
    def icon_pixmap(self) -> 'a(iiay)':
        """
        Hand over the icon itself, drawn for the state of the link.

        Returns:
            The icon at every size it was drawn in, smallest first.

        """
        return [
            [width, height, pixels]
            for width, height, pixels in pixmaps(
                connected=self.tray.connected,
            )
        ]

    @dbus_property(access=PropertyAccess.READ, name='IconAccessibleDesc')
    @no_type_check
    def icon_description(self) -> 's':
        """
        Tell what is read out loud in the place of the icon.

        **Outside the specification and answered all the same**, and
        that is the whole of why it is here: the AppIndicator extension
        asks for it after every `NewIcon`, and a property an interface
        does not carry is an error on the bus - one the extension
        swallows and one dbus-next writes a traceback for, so an icon
        redrawn by a gyroscope fills a terminal instead of a bar.
        Saying it costs three lines and buys the name a screen reader
        reads.

        Returns:
            What the icon says of the cube, which is what there is to
            read out of a picture of one.

        """
        return self.tray.label

    @dbus_property(access=PropertyAccess.READ, name='AttentionIconName')
    @no_type_check
    def attention_icon_name(self) -> 's':
        """
        Tell what is worn when the icon asks to be looked at.

        Returns:
            Nothing: this icon never asks.

        """
        return ''

    @dbus_property(access=PropertyAccess.READ, name='AttentionAccessibleDesc')
    @no_type_check
    def attention_description(self) -> 's':
        """
        Tell what is read out when the icon asks to be looked at.

        Answered for the same reason as `IconAccessibleDesc`, and said
        empty for the same reason as `AttentionIconName`.

        Returns:
            Nothing: this icon never asks.

        """
        return ''

    @dbus_property(access=PropertyAccess.READ, name='OverlayIconName')
    @no_type_check
    def overlay_icon_name(self) -> 's':
        """
        Tell what is drawn on top of the icon.

        Returns:
            Nothing: what there is to say is said by the cube itself.

        """
        return ''

    @dbus_property(access=PropertyAccess.READ, name='ToolTip')
    @no_type_check
    def tooltip(self) -> '(sa(iiay)ss)':
        """
        Tell what is written when the icon is hovered.

        Returns:
            The name of the client, and the cube under it.

        """
        return ['', [], TRAY_TITLE, self.tray.label]

    @dbus_property(access=PropertyAccess.READ, name='ItemIsMenu')
    @no_type_check
    def item_is_menu(self) -> 'b':
        """
        Tell whether a left click is meant to drop the menu.

        Returns:
            False: a click opens the cube, the menu being what the
            other button is for.

        """
        return ITEM_IS_MENU

    @dbus_property(access=PropertyAccess.READ, name='Menu')
    @no_type_check
    def menu(self) -> 'o':
        """
        Tell where the menu of this icon is to be found.

        Returns:
            The path the menu is exported at.

        """
        return MENU_PATH

    @method(name='Activate')
    @no_type_check
    def activate(self, x: 'i', y: 'i') -> None:
        """
        Answer a click on the icon.

        Args:
            x: Where the click landed, which nothing here reads: the
                window is placed by the compositor, no shell telling
                anybody where it drew the icon.
            y: The other half of the same unread answer.

        """
        self.tray.toggle()

    @method(name='SecondaryActivate')
    @no_type_check
    def secondary_activate(self, x: 'i', y: 'i') -> None:
        """
        Answer a middle click on the icon, as a left one.

        Args:
            x: Where the click landed, unread.
            y: Where the click landed, unread.

        """
        self.tray.toggle()

    @method(name='Scroll')
    @no_type_check
    def scroll(self, delta: 'i', orientation: 's') -> None:
        """
        Answer the wheel over the icon, by doing nothing.

        A cube has nothing to be scrolled through, and a window that
        opened on a stray wheel would be one nobody asked for.

        Args:
            delta: How far the wheel was turned.
            orientation: Which way it was turned.

        """

    @signal(name='NewIcon')
    @no_type_check
    def new_icon(self) -> None:
        """Tell the bar the icon is not the one it is showing."""

    @signal(name='NewToolTip')
    @no_type_check
    def new_tooltip(self) -> None:
        """Tell the bar what is written under the icon has changed."""

    def refresh(self) -> None:
        """
        Say the cube behind the icon is not the one it was.

        Both are sent, and they are two because shells read two things:
        the signals of the item are what the specification defines, and
        the properties that changed are what a shell caching them - and
        they all cache them - reads instead. Sending one alone leaves
        the icon of a cube that left in the bar of somebody.
        """
        self.new_icon()
        self.new_tooltip()

        self.emit_properties_changed({
            ICON_PIXMAP_PROPERTY: self.icon_pixmap,
            ICON_DESCRIPTION_PROPERTY: self.icon_description,
            TOOLTIP_PROPERTY: self.tooltip,
        })


class TrayMenu(ServiceInterface):
    """
    The menu the icon drops, as the bus carries it.

    The lines are asked of ``CubeTray`` every time they are handed
    over: a menu is read at the moment it opens, and one built once
    would offer to show a window that is already up.
    """

    def __init__(self, tray: CubeTray) -> None:
        """
        Put the menu of a client on the bus.

        Args:
            tray: What the menu offers, and what a click reaches.

        """
        super().__init__(MENU_INTERFACE)

        self.tray = tray
        self.revision = 1

    @dbus_property(access=PropertyAccess.READ, name='Version')
    @no_type_check
    def version(self) -> 'u':
        """
        Tell what version of the menu protocol is spoken.

        Returns:
            The version this menu is written against.

        """
        return MENU_VERSION

    @dbus_property(access=PropertyAccess.READ, name='TextDirection')
    @no_type_check
    def text_direction(self) -> 's':
        """
        Tell which way the labels are read.

        Returns:
            Left to right.

        """
        return MENU_TEXT_DIRECTION

    @dbus_property(access=PropertyAccess.READ, name='Status')
    @no_type_check
    def status(self) -> 's':
        """
        Tell how the menu is to be drawn.

        Returns:
            Plainly.

        """
        return MENU_STATUS

    @dbus_property(access=PropertyAccess.READ, name='IconThemePath')
    @no_type_check
    def icon_theme_path(self) -> 'as':
        """
        Tell where the icons of the menu are to be found.

        Returns:
            Nowhere: this menu is words and nothing else.

        """
        return []

    @method(name='GetLayout')
    @no_type_check
    def get_layout(
            self, parent: 'i', depth: 'i', names: 'as',
    ) -> 'u(ia{sv}av)':
        """
        Hand over the menu, as it stands at this very moment.

        Args:
            parent: The line the layout is asked under, the root being
                the only one this menu has.
            depth: How far down it is asked for, which changes nothing
                on a menu one line deep.
            names: The properties asked for, empty for all of them.

        Returns:
            The revision of the menu, and the root with its lines.

        """
        children = [
            Variant(
                '(ia{sv}av)',
                [
                    entry.identifier,
                    selected(entry_properties(entry), names),
                    [],
                ],
            )
            for entry in self.tray.entries
        ]

        return [self.revision, [MENU_ROOT, {}, children]]

    @method(name='GetGroupProperties')
    @no_type_check
    def get_group_properties(
            self, ids: 'ai', names: 'as',
    ) -> 'a(ia{sv})':
        """
        Hand over what several lines of the menu carry.

        Args:
            ids: The lines asked about, empty for all of them.
            names: The properties asked for, empty for all of them.

        Returns:
            Each line asked about, and what it carries.

        """
        return [
            [entry.identifier, selected(entry_properties(entry), names)]
            for entry in self.tray.entries
            if not ids or entry.identifier in ids
        ]

    @method(name='GetProperty')
    @no_type_check
    def get_property(self, identifier: 'i', name: 's') -> 'v':
        """
        Hand over one property of one line of the menu.

        Args:
            identifier: The line asked about.
            name: The property asked for.

        Returns:
            What the line carries under that name, an empty string when
            it carries nothing.

        """
        for entry in self.tray.entries:
            if entry.identifier == identifier:
                found = entry_properties(entry).get(name)

                if found is not None:
                    return found

        return Variant('s', '')

    @method(name='Event')
    @no_type_check
    def event(
            self, identifier: 'i', event: 's', data: 'v', timestamp: 'u',
    ) -> None:
        """
        Answer a click on one line of the menu.

        Args:
            identifier: The line that was clicked.
            event: What happened to it, only a click being acted on.
            data: What came with it, which a click carries nothing of.
            timestamp: When it happened, which changes nothing here.

        """
        if event != CLICKED_EVENT:
            return

        self.tray.activate(identifier)

    @method(name='EventGroup')
    @no_type_check
    def event_group(self, events: 'a(isvu)') -> 'ai':
        """
        Answer several clicks at once.

        Args:
            events: The clicks, each as one line, what happened to it,
                what came with it and when.

        Returns:
            The lines nothing was done about, none of them here: a menu
            this short answers for every line it offers.

        """
        for identifier, event, _data, _timestamp in events:
            if event == CLICKED_EVENT:
                self.tray.activate(identifier)

        return []

    @method(name='AboutToShow')
    @no_type_check
    def about_to_show(self, identifier: 'i') -> 'b':
        """
        Answer a menu that is about to be drawn.

        The menu is always said to have moved, and it is not a lie
        worth avoiding: what the lines say depends on a window that may
        have closed itself a moment ago, and a shell reading the layout
        again costs one call at the very moment somebody is opening a
        menu by hand.

        Args:
            identifier: The line about to be shown.

        Returns:
            True: read the layout again before drawing it.

        """
        return True

    @method(name='AboutToShowGroup')
    @no_type_check
    def about_to_show_group(self, ids: 'ai') -> 'aiai':
        """
        Answer several menus that are about to be drawn.

        Two answers and not one pair: the protocol declares two out
        arguments here, where ``GetLayout`` declares a structure, and a
        client reading a structure off two arguments reads neither.

        Args:
            ids: The lines about to be shown.

        Returns:
            The lines that moved, and the ones that could not be found.

        """
        return [list(ids), []]

    @signal(name='LayoutUpdated')
    @no_type_check
    def layout_updated(self, revision: 'u', parent: 'i') -> 'ui':
        """
        Tell the bar the menu is not the one it is showing.

        Args:
            revision: What the menu now stands at.
            parent: The line the change is under.

        Returns:
            The two of them, as the signal carries them.

        """
        return [revision, parent]

    @signal(name='ItemsPropertiesUpdated')
    @no_type_check
    def items_properties_updated(
            self, updated: 'a(ia{sv})', removed: 'a(ias)',
    ) -> 'a(ia{sv})a(ias)':
        """
        Hand the bar the words the lines of the menu now say.

        Args:
            updated: The lines that moved, and what they now carry.
            removed: The lines that lost a property, and which.

        Returns:
            The two of them, as the signal carries them.

        """
        return [updated, removed]

    def refresh(self) -> None:
        """
        Say the menu moved, and say what it now says.

        **The words are sent and not merely the revision**, because a
        revision is answered by asking for the layout again and the
        layout is not where a shell reads a label: the tray of GNOME
        asks it for the shape of the menu alone - the types of the
        lines - and takes their words from the properties it was last
        handed. A menu announced by its revision only is one that goes
        on offering to show a window that is already up.

        Both are sent all the same. They answer two different changes -
        the lines a menu is made of, and what those lines say - and a
        shell is free to have read either of them.
        """
        self.revision += 1

        self.items_properties_updated(
            [
                [entry.identifier, entry_properties(entry)]
                for entry in self.tray.entries
            ],
            [],
        )

        self.layout_updated(self.revision, MENU_ROOT)


def item_service(number: int = 1) -> str:
    """
    Name the item on the bus, as the specification asks it to be named.

    Args:
        number: Which icon of this process it is.

    Returns:
        The name to ask the bus for.

    """
    return f'{ ITEM_SERVICE }-{ os.getpid() }-{ number }'
