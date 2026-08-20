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
  say nothing at all of a cube that has already connected. Graphite
  while nothing is connected, its blue green back
  the moment the link comes up: the one thing left in the window has
  to say for itself whether there is a cube behind it. Graphite and
  never black, because **the shader adds the core highlight on top of
  the color rather than through it**: a ball taken down to black is
  that one hard glint and nothing else — the plastic sphere of a
  rendering of thirty years ago — and its rim light, which multiplies
  the color, has nothing left to multiply. So a waiting core is also
  taken matte, `core_specular_strength` and `core_specular_power`
  dimmed and spread by `DORMANT_GLOSS` and `DORMANT_GLOSS_SPREAD`
  through `dimmed()`, weighed by what is missing of the glow so the
  sheen comes back exactly as the color does. It travels
  through `look.core_color`, which the `look=` of `Viewer.draw()`
  carries and which **cubing-algs holds since the `Look` field of the
  same name**: the `>=` of `pyproject.toml` is what says so, and it
  has to name the release that added it. Only the blast is shared —
  `glow` goes out on `EXPLOSION_DURATION` with the pieces, a cube
  going away being one gesture where it arrives in two. A dormant
  ball also **breathes**, graphite to a banked teal and back
  (`DORMANT_CORE` to
  `PULSE_CORE`), the light of the core swelling on the same cosine: a
  still picture says nothing of whether the viewer is waiting or has
  stopped, and the wait is what has to be seen. Slowly, over a
  `PULSE_PERIOD` measured in the seconds of something at rest, weighed
  by `BREATH_EASE` so the ball lies at the bottom of its breath far
  longer than it rises — an even swell in and out beats like a
  metronome — and between two colors a step apart rather than a leap:
  a swell is to be found by an eye resting on the window, never thrown
  at one crossing it, and anything quicker or louder reads as an
  alarm. **The breath is spent on the light before the hue**, which is
  what there is here in the place of a glow: `core_rim_strength` up
  and `core_rim_power` down (`PULSE_RIM`, `PULSE_HALO`) widen the edge
  inwards, on a teal barely leaning off the graphite. **The rim and
  nothing else**, and the reason is in the shader: it multiplies the
  color, where the highlight is *added* on top of it and added white —
  a sheen swelling over the ball glows the color of the lamp and
  washes the ball out instead of warming it. So the highlight stays at
  the matte it is dimmed to, still for the whole of the wait, and a
  halo spilling past the ball would take a post-process cubing-algs
  does not have. Both ends of the
  breath wear **the hue of a live core and none of its light** — the
  wait is about that cube, so it says so with its color, and a sixth
  of the brightness is what keeps waiting from being read as running,
  where a warmth of its own would have said something happened
  instead. It lives in the dormant end of the mix and is
  weighed by what is missing of the *glow*, so it goes out exactly as
  the color comes in and a lit core is handed the very look it came
  with; `Assembly.elapsed` is its clock, wrapped on `PULSE_PERIOD` so
  a window nobody closes never counts a night into a float. The lamp
  also **walks around the ball** (`spun()`, `SPIN_PERIOD`,
  `SPIN_AXIS`, on the `Assembly.turned` clock of its own, **held at
  nothing while the core is lit** — where `elapsed` runs on behind a
  connected cube, a turn cannot: the angle a free-running counter
  stood at is the angle the lamp would be dragged across the moment
  the link drops, and a cube going away has to see the light *start*
  moving rather than land. It is reset where the weight of the turn is
  already nothing, so the reset itself costs no jump), and it is
  the light because **the ball cannot be turned at all**: the core is
  a smooth sphere of one color centered on the origin, so rotating its
  geometry carries every vertex onto the place of another and its
  normal with it — not one pixel changes, which the core already
  proves by following the gyroscope through every turn of the cube
  without ever being seen to move. A highlight going round is the only
  spin such a ball has in it. `light_direction` is the lamp of the
  *cube* as much as of the core — cubing-algs lights both from the one
  direction — so the angle is weighed by what is missing of the glow
  like everything else here: the lamp walks home the short way as the
  core lights up, and a connected cube is lit from exactly where
  `--rotation` and the look put it. `SPIN_PERIOD` is deliberately not
  divided by `PULSE_PERIOD`, and it has its own counter for that
  reason: one clock shared would either lock the breath and the turn
  into a single beat or jump one of them at the wrap.
- **`tail/client.py` / `tail/render.py` / `tail/ansi.py`** — `tt-tail`,
  the stream read out loud. `StreamTail` holds no cube and imports
  nothing of cubing-algs: what arrives is what is shown, and the only
  state it keeps — the previous stamp, the one per topic, the sequence
  number — belongs to the reading rather than to the cube. The split
  is the one `viewer/` is made of: `render.py` turns an envelope into
  lines and touches no terminal, `client.py` decides what is written
  and hands the lines to an injected writer, and `main.py` is the only
  thing that knows about `sys.stdout`. **A field is shaped by its name
  and by its type, never by the topic it arrived under** — that is
  what makes a topic added tomorrow readable today, and it is why
  `CLOCK_FIELDS` and its neighbours are keyed on field names rather
  than on a table per topic. For the same reason **every topic is
  printed, the unknown ones included**: ignoring what it does not know
  is what a client owes the protocol, and the viewer does exactly
  that, but a tail hiding the one message its reader opened it for
  would be of no use. `QUIET_TOPICS` is the single exception, and it
  is about cadence rather than about meaning — the gyroscope publishes
  tens of times a second, and `--all` gives it up. A message held back
  is still counted in the sequence, so a loss it hid is reported
  rather than blamed on the topic that comes next; the two prefixes
  cover everything the publisher emits, which is what makes a break in
  `seq` a loss at all. The gaps are measured on **what is printed**,
  not on what arrived: a cadence counting invisible messages would say
  nothing about the blocks being read. Colors are asked for the same
  way whether or not any are worn — a disabled `Paint` hands its text
  back untouched — so the rendering has one shape, and the whole suite
  asserts on bare text; wrapping is measured on the bare text and the
  color worn by each piece afterwards, an escape being counted as a
  column by anything that counts characters.
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

`tt-tail` reads the stream in the main thread — `stream.receive()` in a
loop rather than `stream.start()` — because nothing here needs that
thread for itself. One reader and one writer means no lock, and
`STREAM_POLL_TIMEOUT` is what a `Ctrl-C` costs. `cube-cast` is the
other case, and the reason is glfw rather than taste.

The threading split of the viewer is deliberate and constrains where
things may be done: the stream thread pushes moves the moment they
arrive (the animation reads its cadence from that), while glfw demands
its window
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
sockets and windows, add a `[project.scripts]` entry point. What is
shared by the *command lines* rather than by the stream lives in
`argparser.py`: `LOG_FORMAT`, `parse_stream_endpoint()` and
`add_endpoint_argument()`, so that every client is pointed at the
stream by the same option with the same help rather than by a copy of
it that will drift.

A client subscribes to the prefixes it needs (`CUBE_PREFIX`,
`SESSION_PREFIX`) — ZeroMQ filters by prefix, and no complete topic
name is a prefix of another, which is why the move catch-up is
`cube.history` and not
`cube.move_history`.

## Tests

`tests/replays/gan_gen2/*.json` are real captures: a list of driver
events, each with an `event` key naming its type. `test_viewer.py`
turns them into envelopes (`event` stripped, mapped through `TOPICS`)
and plays them into a mocked `Viewer` — that is how cube behaviour is
tested without hardware. `test_protocol.py` uses real ZeroMQ sockets on
a real thread instead of mocking the transport.

`tests/fixtures.py::envelope()` builds a message as the publisher
writes it; use it rather than hand-writing dicts. `TOPICS`, `capture()`
and `envelopes()` live there too rather than in the suite of one
client: two copies of what a capture means would be two answers the day
a topic is renamed. `test_tail.py` writes into a list and keeps the
colors off, an escape counted as a column being a block nothing can
assert on.

## Style

Enforced by ruff, but worth knowing before writing: single quotes,
line length 80, one import per line (`force-single-line`), spaced
f-string braces (`f'{ value }%'`) — which a format spec makes
impossible, the trailing space landing inside it, so those go through
`format(value, '.3f')` instead — Google-style docstrings on
everything public — including `Args:` and `Returns:`. Comments in this
codebase explain *why* a constraint exists, not what a line does; match
that register.
