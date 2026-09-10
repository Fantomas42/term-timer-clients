"""Custom ArgumentParser with enhanced help message formatting."""
# ruff: noqa: ANN401
import argparse
from argparse import ArgumentTypeError
from typing import Any

from term_timer_clients.protocol import parse_endpoint

LOG_FORMAT = '%(levelname)s: %(message)s'

# What separates the two halves of a size, as every client writes it.
SIZE_SEPARATOR = 'x'

# How big a window opens when nothing asked for another size. It is
# here rather than in the client that opens one because a client
# *driving* another one hands it that size on a command line: two
# defaults would be a popup opening at one size and the very same
# client, run by hand, at another.
DEFAULT_WINDOW_SIZE = (400, 300)


def parse_stream_endpoint(value: str) -> str:
    """
    Read the endpoint of the stream a ``--endpoint`` argument names.

    The endpoint goes through what the publisher reads its own with, so
    that a tilde written on the command line points at the same socket
    as the one written in the configuration.

    Args:
        value: The argument, as it was typed.

    Returns:
        The endpoint to connect to.

    Raises:
        ArgumentTypeError: When the argument names no transport. A
            subscriber given a broken endpoint would wait in silence
            forever, so it is refused here.

    """
    endpoint = parse_endpoint(value)

    if not endpoint:
        msg = (
            f'"{ value }" is not an endpoint, '
            f'expected TRANSPORT://ADDRESS'
        )
        raise ArgumentTypeError(msg)

    return endpoint


def parse_size(value: str) -> tuple[int, int]:
    """
    Read the size of a window a ``WIDTHxHEIGHT`` argument names.

    Args:
        value: The argument, as it was typed.

    Returns:
        The width and the height, in pixels.

    Raises:
        ArgumentTypeError: When the argument names no size.

    """
    width, separator, height = value.lower().partition(SIZE_SEPARATOR)

    if not separator or not width.isdigit() or not height.isdigit():
        msg = (
            f'"{ value }" is not a size, '
            f'expected WIDTH{ SIZE_SEPARATOR }HEIGHT'
        )
        raise ArgumentTypeError(msg)

    return int(width), int(height)


def write_size(size: tuple[int, int]) -> str:
    """
    Write a size out the way a command line takes it.

    Next to what reads one, and for that reason: a client handing a
    size to another client writes what that one reads, and the two
    halves of one notation drifting apart is exactly what a shared
    module is for.

    Args:
        size: The width and the height, in pixels.

    Returns:
        The size, as it would have been typed.

    """
    width, height = size

    return f'{ width }{ SIZE_SEPARATOR }{ height }'


class ArgumentParser(argparse.ArgumentParser):
    """
    Custom ArgumentParser with enhanced help formatting.

    Capitalizes section titles and help text for better presentation.
    """

    class _ArgumentGroup(argparse._ArgumentGroup):  # noqa: SLF001
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.title = self.title and self.title.title()

    class _HelpFormatter(argparse.RawTextHelpFormatter):
        def _format_usage(self, *args: Any, **kwargs: Any) -> str:
            return super()._format_usage(*args, **kwargs).replace(
                'usage:', 'Usage:', 1,
            )

        def _format_action_invocation(self, action: argparse.Action) -> str:
            action.help = action.help and (
                action.help[0].upper() + action.help[1:]
            )
            if action.help and not action.help.endswith('.'):
                action.help = f'{ action.help }.'
            return super()._format_action_invocation(action)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize ArgumentParser with custom help formatter."""
        kwargs['formatter_class'] = self._HelpFormatter
        super().__init__(*args, **kwargs)

    def add_argument_group(self, *args: Any, **kwargs: Any) -> _ArgumentGroup:
        """
        Add argument group with custom formatting.

        Returns:
            Custom _ArgumentGroup instance with title capitalization.

        """
        group = self._ArgumentGroup(self, *args, **kwargs)
        self._action_groups.append(group)
        return group


def add_endpoint_argument(
        parser: ArgumentParser,
        endpoint: str,
) -> None:
    """
    Give a client the ``--endpoint`` argument every client takes.

    Every client connects to the same stream, and one of them spelling
    the option differently would be one of them to look up: the
    argument is built here rather than copied, so that what a client is
    pointed at is asked for the same way everywhere.

    Args:
        parser: The parser of the client.
        endpoint: The endpoint the configuration names, empty when it
            names none.

    """
    # Required only when the configuration names no endpoint: what is
    # missing then is the stream itself, and argparse is what says so
    parser.add_argument(
        '-e', '--endpoint',
        required=not endpoint,
        default=endpoint,
        type=parse_stream_endpoint,
        metavar='ENDPOINT',
        help=(
            'Connect to this ZeroMQ endpoint, one of those the\n'
            '[publisher] section of the configuration binds.\n'
            f'Default: { endpoint or "the first one it binds" }'
        ),
    )
