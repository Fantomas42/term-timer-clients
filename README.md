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

- **`cube-cast`**, a 3D view of the cube, turning and animating in real
  time in a window of its own.

## Installation

```bash
pip install .
```

The 3D view is drawn by [cubing-algs][ca], through moderngl and glfw,
which come with it.

[ca]: https://github.com/Fantomas42/cubing-algs

## cube-cast

Publishing is off by default in term-timer. Turn it on for a session,
with the `[publisher]` section of its configuration file filled in:

```toml
[publisher]
active = true
endpoints = ["ipc://~/.term_timer/cube.ipc"]
```

Then, in a terminal of its own, connect a window to it:

```bash
cube-cast -e ipc://~/.term_timer/cube.ipc
```

Any command that talks to a cube feeds it — `solve`, `train`, `ghost`,
`daily`, `bt-info` — and so does a replay. Nothing has to be started in
any particular order: the window waits for a session, follows the next
one when term-timer is restarted, and can be closed and reopened
without the session ever noticing.

A window that opens on a cube nobody has described yet shows the ball
core alone, the pieces of the cube lying on the floor out of the frame.
They gather around the core the moment a cube connects and says what it
looks like, and they let go and fall back down when the link drops —
the state underneath is kept, and it is the one the next connection
starts from.

```
Usage: cube-cast [-h] -e ENDPOINT [-o ORIENTATION] [-p PALETTE] [-m MODE]
                 [-w WIDTHxHEIGHT] [-t] [--no-msaa]

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
  -m MODE, --mode MODE  Show only what a step of the solve is about, e.g. oll.
                        Default: the whole cube.
  -w WIDTHxHEIGHT, --window-size WIDTHxHEIGHT
                        Set the size of the window.
                        Default: 400x300.
  -t, --transparent     Lay the cube on the desktop: no background, no window
                        decoration, and floating above everything.
                        Default: False.
  --no-msaa             Draw the cube into the window itself, aliased but with
                        nothing in between.
                        Default: False.
```

`--mode` shows only what a step of the solve is about — `oll`, `pll`,
`f2l`, `cross` and the rest of the names `python -m cubing_algs apply`
takes — and hides what the step says nothing about. What is hidden is
a mask over what is drawn, never over what is known: the mask is
settled once and follows the pieces as they turn, so the cube keeps
being the one the hardware reports.

The window turns nothing itself. The cubing-algs viewer reads the
letters of the notation as moves, and this one holds them back: the
stream is the only thing entitled to move a cube that is being turned
somewhere else, and a face played from the keyboard — or a `Backspace`
putting the cube back together — would drift the window away from the
hardware with nothing to bring the two back together. What is left is
what only looks at the cube:

```
  Drag             Orbit the cube
  Ctrl drag        Carry the window across the screen
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

The carry is what replaces a title bar when there is none left, and it
is added to the drag rather than put in its place: which button orbits
the cube is the same whatever the window looks like, and the gesture is
there to be learnt before `--transparent` is ever passed — on a window
that still has its bar, where it merely doubles it.

`--transparent` lays the cube on the desktop: the background goes, the
decoration with it, and the window floats above everything else. It has
nowhere left to show the title, and the hardware and the battery are
written there — a compositor that refuses the transparency says so in a
warning, and the window opens on the grey of the viewer.

A transparent window is refused the multisampling of an ordinary one,
so the cube is antialiased aside and copied in. `--no-msaa` gives that
detour up and draws straight into the window, aliased but with nothing
in between — and drops the antialiasing of an ordinary window as well.

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
