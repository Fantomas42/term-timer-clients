"""
Tests for the configuration a client reads from term-timer.

Nothing here reads the configuration of the machine running the tests:
the environment names a home written for the occasion, which is what
``TERM_TIMER_HOME`` is for on the other side too.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from term_timer_clients.config import CONFIG_NAME
from term_timer_clients.config import Config
from term_timer_clients.config import config_file
from term_timer_clients.config import config_section
from term_timer_clients.config import configured_cube
from term_timer_clients.config import configured_endpoint
from term_timer_clients.config import load_config

CONFIG = """[cube]
orientation = "DF"
palette = "dracula"
linear = true

[publisher]
active = true
endpoints = [
  "ipc://~/.term_timer/cube.ipc",
  "tcp://127.0.0.1:5333",
]
"""


class ConfigFileTestCase(unittest.TestCase):
    """Where the configuration of term-timer is looked for."""

    def test_default_home(self) -> None:
        """A client with nothing in its environment reads the usual home."""
        with patch.dict('os.environ', clear=True):
            self.assertEqual(
                config_file(),
                Path.home() / '.term_timer' / CONFIG_NAME,
            )

    def test_home_variable(self) -> None:
        """A home moved aside is where the file is read from."""
        with patch.dict(
                'os.environ',
                {'TERM_TIMER_HOME': '/opt/timer'},
                clear=True,
        ):
            self.assertEqual(
                config_file(),
                Path('/opt/timer') / CONFIG_NAME,
            )

    def test_config_variable_wins(self) -> None:
        """A file named by the environment is the one that is read."""
        with patch.dict(
                'os.environ',
                {
                    'TERM_TIMER_HOME': '/opt/timer',
                    'TERM_TIMER_CONFIG': '~/elsewhere.toml',
                },
                clear=True,
        ):
            self.assertEqual(
                config_file(),
                Path.home() / 'elsewhere.toml',
            )


class LoadConfigTestCase(unittest.TestCase):
    """What is read from the file, and what is read from nothing."""

    def setUp(self) -> None:
        """Write a configuration in a home of its own."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        self.home = Path(self.directory.name)
        self.path = self.home / CONFIG_NAME

    def read(self) -> Config:
        """
        Read the configuration of the home written for the test.

        Returns:
            The configuration, as the client reads it.

        """
        with patch.dict(
                'os.environ',
                {'TERM_TIMER_HOME': str(self.home)},
                clear=True,
        ):
            return load_config()

    def test_configuration_is_read(self) -> None:
        """The file of the home is read where term-timer keeps it."""
        self.path.write_text(CONFIG, encoding='utf-8')

        self.assertEqual(configured_cube(self.read(), 'palette'), 'dracula')

    def test_missing_file_carries_no_default(self) -> None:
        """A client run without term-timer configured opens all the same."""
        self.assertEqual(self.read(), {})

    def test_unreadable_file_is_reported(self) -> None:
        """A configuration that is not one is said so, and not raised."""
        self.path.write_text('[cube', encoding='utf-8')

        with self.assertLogs('term_timer_clients.config', 'WARNING'):
            self.assertEqual(self.read(), {})


class ConfigReadingTestCase(unittest.TestCase):
    """What a client of the stream reads in the configuration."""

    def test_section(self) -> None:
        """A table of the file is read, and anything else is not one."""
        self.assertEqual(config_section({'cube': {'a': 1}}, 'cube'), {'a': 1})
        self.assertEqual(config_section({'cube': 'DF'}, 'cube'), {})
        self.assertEqual(config_section({}, 'cube'), {})

    def test_endpoint_is_the_first_one_bound(self) -> None:
        """The first endpoint naming a transport is the one connected to."""
        config: Config = {
            'publisher': {
                'endpoints': ['cube.ipc', 'tcp://127.0.0.1:5333'],
            },
        }

        self.assertEqual(configured_endpoint(config), 'tcp://127.0.0.1:5333')

    def test_endpoint_ipc_path_expanded(self) -> None:
        """A tilde in the file is the home the publisher binds."""
        config: Config = {
            'publisher': {'endpoints': ['ipc://~/.term_timer/cube.ipc']},
        }

        self.assertEqual(
            configured_endpoint(config),
            f'ipc://{ Path.home() }/.term_timer/cube.ipc',
        )

    def test_no_endpoint_to_connect_to(self) -> None:
        """A publisher binding nothing leaves the client its command line."""
        configs: tuple[Config, ...] = (
            {},
            {'publisher': {}},
            {'publisher': {'endpoints': []}},
            {'publisher': {'endpoints': 'tcp://127.0.0.1:5333'}},
            {'publisher': {'endpoints': ['cube.ipc']}},
        )

        for config in configs:
            with self.subTest(config=config):
                self.assertEqual(configured_endpoint(config), '')

    def test_cube_setting(self) -> None:
        """A display setting is read under the key term-timer spells."""
        config: Config = {'cube': {'orientation': 'DF', 'linear': True}}

        self.assertEqual(configured_cube(config, 'orientation'), 'DF')
        self.assertEqual(configured_cube(config, 'palette'), '')
        self.assertEqual(configured_cube(config, 'linear'), '')
