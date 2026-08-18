# Term Timer Clients

Clients of the [term-timer][tt] event stream: separate processes that
subscribe to what a solving session publishes and do something with it.

[tt]: https://github.com/Fantomas42/term-timer

term-timer publishes two planes of events over ZeroMQ — `cube.*` for
what the hardware produces, `session.*` for what only a timing session
knows — and never loads a client, launches one, or knows one exists.
A client connects, and that is the whole of the coupling. The contract
between the two is [PROTOCOL.md](PROTOCOL.md), version 1.

Living here today:

- **`cube-view`**, a 3D view of the cube, turning and animating in real
  time in a window of its own.

## Installation

```bash
pip install .
```

The 3D view is drawn by [cubing-algs][ca], through moderngl and glfw,
which come with it.

[ca]: https://github.com/Fantomas42/cubing-algs

## cube-view

Publishing is off by default in term-timer. Turn it on for a session,
with the `[publisher]` section of its configuration file filled in:

```toml
[publisher]
active = true
endpoints = ["ipc://~/.term_timer/cube.ipc"]
```

Then, in a terminal of its own, connect a window to it:

```bash
cube-view -e ipc://~/.term_timer/cube.ipc
```

Any command that talks to a cube feeds it — `solve`, `train`, `ghost`,
`daily`, `bt-info` — and so does a replay. Nothing has to be started in
any particular order: the window waits for a session, follows the next
one when term-timer is restarted, and can be closed and reopened
without the session ever noticing.

A window that opens on a cube nobody has described yet shows a solved
one, and gets it right at the first state the cube reports — a single
move is enough.

```
Usage: cube-view [-h] -e ENDPOINT [-o ORIENTATION] [-p PALETTE]
                 [-s WIDTHxHEIGHT] [-a] [-d]

Watch a cube in 3D, from the term-timer event stream.

Options:
  -h, --help            Show this help message and exit.
  -e ENDPOINT, --endpoint ENDPOINT
                        Connect to this ZeroMQ endpoint, one of those the
                        [publisher] section of the configuration binds.
  -o ORIENTATION, --orientation ORIENTATION
                        Set the cube orientation used.
                        Default: the faces the cube is held by.
  -p PALETTE, --palette PALETTE
                        Set the colors of the cube.
                        Default: the colors of a cube.
  -s WIDTHxHEIGHT, --size WIDTHxHEIGHT
                        Set the size of the window.
                        Default: 800x600.
  -a, --axes            Show the XYZ axes in the scene.
                        Default: False.
  -d, --debug           Measure what a frame costs, and write it in the title.
                        Default: False.
```

The window itself is driven by the keys of the cubing-algs viewer:
letters of the notation turn a face, shift for a prime, control for a
half turn, alt to widen.

## Writing another client

Everything a client needs is in [PROTOCOL.md](PROTOCOL.md), and a
useful one is short: a tail of the stream, a recorder writing down what
it hears, a bridge to a WebSocket overlay, a script announcing personal
bests. `term_timer_clients/protocol.py` holds what they share — the
envelope, the endpoints, and a subscription read in a thread.

## Development

```bash
pip install -e .[dev]

ruff check term_timer_clients
mypy term_timer_clients --strict
pytest term_timer_clients --cov=term_timer_clients
```

The suite needs neither a GPU nor a cube: it plays recorded captures
into a mocked viewer, and real sockets on a real thread for the stream.
