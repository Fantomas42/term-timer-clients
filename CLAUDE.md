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
  `GlfwHost` with a window title, and takes the keyboard moves back
  off. The stream is the only thing entitled to turn this cube: a face
  played from the keyboard — or a `Backspace` putting the cube back
  together — would drift the window away from the hardware with nothing
  to bring the two back together, so `on_viewer_key()` claims every key
  the window does not answer itself. `VIEWER_SHORTCUTS` is the list
  that says so, written when the window opens through the `shortcuts`
  field of `GlfwHost`.
- **`--transparent`** — a cube laid on the desktop, and the one place
  the host reaches around `GlfwHost` rather than under it. The three
  glfw hints it needs are posted *before* `super().open()` runs: hints
  are a global state read when a window is created, and
  `create_window()` adds its own to them instead of clearing them
  first, which is what keeps the whole of `open()` inherited. A
  multisampled window gets the transparency refused, so `viewer.look`
  is dropped to zero samples for the length of that call and put back
  at once — `F12` and `F4` read their samples from it too — and the
  cube is antialiased in an `OffscreenTarget` resolved onto the window
  in `frame()`. Both hypotheses are checked at runtime: a refused
  transparency is read back off the window and logged. `--no-msaa`
  gives that detour up: `offscreen` is what says a target is built at
  all, and no antialiasing means none in the window either.
- **The mouse** — a drag orbits the cube in either mode, and no mode
  may move that: it is the one gesture the viewer is made of, and a
  `--transparent` displacing it would make the flag change what the
  hands do. What a window with no bar needs on top is the carry,
  `Ctrl` held down at the press, and a decorated window answers it too
  — there it merely doubles the bar it still has, which is what makes
  the gesture learnable before the flag is ever passed. So
  `VIEWER_SHORTCUTS` is one list, and `on_mouse_button()` reads the
  modifier rather than the mode. The carry needs a window free to
  place itself, and every window opened here is: cubing-algs hands a
  Wayland session the X11 variant of glfw — moderngl having no way to
  read a context off the other one — and refuses a window outright on
  a platform that stayed Wayland.

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
