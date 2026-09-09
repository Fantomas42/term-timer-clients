"""
Tests for the ``cube-tray`` client, on a bus of its own.

**Nothing here ever touches the bus of the desktop.** A session bus is
started for the suite and torn down with it, so the icon is registered,
read and clicked on a bus nothing else is listening to: a shell asked
to draw an item that a test is about to take away is a shell waiting on
a service that will not answer, and a shell waiting is a desktop that
has stopped. That is also what these tests are for - the two service
interfaces are a translation, and this is where the translation is read
back the way a shell would read it.

The suite skips itself where there is no ``dbus-daemon`` to start.
"""
import asyncio
import os
import select
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import unittest
from typing import Any
from typing import no_type_check
from unittest.mock import patch

from dbus_next.constants import MessageFlag
from dbus_next.constants import MessageType
from dbus_next.message import Message
from dbus_next.service import ServiceInterface
from dbus_next.service import method
from dbus_next.signature import Variant

from term_timer_clients.tests.fixtures import envelope
from term_timer_clients.tests.test_tray import StubPopup
from term_timer_clients.tray import main as entry
from term_timer_clients.tray.bus import ADD_MATCH_MEMBER
from term_timer_clients.tray.bus import DBUS_INTERFACE
from term_timer_clients.tray.bus import DBUS_PATH
from term_timer_clients.tray.bus import DBUS_SERVICE
from term_timer_clients.tray.bus import BusError
from term_timer_clients.tray.bus import call
from term_timer_clients.tray.bus import close_bus
from term_timer_clients.tray.bus import follow_watcher
from term_timer_clients.tray.bus import open_bus
from term_timer_clients.tray.bus import publish
from term_timer_clients.tray.bus import register
from term_timer_clients.tray.client import HIDE_LABEL
from term_timer_clients.tray.client import SHOW_LABEL
from term_timer_clients.tray.client import STATUS_ITEM
from term_timer_clients.tray.client import TOGGLE_ITEM
from term_timer_clients.tray.client import TRAY_CONNECTED
from term_timer_clients.tray.client import TRAY_OFFLINE
from term_timer_clients.tray.client import TRAY_TITLE
from term_timer_clients.tray.client import CubeTray
from term_timer_clients.tray.item import CLICKED_EVENT
from term_timer_clients.tray.item import ITEM_ID
from term_timer_clients.tray.item import ITEM_INTERFACE
from term_timer_clients.tray.item import ITEM_PATH
from term_timer_clients.tray.item import LABEL_PROPERTY
from term_timer_clients.tray.item import MENU_INTERFACE
from term_timer_clients.tray.item import MENU_PATH
from term_timer_clients.tray.item import MENU_ROOT
from term_timer_clients.tray.item import TYPE_PROPERTY
from term_timer_clients.tray.item import WATCHER_PATH
from term_timer_clients.tray.item import WATCHER_SERVICE
from term_timer_clients.tray.item import TrayItem
from term_timer_clients.tray.item import TrayMenu

DAEMON = 'dbus-daemon'

BUS_VARIABLE = 'DBUS_SESSION_BUS_ADDRESS'

# How long the daemon is given to say where it is listening. It writes
# the address before anything else, so this is only ever the wait of a
# daemon that is not going to start at all.
DAEMON_TIMEOUT = 5.0

PROPERTIES_INTERFACE = 'org.freedesktop.DBus.Properties'

GET_MEMBER = 'Get'

# How many lines the menu offers, and where the one that is clicked
# stands. The suite asserts on the layout as a shell reads it, so it
# counts what a shell would draw.
MENU_LINES = 5

REGISTER_MEMBER = 'RegisterStatusNotifierItem'

# How long a round of the loop is waited for, and how many of them.
# What is waited on is the bus having gone round, never a call of a
# test: a wait that is too short fails on a slow machine, and one that
# is too long is a suite nobody runs.
ROUND = 0.05

ROUNDS = 40


class StubWatcher(ServiceInterface):
    """
    The tray of a desktop, as far as an icon registering can tell.

    One method and the name it answers on: what an icon asks of a
    desktop is to be shown, and what it hears back is that it was.
    """

    def __init__(self) -> None:
        """Start on a tray nothing has registered with."""
        super().__init__(WATCHER_SERVICE)

        self.registered: list[str] = []

    @method(name=REGISTER_MEMBER)
    @no_type_check
    def register_item(
            self, service: 's',  # ruff: ignore[undefined-name]
    ) -> None:
        """
        Take note of an icon asking to be shown.

        Args:
            service: The name the icon answers to.

        """
        self.registered.append(service)


async def settled(watcher: 'StubWatcher') -> None:
    """
    Wait for an icon to have registered with the tray.

    Nothing is awaited on its own: what registers is a handler the bus
    calls, so what is waited for is a round of the loop rather than a
    call this suite made.

    Args:
        watcher: The tray the icon is to register with.

    """
    for _ in range(ROUNDS):
        await asyncio.sleep(ROUND)

        if watcher.registered:
            return


def start_daemon() -> tuple[subprocess.Popen[str], str]:
    """
    Start a session bus of this suite's own.

    Returns:
        The daemon, and the address it listens on.

    Raises:
        RuntimeError: When it says nothing in the time it is given.

    """
    daemon = subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]
        [DAEMON, '--session', '--print-address', '--nofork'],
        stdout=subprocess.PIPE,
        text=True,
    )

    output = daemon.stdout
    msg = 'the private bus said nothing'

    if output is None:
        stop_daemon(daemon)
        raise RuntimeError(msg)

    # Read with a timeout rather than plainly: a daemon that starts and
    # says nothing would otherwise hold the whole suite forever, which
    # is the one thing a test of a desktop service may not do.
    readable, _, _ = select.select([output], [], [], DAEMON_TIMEOUT)

    if not readable:
        stop_daemon(daemon)
        raise RuntimeError(msg)

    return daemon, output.readline().strip()


def stop_daemon(daemon: subprocess.Popen[str]) -> None:
    """
    Take the private bus down, whatever state it is in.

    Args:
        daemon: The daemon to stop.

    """
    daemon.terminate()

    try:
        daemon.wait(timeout=DAEMON_TIMEOUT)
    except subprocess.TimeoutExpired:
        daemon.kill()
        daemon.wait()

    if daemon.stdout is not None:
        daemon.stdout.close()


@unittest.skipUnless(shutil.which(DAEMON), 'no dbus-daemon to run a bus on')
class BusTestCase(unittest.IsolatedAsyncioTestCase):
    """Base case holding a bus of its own, and nothing on it yet."""

    daemon: subprocess.Popen[str]

    @classmethod
    def setUpClass(cls) -> None:
        """Start the private bus, and point every client at it."""
        daemon, address = start_daemon()

        cls.daemon = daemon
        cls.addClassCleanup(stop_daemon, daemon)

        environment = patch.dict(os.environ, {BUS_VARIABLE: address})
        environment.start()
        cls.addClassCleanup(environment.stop)

    async def asyncSetUp(self) -> None:
        """Open both ends of the private bus."""
        self.popup = StubPopup()
        self.tray = CubeTray(self.popup)

        self.bus = await open_bus()
        self.client = await open_bus()

    async def asyncTearDown(self) -> None:
        """Give both ends of the bus back."""
        close_bus(self.client)
        close_bus(self.bus)

    async def show_tray(self) -> StubWatcher:
        """
        Put a tray of a desktop on the bus, for an icon to find.

        Returns:
            The tray, holding what registered with it.

        """
        watcher = StubWatcher()

        self.client.export(WATCHER_PATH, watcher)
        await self.client.request_name(WATCHER_SERVICE)

        return watcher

    async def catch(self, path: str, interface: str) -> list[Message]:
        """
        Collect the signals an interface sends, as they arrive.

        Args:
            path: What is watched.
            interface: The interface its signals are sent under.

        Returns:
            The signals, filled in as the bus carries them.

        """
        caught: list[Message] = []

        def collect(message: Message) -> None:
            if (
                    message.message_type == MessageType.SIGNAL
                    and message.path == path
                    and message.interface == interface
            ):
                caught.append(message)

        await call(
            self.client,
            Message(
                destination=DBUS_SERVICE,
                path=DBUS_PATH,
                interface=DBUS_INTERFACE,
                member=ADD_MATCH_MEMBER,
                signature='s',
                body=[
                    (
                        f"type='signal',path='{ path }',"
                        f"interface='{ interface }'"
                    ),
                ],
            ),
        )

        self.client.add_message_handler(collect)
        self.addCleanup(self.client.remove_message_handler, collect)

        return caught

    async def sent(self, caught: list[Message], member: str) -> Message:
        """
        Wait for one signal to have been sent, and hand it over.

        Args:
            caught: Where the signals are collected.
            member: The one that is waited for.

        Returns:
            The signal.

        """
        for _ in range(ROUNDS):
            await asyncio.sleep(ROUND)

            for message in caught:
                if message.member == member:
                    return message

        # `fail()` never returns, and ruff reads it as a call like any
        # other: the raise is what says so on the line itself.
        msg = f'{ member } was never sent'
        raise self.failureException(msg)


class ItemTestCase(BusTestCase):
    """Base case holding an icon exported on a bus of its own."""

    async def asyncSetUp(self) -> None:
        """Put an icon and its menu on the private bus."""
        await super().asyncSetUp()

        self.item = TrayItem(self.tray)
        self.menu = TrayMenu(self.tray)

        self.service = await publish(self.bus, self.item, self.menu)

    async def ask(
            self,
            path: str,
            interface: str,
            member: str,
            signature: str = '',
            body: list[Any] | None = None,
    ) -> list[Any]:
        """
        Ask the icon something, the way a shell asks it.

        Args:
            path: What is being asked.
            interface: Under which interface.
            member: The method or the property.
            signature: What the arguments are.
            body: The arguments themselves.

        Returns:
            What came back.

        """
        reply = await self.client.call(
            Message(
                destination=self.service,
                path=path,
                interface=interface,
                member=member,
                signature=signature,
                body=body if body is not None else [],
            ),
        )

        if reply is None:
            self.fail(f'nothing answered { member }')

        self.assertIsNone(reply.error_name, reply.body)

        return list(reply.body)

    async def read(self, path: str, interface: str, name: str) -> Any:  # ruff: ignore[any-type]
        """
        Read one property of the icon, as a shell reads it.

        Args:
            path: What carries the property.
            interface: Under which interface.
            name: The property itself.

        Returns:
            The value, out of the variant it travelled in.

        """
        body = await self.ask(
            path,
            PROPERTIES_INTERFACE,
            GET_MEMBER,
            'ss',
            [interface, name],
        )

        return body[0].value


class ItemPropertiesTestCase(ItemTestCase):
    """What a shell reads off the icon before drawing it."""

    async def test_the_icon_names_itself(self) -> None:
        """A shell tells icons apart by what they call themselves."""
        self.assertEqual(
            await self.read(ITEM_PATH, ITEM_INTERFACE, 'Id'),
            ITEM_ID,
        )
        self.assertEqual(
            await self.read(ITEM_PATH, ITEM_INTERFACE, 'Title'),
            TRAY_TITLE,
        )

    async def test_the_icon_points_at_its_menu(self) -> None:
        """A menu nobody can find is a menu nobody opens."""
        self.assertEqual(
            await self.read(ITEM_PATH, ITEM_INTERFACE, 'Menu'),
            MENU_PATH,
        )

    async def test_a_click_is_meant_for_the_cube(self) -> None:
        """The menu is what the other button is for."""
        self.assertFalse(
            await self.read(ITEM_PATH, ITEM_INTERFACE, 'ItemIsMenu'),
        )

    async def test_the_icon_is_drawn_and_not_named(self) -> None:
        """No theme has ever carried a cube."""
        self.assertEqual(
            await self.read(ITEM_PATH, ITEM_INTERFACE, 'IconName'),
            '',
        )

        pixmaps = await self.read(ITEM_PATH, ITEM_INTERFACE, 'IconPixmap')

        for width, height, pixels in pixmaps:
            with self.subTest(width=width):
                self.assertEqual(len(pixels), width * height * 4)

    async def test_the_icon_follows_the_cube(self) -> None:
        """The one thing an icon in a bar is there to say."""
        away = await self.read(ITEM_PATH, ITEM_INTERFACE, 'IconPixmap')

        self.tray.dispatch(
            {'v': 1, 'sid': 'a', 'topic': 'cube.move', 'data': {'move': 'R'}},
        )

        self.assertNotEqual(
            await self.read(ITEM_PATH, ITEM_INTERFACE, 'IconPixmap'),
            away,
        )

    async def test_the_icon_is_read_out_as_the_cube(self) -> None:
        """
        A property outside the specification, answered all the same.

        The AppIndicator extension asks for it after every `NewIcon`,
        and an interface that does not carry it answers an error on the
        bus: a traceback per redraw on this side, and an icon with no
        name to read out on the other.
        """
        self.assertEqual(
            await self.read(ITEM_PATH, ITEM_INTERFACE, 'IconAccessibleDesc'),
            TRAY_OFFLINE,
        )
        self.assertEqual(
            await self.read(
                ITEM_PATH, ITEM_INTERFACE, 'AttentionAccessibleDesc',
            ),
            '',
        )

    async def test_the_tooltip_says_what_the_cube_is(self) -> None:
        """What a window writes in its bar, an icon says on hover."""
        _name, _pixmaps, title, description = await self.read(
            ITEM_PATH, ITEM_INTERFACE, 'ToolTip',
        )

        self.assertEqual(title, TRAY_TITLE)
        self.assertEqual(description, TRAY_OFFLINE)


class ItemClickTestCase(ItemTestCase):
    """What a click on the icon reaches."""

    async def test_a_click_opens_the_cube(self) -> None:
        """The whole of what the icon is clicked for."""
        await self.ask(ITEM_PATH, ITEM_INTERFACE, 'Activate', 'ii', [0, 0])

        self.assertEqual(self.popup.opened, 1)

    async def test_a_middle_click_opens_it_too(self) -> None:
        """The same gesture, wherever a shell sends it."""
        await self.ask(
            ITEM_PATH, ITEM_INTERFACE, 'SecondaryActivate', 'ii', [0, 0],
        )

        self.assertEqual(self.popup.opened, 1)

    async def test_the_wheel_opens_nothing(self) -> None:
        """A window opened on a stray wheel is one nobody asked for."""
        await self.ask(
            ITEM_PATH, ITEM_INTERFACE, 'Scroll', 'is', [1, 'vertical'],
        )

        self.assertEqual(self.popup.opened, 0)

    async def test_the_bar_is_told_the_cube_moved(self) -> None:
        """A shell that cached the icon has to hear it is stale."""
        self.item.refresh()

        self.assertEqual(
            await self.read(ITEM_PATH, ITEM_INTERFACE, 'Id'),
            ITEM_ID,
        )


class MenuLayoutTestCase(ItemTestCase):
    """The menu as a shell reads it off the bus."""

    async def layout(self) -> list[Any]:
        """
        Ask for the menu the way a shell asks for it.

        Returns:
            The lines of the menu, as they were sent.

        """
        _revision, root = await self.ask(
            MENU_PATH, MENU_INTERFACE, 'GetLayout', 'iias',
            [MENU_ROOT, -1, []],
        )

        identifier, _properties, children = root

        self.assertEqual(identifier, MENU_ROOT)

        return list(children)

    async def test_the_menu_travels_whole(self) -> None:
        """The one shape in this client the bus has to carry nested."""
        self.assertEqual(len(await self.layout()), MENU_LINES)

    async def test_the_lines_say_what_they_offer(self) -> None:
        """A shell draws the labels and nothing else."""
        children = await self.layout()

        _identifier, properties, _grandchildren = children[2].value

        self.assertEqual(properties[LABEL_PROPERTY].value, SHOW_LABEL)

    async def test_the_state_of_the_cube_heads_the_menu(self) -> None:
        """What an icon has nowhere else to say."""
        children = await self.layout()

        _identifier, properties, _grandchildren = children[0].value

        self.assertEqual(properties[LABEL_PROPERTY].value, TRAY_OFFLINE)

    async def test_the_menu_is_read_again_before_it_is_drawn(self) -> None:
        """What the lines say depends on a window that may have closed."""
        body = await self.ask(
            MENU_PATH, MENU_INTERFACE, 'AboutToShow', 'i', [MENU_ROOT],
        )

        self.assertTrue(body[0])

    async def test_several_menus_are_answered_at_once(self) -> None:
        """A shell asking about a group is answered about the group."""
        moved, gone = await self.ask(
            MENU_PATH, MENU_INTERFACE, 'AboutToShowGroup', 'ai',
            [[TOGGLE_ITEM]],
        )

        self.assertEqual(moved, [TOGGLE_ITEM])
        self.assertEqual(gone, [])

    async def test_one_line_is_read_on_its_own(self) -> None:
        """A shell is free to ask about one property of one line."""
        body = await self.ask(
            MENU_PATH, MENU_INTERFACE, 'GetProperty', 'is',
            [TOGGLE_ITEM, LABEL_PROPERTY],
        )

        self.assertEqual(body[0].value, SHOW_LABEL)

    async def test_a_property_a_line_does_not_carry_is_nothing(self) -> None:
        """A line is asked about what it has, and what it has not."""
        body = await self.ask(
            MENU_PATH, MENU_INTERFACE, 'GetProperty', 'is',
            [STATUS_ITEM, TYPE_PROPERTY],
        )

        self.assertEqual(body[0].value, '')

    async def test_a_line_that_is_not_there_carries_nothing(self) -> None:
        """What a client does not know, it does not invent."""
        body = await self.ask(
            MENU_PATH, MENU_INTERFACE, 'GetProperty', 'is',
            [404, LABEL_PROPERTY],
        )

        self.assertEqual(body[0].value, '')

    async def test_the_lines_are_handed_over_as_a_group(self) -> None:
        """How a shell reads a whole menu it already has the shape of."""
        body = await self.ask(
            MENU_PATH, MENU_INTERFACE, 'GetGroupProperties', 'aias',
            [[], []],
        )

        self.assertEqual(len(body[0]), MENU_LINES)

    async def test_the_menu_says_when_it_moved(self) -> None:
        """A revision that never moves is a menu never read again."""
        before = self.menu.revision

        self.menu.refresh()

        self.assertGreater(self.menu.revision, before)


class MenuClickTestCase(ItemTestCase):
    """What a click on a line of the menu reaches."""

    async def click(self, identifier: int, event: str = CLICKED_EVENT) -> None:
        """
        Click one line of the menu, the way a shell reports it.

        Args:
            identifier: The line that was clicked.
            event: What happened to it.

        """
        await self.ask(
            MENU_PATH, MENU_INTERFACE, 'Event', 'isvu',
            [identifier, event, Variant('s', ''), 0],
        )

    async def test_the_menu_opens_the_cube(self) -> None:
        """Some shells never send a plain click on the icon."""
        await self.click(TOGGLE_ITEM)

        self.assertEqual(self.popup.opened, 1)

    async def test_only_a_click_is_acted_on(self) -> None:
        """A menu merely opening under the cursor opens no window."""
        await self.click(TOGGLE_ITEM, 'opened')

        self.assertEqual(self.popup.opened, 0)

    async def test_several_clicks_are_answered_at_once(self) -> None:
        """A shell batching two clicks is answered for the two."""
        await self.ask(
            MENU_PATH, MENU_INTERFACE, 'EventGroup', 'a(isvu)',
            [[[TOGGLE_ITEM, CLICKED_EVENT, Variant('s', ''), 0]]],
        )

        self.assertEqual(self.popup.opened, 1)

    async def test_a_batch_of_what_is_not_a_click_opens_nothing(
            self,
    ) -> None:
        """What is batched with a click is read like a click is."""
        await self.ask(
            MENU_PATH, MENU_INTERFACE, 'EventGroup', 'a(isvu)',
            [[[TOGGLE_ITEM, 'hovered', Variant('s', ''), 0]]],
        )

        self.assertEqual(self.popup.opened, 0)


class SignalTestCase(ItemTestCase):
    """
    How a shell is told the icon is not the one it is showing.

    **A shell caches everything it read**, and what it re-reads on its
    own is decided by the signal it hears rather than by this client:
    the tray of GNOME never asks the layout for a label again, so a
    menu announced by its revision alone is a menu that stays on the
    words it was first drawn with.
    """

    async def test_a_shell_is_told_the_icon_changed(self) -> None:
        """The picture of the cube, and the words under it."""
        caught = await self.catch(ITEM_PATH, ITEM_INTERFACE)

        self.item.refresh()

        await self.sent(caught, 'NewIcon')
        await self.sent(caught, 'NewToolTip')

    async def test_a_shell_is_handed_the_properties_that_moved(
            self,
    ) -> None:
        """A signal saying so and nothing else leaves the icon stale."""
        caught = await self.catch(ITEM_PATH, PROPERTIES_INTERFACE)

        self.item.refresh()

        signal = await self.sent(caught, 'PropertiesChanged')
        _interface, changed, _invalidated = signal.body

        self.assertIn('IconPixmap', changed)
        self.assertIn('IconAccessibleDesc', changed)
        self.assertIn('ToolTip', changed)

    async def test_a_shell_is_told_the_menu_moved(self) -> None:
        """A revision that never moves is a menu never read again."""
        caught = await self.catch(MENU_PATH, MENU_INTERFACE)

        self.menu.refresh()

        signal = await self.sent(caught, 'LayoutUpdated')
        revision, parent = signal.body

        self.assertEqual(revision, self.menu.revision)
        self.assertEqual(parent, MENU_ROOT)

    async def test_a_shell_is_handed_the_words_the_menu_now_says(
            self,
    ) -> None:
        """
        The labels themselves, and not merely that they changed.

        The tray of GNOME asks the layout for the shape of the menu
        and never for its words: what it draws is what it was handed
        the last time properties were sent to it, so a menu that only
        ever bumps its revision goes on offering to show a window that
        is already up.
        """
        caught = await self.catch(MENU_PATH, MENU_INTERFACE)

        self.tray.toggle()
        self.menu.refresh()

        signal = await self.sent(caught, 'ItemsPropertiesUpdated')
        changed, _removed = signal.body

        said = {
            identifier: properties[LABEL_PROPERTY].value
            for identifier, properties in changed
            if LABEL_PROPERTY in properties
        }

        self.assertEqual(said[TOGGLE_ITEM], HIDE_LABEL)
        self.assertEqual(said[STATUS_ITEM], TRAY_OFFLINE)


class AskingTestCase(ItemTestCase):
    """What comes back when nothing does."""

    async def test_a_question_nobody_answers_is_an_error(self) -> None:
        """A caller left waiting on a reply that will not come."""
        message = Message(
            destination=self.service,
            path=ITEM_PATH,
            interface=ITEM_INTERFACE,
            member='Activate',
            signature='ii',
            body=[0, 0],
            flags=MessageFlag.NO_REPLY_EXPECTED,
        )

        with self.assertRaises(BusError):
            await call(self.client, message)


class RegistrationTestCase(ItemTestCase):
    """How an icon gets itself shown, and stays shown."""

    async def test_an_icon_asks_the_tray_to_show_it(self) -> None:
        """The one thing an icon ever asks of a desktop."""
        watcher = await self.show_tray()

        await register(self.bus, self.service)

        self.assertEqual(watcher.registered, [self.service])

    async def test_a_desktop_with_no_tray_says_so(self) -> None:
        """A client with nowhere to be shown stops rather than waits."""
        with self.assertRaises(BusError):
            await register(self.bus, self.service)

    async def test_a_tray_coming_back_is_registered_with_again(self) -> None:
        """A shell that restarts remembers no icon at all."""
        await follow_watcher(self.bus, self.service)

        watcher = await self.show_tray()
        await settled(watcher)

        self.assertEqual(watcher.registered, [self.service])

    async def test_a_tray_going_away_is_not_a_tray_to_register_with(
            self,
    ) -> None:
        """A shell on its way out is nothing an icon can do about."""
        watcher = await self.show_tray()

        await follow_watcher(self.bus, self.service)
        await self.client.release_name(WATCHER_SERVICE)

        # A few rounds and no more: what is asserted is that nothing
        # happened, and nothing never arrives.
        await asyncio.sleep(ROUND * 4)

        self.assertEqual(watcher.registered, [])


class ServeTestCase(BusTestCase):
    """The loop that shows the icon and keeps it up to date."""

    async def serving(self) -> asyncio.Task[None]:
        """
        Show the icon the way the entry point shows it.

        Returns:
            The loop, running until the tray is stopped.

        """
        serving = asyncio.create_task(entry.serve(self.tray))
        self.addAsyncCleanup(self.stop_serving, serving)

        return serving

    async def stop_serving(self, serving: asyncio.Task[None]) -> None:
        """
        Stop the loop, whatever the test left it doing.

        Args:
            serving: The loop to stop.

        """
        self.tray.stopped = True

        try:
            await asyncio.wait_for(serving, timeout=ROUND * ROUNDS)
        except (TimeoutError, asyncio.CancelledError):
            serving.cancel()

    async def test_the_icon_is_shown_as_soon_as_the_loop_runs(self) -> None:
        """An icon nobody registered is a process with nothing to show."""
        watcher = await self.show_tray()

        await self.serving()
        await settled(watcher)

        self.assertEqual(len(watcher.registered), 1)

    async def test_the_loop_ends_when_the_tray_is_stopped(self) -> None:
        """Quit closes the window, and the bus goes with it."""
        watcher = await self.show_tray()

        serving = await self.serving()
        await settled(watcher)

        self.tray.stop()
        await asyncio.wait_for(serving, timeout=ROUND * ROUNDS)

        self.assertTrue(serving.done())

    async def test_the_menu_is_told_the_words_it_now_says(self) -> None:
        """
        The whole way, from a move on the stream to the bar.

        What the other cases assert apart - a link read, a state
        compared, a signal sent - is asserted here in one piece,
        because it is in one piece that it failed: every part of it
        worked while the menu went on saying no cube was connected.
        """
        watcher = await self.show_tray()
        caught = await self.catch(MENU_PATH, MENU_INTERFACE)

        await self.serving()
        await settled(watcher)

        self.tray.dispatch(envelope('cube.move', {'move': 'R'}))

        signal = await self.sent(caught, 'ItemsPropertiesUpdated')
        changed, _removed = signal.body

        said = {
            identifier: properties[LABEL_PROPERTY].value
            for identifier, properties in changed
            if LABEL_PROPERTY in properties
        }

        self.assertEqual(said[STATUS_ITEM], TRAY_CONNECTED)

    async def test_the_bar_is_written_again_when_the_cube_arrives(
            self,
    ) -> None:
        """What the whole loop is there for."""
        watcher = await self.show_tray()

        await self.serving()
        await settled(watcher)

        self.tray.dispatch(envelope('cube.move', {'move': 'R'}))

        for _ in range(ROUNDS):
            await asyncio.sleep(ROUND)

            if self.tray.connected:
                break

        self.assertTrue(self.tray.connected)


if __name__ == '__main__':
    unittest.main()
