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
- **`link.py`** — `CubeLink`, what the stream says of the cube before
  anything shows it, and the base every client showing one is built
  on. Three questions are answered before a picture is: whether the
  stream is one this client can read at all, whether it is still the
  same session talking, and whether there is a cube on the other end.
  The answers are the same for a window and for an icon in a bar, so
  they live here rather than in either — **two copies of them would be
  two answers the day a topic is renamed**, which is the very reason
  the captures of the suite are read in one place. What it holds is the
  link and what the cube said of itself over it: `connected`,
  `hardware`, `battery`, and the `parts` whoever shows them makes a
  sentence of — a window writes them in its bar and an icon in its
  tooltip, and neither spelling is the business of the stream. It is
  written to be subclassed: `handlers` is the dict a consumer adds its
  own topics to, and `restart()` and `unlink()` are what it extends to
  throw away what it alone holds of a cube that is gone. `CubeCast` is
  exactly that — the topics a window has a use for, added to the ones
  the link already answers.
- **`orders.py`** — the three words one client says to a window another
  one holds: `show`, `hide` and `close`, a line each. It is the other
  channel of this repository and it is **nothing like the stream** —
  the stream is a publisher binding for everybody and saying what a
  cube does, this is one process telling one window what to be, so it
  travels on the standard input the child was handed rather than on
  anything bound or named. **The end of the pipe is the third order**,
  and it is the one nobody has to remember to give: a window driven
  from outside has no reason of its own to be open, so the process that
  opened it going away — killed outright included — closes it instead
  of leaving a window nothing can ever reach again. Both sides live
  here for the reason both sides of an endpoint do, and it is the same
  reason `parse_endpoint()` is not written twice: one place saying what
  an order is. `read_orders()` ignores a word it does not know, exactly
  as a client ignores a topic it does not know, and `OrderReader` is
  the very arrangement `EventStream` is — a thread that only ever
  writes down what the loop reads at its next turn.

A cube **announces its departure and never its arrival** — `cube.link`
is published by term-timer rather than by a driver — and a client
opened in the middle of a session has heard neither. So the cube
talking at all is what says it is there, and `cube.link` is the only
topic that ever says it is gone — with `session.end`, which says it of
the publisher rather than of the cube and comes to the same thing: a
cube nobody publishes any more is a cube nobody is connected to. It
can also **go missing**, a process killed outright publishing nothing
at all, so nothing here ever waits for it: it is what spares a client
the wait rather than what a client is built on. Neither closes the
window — that would take the session with it — and a publisher that
comes back finds somewhere to be shown, `interrupted` and `crashed`
being sessions that may well.

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
it that will drift. `parse_size()` and `write_size()` are there for
the same reason and are a pair on purpose — `cube-tray` writes the
size that `cube-cast` reads, and one notation spelled in two places is
one that will be spelled two ways. `DEFAULT_WINDOW_SIZE` is there for
the reason the notation is: the window a click opens *is* `cube-cast`,
so a size of its own in `tray/` would be one client showing the same
cube at two sizes depending on which one opened it — and the client
that draws the window cannot be the one holding it, an OpenGL stack
being what importing it costs a process that draws twenty-two pixels.
`orders.py` is the third of these,
for a client that *drives* another one rather than merely reading the
same stream: `write_order()` and `read_orders()` are the two sides of
one word, and they are in one file for the reason both ends of an
endpoint are.

A client subscribes to the prefixes it needs (`CUBE_PREFIX`,
`SESSION_PREFIX`) — ZeroMQ filters by prefix, and no complete topic
name is a prefix of another, which is why the move catch-up is
`cube.history` and not
`cube.move_history`. A whole topic name filters just as well, which is
what `cube-cast` subscribes with: `SESSION_END_TOPIC` and
`SESSION_STATE_TOPIC` and `SESSION_TRAIN_TOPIC` next to the cube
plane, the three messages of the session plane a window has any use
for — the end of the stream, what the session says it is doing, which
is the only thing telling a solve landing from a cube being fiddled
with, and an attempt on a trained case, which is the one thing a cube
ending every case solved can never tell — and the rest of what
term-timer knows alone stays on the wire.

## Style

Enforced by ruff, but worth knowing before writing: single quotes,
line length 80, one import per line (`force-single-line`), spaced
f-string braces (`f'{ value }%'`) — which a format spec makes
impossible, the trailing space landing inside it, so those go through
`format(value, '.3f')` instead, and which **a `str.format()` template
cannot take either**, the spaces being part of the key there:
`'{ pid }'.format(pid=1)` raises, and an f-string is what such a
template is written as instead — Google-style docstrings on
everything public — including `Args:` and `Returns:`. Comments in this
codebase explain *why* a constraint exists, not what a line does; match
that register.

## Where the rest lives

Detail lives in `.claude/rules/`, loaded when a matching file is read.
Read the file itself when reasoning about one of these without opening it:

- `cube-cast.md` — the client itself and the clock its moves are played on
- `cube-cast-window.md` — host, framing, and every command line option
- `cube-cast-effects.md` — the implosion of `assembly.py`, the breaths of `flare.py`
- `tt-tail.md` — the stream read out loud, and what `--record` is for
- `cube-tray.md` — the icon, its menu, the two processes, and the DBus file
- `tests.md` — the captures, the fixtures, and the bus the suite starts
- `publishers.md` — the benches, and why nothing tests them
- `deploy.md` — the unit template and `install.sh`
