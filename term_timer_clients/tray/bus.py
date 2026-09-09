"""How an icon gets itself shown by the desktop, and stays shown."""
import asyncio
import logging

from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import BusType
from dbus_next.constants import MessageType
from dbus_next.message import Message

from term_timer_clients.tray.item import ITEM_PATH
from term_timer_clients.tray.item import MENU_PATH
from term_timer_clients.tray.item import WATCHER_PATH
from term_timer_clients.tray.item import WATCHER_SERVICE
from term_timer_clients.tray.item import TrayItem
from term_timer_clients.tray.item import TrayMenu
from term_timer_clients.tray.item import item_service

logger = logging.getLogger(__name__)


class BusError(Exception):
    """
    What the bus answered when the icon could not be shown.

    Its own rather than the one dbus-next raises, and for the reason
    every error here is raised at all: nothing is asked of a proxy, so
    nothing raises on its own, and an error reply is read where it
    arrives.
    """


# What asks the desktop to show an icon, and what is answered by the
# tray of a shell rather than by the specification: an item registers
# itself, and is drawn from then on.
REGISTER_MEMBER = 'RegisterStatusNotifierItem'

# The bus daemon itself, and the one thing it is asked here: who owns a
# name. A shell that restarts - or an extension turned off and on
# again - takes every icon with it and remembers none of them, and the
# name coming back is the only warning an icon ever gets.
DBUS_SERVICE = 'org.freedesktop.DBus'

DBUS_PATH = '/org/freedesktop/DBus'

DBUS_INTERFACE = 'org.freedesktop.DBus'

ADD_MATCH_MEMBER = 'AddMatch'

OWNER_CHANGED_MEMBER = 'NameOwnerChanged'

# Only the tray of the desktop coming and going, and nothing else the
# bus carries: a session bus is a busy place, and a handler reading
# every message on it to drop all but one is a handler run for nothing
# thousands of times.
OWNER_CHANGED_MATCH = (
    f"type='signal',sender='{ DBUS_SERVICE }',"
    f"interface='{ DBUS_INTERFACE }',member='{ OWNER_CHANGED_MEMBER }',"
    f"arg0='{ WATCHER_SERVICE }'"
)


async def open_bus() -> MessageBus:
    """
    Connect to the bus of the session.

    Returns:
        The bus, connected.

    """
    return await MessageBus(bus_type=BusType.SESSION).connect()


async def call(bus: MessageBus, message: Message) -> Message:
    """
    Ask something of the bus, and read what comes back.

    Written on messages rather than on a proxy, and it buys two things:
    the round trip an introspection costs before the first word is
    spoken, and an answer whose shape is known here rather than
    assembled at runtime out of an XML document.

    Args:
        bus: The bus to talk on.
        message: What is being asked.

    Returns:
        The reply.

    Raises:
        BusError: When the reply is an error, or when there is no reply
            at all.

    """
    reply = await bus.call(message)

    if reply is None:
        msg = f'no reply to { message.member }'
        raise BusError(msg)

    if reply.message_type == MessageType.ERROR:
        text = reply.body[0] if reply.body else reply.error_name
        raise BusError(str(text))

    return reply


async def register(bus: MessageBus, service: str) -> None:
    """
    Ask the desktop to show this icon.

    Args:
        bus: The bus the icon is exported on.
        service: The name the icon answers to.

    """
    await call(
        bus,
        Message(
            destination=WATCHER_SERVICE,
            path=WATCHER_PATH,
            interface=WATCHER_SERVICE,
            member=REGISTER_MEMBER,
            signature='s',
            body=[service],
        ),
    )

    logger.info('Registered in the system tray')


async def follow_watcher(bus: MessageBus, service: str) -> None:
    """
    Register again whenever the desktop puts its tray back up.

    An icon that registered once and never again is one that is simply
    gone the first time a shell restarts, the process behind it running
    on with nothing to show for it.

    Args:
        bus: The bus the icon is exported on.
        service: The name the icon answers to.

    """
    def owner_changed(message: Message) -> None:
        """
        Notice the tray of the desktop coming back.

        Args:
            message: Whatever the bus just carried.

        """
        if (
                message.message_type != MessageType.SIGNAL
                or message.member != OWNER_CHANGED_MEMBER
                or message.interface != DBUS_INTERFACE
        ):
            return

        # The name, who owned it, and who owns it now: an owner
        # arriving is the tray coming up, and one leaving is the shell
        # on its way out, which there is nothing to do about.
        _name, _old, new = message.body

        if not new:
            return

        logger.info('The system tray came back')

        task = asyncio.create_task(register(bus, service))

        # Held until it is over: a task nothing keeps a name to is one
        # the loop is free to collect in the middle of registering.
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    tasks: set[asyncio.Task[None]] = set()

    await call(
        bus,
        Message(
            destination=DBUS_SERVICE,
            path=DBUS_PATH,
            interface=DBUS_INTERFACE,
            member=ADD_MATCH_MEMBER,
            signature='s',
            body=[OWNER_CHANGED_MATCH],
        ),
    )

    bus.add_message_handler(owner_changed)


async def publish(bus: MessageBus, item: TrayItem, menu: TrayMenu) -> str:
    """
    Put the icon and its menu on the bus, under a name of their own.

    Args:
        bus: The bus to be shown on.
        item: The icon itself.
        menu: The menu it drops.

    Returns:
        The name the icon answers to.

    """
    bus.export(ITEM_PATH, item)
    bus.export(MENU_PATH, menu)

    service = item_service()

    await bus.request_name(service)

    return service


def close_bus(bus: MessageBus) -> None:
    """
    Give the bus back, the icon having nothing left to say.

    Args:
        bus: The bus the icon was shown on.

    """
    # dbus-next annotates the rest of its bus and not this: an
    # untyped call is what it is, and the alternative is a socket
    # left to the end of the process.
    bus.disconnect()  # type: ignore[no-untyped-call]
