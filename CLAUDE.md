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
- **`config.py`** — the configuration of term-timer, read where
  term-timer keeps it: `TERM_TIMER_CONFIG`, or `config.toml` under
  `TERM_TIMER_HOME`, or `~/.term_timer/config.toml`, the same lookup on
  both sides so a client finds the file of the session it listens to.
  It is what the defaults of `cube-cast` are made of — the first
  endpoint `[publisher]` binds, and the `orientation` and the `palette`
  of `[cube]` — and `-e` is required only when nothing configured one.
  The file belongs to term-timer: nothing here creates it, completes
  it, or fails on it, an unreadable one being an absence of defaults
  rather than an error, and a taste this client cannot draw being
  dropped with a warning rather than refused. `build_parser()` is
  handed the configuration rather than reading it, so a parser built on
  an empty one is the client with nothing configured anywhere — which
  is what the tests are given.
- **`viewer/client.py`** — `CubeCast`, the whole of `cube-cast`, and it
  touches neither a socket nor a window. An envelope comes in and a
  viewer method is called: topics are dispatched through a
  `self.handlers` dict. This is where a new topic is handled.
- **`viewer/assembly.py`** — the pieces of the cube imploding around
  the ball core, and exploding away from it when the link drops.
  Pure: a scene comes in, a scene comes out, its pieces moved, and it
  is layered on the seam `Viewer` documents for an effect —
  `CubeCastHost.frame()` takes `advance()` and `draw()` apart and
  describes the picture rather than writing into the viewer, so
  nothing leaks into the camera the mouse writes to. A cube nobody is
  connected to is handed over with no instance at all: the core is
  drawn before them and on its own, so it is what stays in the window.
  **A piece only ever travels its own ray**, the one leaving the core
  through the place it belongs to, and that is the whole of why
  nothing collides: two rays leaving the same point never meet again,
  and the ball core sits at the point they leave. The shells are
  ranked by their distance to the core rather than by their height on
  the screen (`SHOCKWAVE`), so an outer piece is never less thrown out
  than the one it covers and the blast runs through the cube instead
  of moving it in one block — centers first on the way in, corners
  first on the way out. `blast()` is one cubic read both ways, and it
  never goes past one at either end: an overshoot would take a piece
  inside its own place, and inside a cube every place is taken. None
  of this is held in the frame of the window, which is why no
  orientation is passed here at all: a blast leaves the core in every
  direction at once. A piece is also drawn at the very share of its
  travel it has covered (`shrink()`), because one ray points at the
  camera: drawn whole, the piece on it would loom over the core it is
  leaving and blink out at the end of the blast. `CubeCast.present`
  is what moves it: a cube connected *and* described. Gathering on
  the link alone would
  pick a solved cube up and repaint it in mid air a moment later,
  and gathering on a state alone would leave the colors of a cube
  nobody is connected to any more hanging in the window. **The core is not
  on that clock**: `Assembly.glow` is moved by `CubeCast.connected`
  alone, over `CORE_DURATION`, while `Assembly.progress` carries the
  pieces. Two events, two effects — a link and a state are published
  apart, and a ball waiting for the facelets would have the window
  say nothing at all of a cube that has already connected. Obsidian
  while nothing is connected, its blue green back
  the moment the link comes up: the one thing left in the window has
  to say for itself whether there is a cube behind it. It travels
  through `look.core_color`, which the `look=` of `Viewer.draw()`
  carries and which **cubing-algs holds since the `Look` field of the
  same name**: the `>=` of `pyproject.toml` is what says so, and it
  has to name the release that added it. Only the blast is shared —
  `glow` goes out on `EXPLOSION_DURATION` with the pieces, a cube
  going away being one gesture where it arrives in two. A dormant
  ball also **breathes**, obsidian to a dark red and back (`DORMANT_CORE` to
  `PULSE_CORE`), `core_rim_strength` swelling on the same cosine: a
  still picture says nothing of whether the viewer is waiting or has
  stopped, and the wait is what has to be seen. Both ends of the
  breath are colors the live core is nowhere near, so waiting is never
  read as running. It lives in the dormant end of the mix and is
  weighed by what is missing of the *glow*, so it goes out exactly as
  the color comes in and a lit core is handed the very look it came
  with; `Assembly.elapsed` is its clock, wrapped on `PULSE_PERIOD` so
  a window nobody closes never counts a night into a float.
- **`viewer/main.py` / `viewer/host.py`** — the entry point assembles
  window, viewer and stream; `CubeCastHost` extends the cubing-algs
  `GlfwHost` with a window title, and takes the keyboard moves back
  off. The stream is the only thing entitled to turn this cube: a face
  played from the keyboard — or a `Backspace` putting the cube back
  together — would drift the window away from the hardware with nothing
  to bring the two back together, so `on_viewer_key()` claims every key
  the window does not answer itself. `VIEWER_SHORTCUTS` is the list
  that says so, written when the window opens through the `shortcuts`
  field of `GlfwHost`.
- **`--rotation`** — where the camera stands when the window opens,
  the framing string of cubing-algs and **not** a cube rotation:
  `--orientation` translates the moves, this one only moves the eye,
  and the gyroscope keeps turning the cube under it. It travels to
  `Viewer.rotation`, which `reset_camera()` reads too, so `Space` comes
  back to the angle the window opened on rather than to the library
  default. cubing-algs falls back on that default for a string it
  cannot read, which would open the very window the option was meant to
  change and say nothing about it, so `parse_camera_rotation()` refuses
  one against `ROTATION_PATTERN` instead.
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
mutates state — `CubeCast.title` — and the window picks it up at the
next `frame()`.

A cube **announces its departure and never its arrival** — `cube.link`
is published by term-timer rather than by a driver — and a client
opened in the middle of a session has heard neither. So the cube
talking at all is what says it is there, and `cube.link` is the only
topic that ever says it is gone.

`CubeCast.present` is two conditions, and they answer the two events
the effect is made of: `connected` says there is a cube, `described`
says it has told what it looks like, and the pieces are drawn only
when both hold. The two arrive milliseconds apart on real hardware,
so nothing is waited on that is not already on its way. A link that
drops lets `described` go with it — a state belongs to the connection
it was published in, and the cube describes itself again at the next
one — which also means a session joined in the middle keeps its core
alone in the window until a state is finally published.

`sid` changing means the publisher restarted: `CubeCast.restart()`
throws away the cube, the tracker and the title rather than showing a
new session through the drift of the old one.

Rotations are derived downstream of the drivers and are **not** in the
`cube.*` plane: a client orients from the raw `cube.gyro` quaternion.
Applying both would turn the cube twice. Likewise, when a display
orientation is configured, moves arrive in the hardware frame and must
go through `CubeCast.translate()` before being pushed.

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
