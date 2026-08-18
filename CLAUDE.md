# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e .[dev]

ruff check term_timer_clients
mypy term_timer_clients --strict
pytest term_timer_clients --cov=term_timer_clients

# One module, one case, one test
pytest term_timer_clients/tests/test_viewer.py
pytest term_timer_clients/tests/test_viewer.py::CubeMoveTestCase
pytest term_timer_clients/tests/test_viewer.py::CubeMoveTestCase::test_move_is_pushed_as_it_arrives
```

The suite needs neither a GPU nor a cube. `--strict` mypy and `ruff`
with `select = ["ALL"]` are the baseline: new code is expected to pass
both without new ignores.

## What this repository is

Clients of the [term-timer](https://github.com/Fantomas42/term-timer)
event stream — separate processes that subscribe to what a solving
session publishes over ZeroMQ. term-timer never loads, launches or
knows about a client; connecting is the whole of the coupling.

`PROTOCOL.md` is the contract, version 1, and it lives here alone:
term-timer holds no copy of it and publishes against this one. So this
file is the authority — changing it changes what term-timer must
publish, and nothing propagates the change by itself.

Its evolution rules govern the code: adding a topic or a field breaks
nobody, and renaming or removing one bumps `PROTOCOL_VERSION` — nothing
else does. A client ignores what it does not know rather than failing
on it.

## Architecture

Three layers, and the boundaries between them are the point:

- **`protocol.py`** — the envelope, `parse_endpoint()`, and
  `EventStream`, a `SUB` socket read in a daemon thread. Knows nothing
  about cubes: frames in, envelopes out. Shared by every client.
  The subscriber *connects* and the publisher *binds*, which is what
  makes start order irrelevant and lets a client come and go.
- **`viewer/client.py`** — `CubeView`, the whole of `cube-view`, and it
  touches neither a socket nor a window. An envelope comes in and a
  viewer method is called: topics are dispatched through a
  `self.handlers` dict. This is where a new topic is handled.
- **`viewer/main.py` / `viewer/host.py`** — the entry point assembles
  window, viewer and stream; `CubeViewHost` extends the cubing-algs
  `GlfwHost` and only adds a window title.

The threading split is deliberate and constrains where things may be
done: the stream thread pushes moves the moment they arrive (the
animation reads its cadence from that), while glfw demands its window
be handled from the thread that opened it. So the stream only ever
mutates state — `CubeView.title` — and the window picks it up at the
next `frame()`.

`sid` changing means the publisher restarted: `CubeView.restart()`
throws away the cube, the tracker and the title rather than showing a
new session through the drift of the old one.

Rotations are derived downstream of the drivers and are **not** in the
`cube.*` plane: a client orients from the raw `cube.gyro` quaternion.
Applying both would turn the cube twice. Likewise, when a display
orientation is configured, moves arrive in the hardware frame and must
go through `CubeView.translate()` before being pushed.

## Adding a client

Put shared stream code in `protocol.py`, keep the client itself free of
sockets and windows, add a `[project.scripts]` entry point. A client
subscribes to the prefixes it needs (`CUBE_PREFIX`, `SESSION_PREFIX`) —
ZeroMQ filters by prefix, and no complete topic name is a prefix of
another, which is why the move catch-up is `cube.history` and not
`cube.move_history`.

## Tests

`tests/replays/gan_gen2/*.json` are real captures: a list of driver
events, each with an `event` key naming its type. `test_viewer.py`
turns them into envelopes (`event` stripped, mapped through `TOPICS`)
and plays them into a mocked `Viewer` — that is how cube behaviour is
tested without hardware. `test_protocol.py` uses real ZeroMQ sockets on
a real thread instead of mocking the transport.

`tests/fixtures.py::envelope()` builds a message as the publisher
writes it; use it rather than hand-writing dicts.

## Style

Enforced by ruff, but worth knowing before writing: single quotes,
line length 80, one import per line (`force-single-line`), spaced
f-string braces (`f'{ value }%'`), Google-style docstrings on
everything public — including `Args:` and `Returns:`. Comments in this
codebase explain *why* a constraint exists, not what a line does; match
that register.
