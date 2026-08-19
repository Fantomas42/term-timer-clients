"""What term-timer was configured with, read where term-timer keeps it."""
import logging
import os
import tomllib
from pathlib import Path
from typing import Any
from typing import Final
from typing import cast

from term_timer_clients.protocol import parse_endpoint

logger = logging.getLogger(__name__)

Config = dict[str, Any]

# Where term-timer keeps everything it writes, and the configuration
# file among it. Both variables are read the way term-timer reads them,
# so that a client run against a home moved aside - a test setup, a
# second profile - finds the very file the session it listens to did.
HOME_VARIABLE: Final = 'TERM_TIMER_HOME'

CONFIG_VARIABLE: Final = 'TERM_TIMER_CONFIG'

DEFAULT_HOME: Final = '~/.term_timer'

CONFIG_NAME: Final = 'config.toml'

# Sections of the configuration a client of the stream has a use for:
# where the publisher binds, and how the cube is displayed.
PUBLISHER_SECTION: Final = 'publisher'

CUBE_SECTION: Final = 'cube'


def config_file() -> Path:
    """
    Tell where the configuration of term-timer is to be found.

    ``TERM_TIMER_CONFIG`` names the file itself and wins, as it does in
    term-timer; failing that the file is the one of the home, named by
    ``TERM_TIMER_HOME`` or lying where term-timer creates it.

    Returns:
        The path of the configuration file, existing or not.

    """
    configured = os.getenv(CONFIG_VARIABLE)

    if configured:
        return Path(configured).expanduser()

    home = os.getenv(HOME_VARIABLE) or DEFAULT_HOME

    return Path(home).expanduser() / CONFIG_NAME


def load_config() -> Config:
    """
    Read the configuration term-timer publishes with.

    The file belongs to term-timer alone: a client never creates it and
    never completes it, so anything unreadable is an absence of
    defaults rather than an error. A window still opens on what its own
    command line says, which is all a client ever needed.

    Returns:
        The configuration, empty when there is none to read.

    """
    path = config_file()

    try:
        with path.open('rb') as fd:
            return tomllib.load(fd)
    except OSError as error:
        logger.debug('No configuration read from %s: %s', path, error)
    except tomllib.TOMLDecodeError as error:
        logger.warning('Cannot read the configuration %s: %s', path, error)

    return {}


def config_section(config: Config, name: str) -> Config:
    """
    Read one table of the configuration.

    Args:
        config: The configuration, as it was read.
        name: Name of the table to read.

    Returns:
        The table, empty when the file carries nothing under that name.

    """
    section = config.get(name)

    if not isinstance(section, dict):
        return {}

    return cast('Config', section)


def configured_endpoint(config: Config) -> str:
    """
    Read the endpoint of the stream a client connects to by default.

    The publisher binds every endpoint its ``[publisher]`` section
    lists, and a subscriber connects to one of them: the first that
    names a transport is taken, the file listing them in the order they
    are meant to be tried. An endpoint given on the command line still
    wins over it - what is configured is where the stream is, not where
    this window has to listen.

    Args:
        config: The configuration, as it was read.

    Returns:
        The endpoint to connect to, empty when none is configured.

    """
    endpoints = config_section(config, PUBLISHER_SECTION).get('endpoints', [])

    if not isinstance(endpoints, list):
        return ''

    for token in endpoints:
        endpoint = parse_endpoint(str(token))

        if endpoint:
            return endpoint

    return ''


def configured_cube(config: Config, key: str) -> str:
    """
    Read one of the display settings of the cube.

    The window is meant to look like the cube term-timer draws in the
    terminal, so what is under ``[cube]`` is read here rather than
    typed again on the command line.

    Args:
        config: The configuration, as it was read.
        key: Name of the setting, as the section spells it.

    Returns:
        The setting, empty when the section carries nothing under it.

    """
    value = config_section(config, CUBE_SECTION).get(key, '')

    if not isinstance(value, str):
        return ''

    return value
