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
                 [-s WIDTHxHEIGHT] [-t] [-a] [-d]

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
  -t, --transparent     Lay the cube on the desktop: no background, no window
                        decoration, and floating above everything.
                        Default: False.
  -a, --axes            Show the XYZ axes in the scene.
                        Default: False.
  -d, --debug           Measure what a frame costs, and write it in the title.
                        Default: False.
```

The window turns nothing itself. The cubing-algs viewer reads the
letters of the notation as moves, and this one holds them back: the
stream is the only thing entitled to move a cube that is being turned
somewhere else, and a face played from the keyboard — or a `Backspace`
putting the cube back together — would drift the window away from the
hardware with nothing to bring the two back together. What is left is
what only looks at the cube:

```
  Drag             Orbit the cube
  Wheel            Zoom in and out
  Space            Frame the cube again
  Tab              Open the cube up, and put it back together
  F2               Show the X/Y/Z axes, red green blue
  F3               Monitor the rendering performance
  F4               Print a performance report
  F5               Turn the vsync on and off
  F12              Write a screenshot
  Esc, Q           Close the window
```

`--transparent` lays the cube on the desktop: the background goes, the
decoration with it, and the window floats above everything else. The
window then has no bar left to carry it by, so the left button moves it
and the orbit goes to the right one. It also has nowhere left to show
the title, and the hardware and the battery are written there — a
compositor that refuses the transparency says so in a warning, and the
window opens on the grey of the viewer.

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
