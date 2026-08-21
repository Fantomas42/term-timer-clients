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
- **`tt-tail`**, the stream itself, read out loud in a terminal: one
  block per message, of both planes, formatted and lightly colored.

## Installation

```bash
pip install .
```

The 3D view is drawn by [cubing-algs][ca], through moderngl and glfw,
which come with it. `tt-tail` needs none of them, and draws with the
escape sequences of the terminal alone.

[ca]: https://github.com/Fantomas42/cubing-algs

## cube-cast

Publishing is off by default in term-timer. Turn it on for a session,
with the `[publisher]` section of its configuration file filled in:

```toml
[publisher]
active = true
endpoints = ["ipc://~/.term_timer/cube.ipc"]
```

Then, in a terminal of its own, open a window on it:

```bash
cube-cast
```

The configuration of term-timer is where the client reads its own
defaults: the first endpoint the `[publisher]` section binds is the one
it connects to, and `[cube]` says how the cube is oriented and painted.
The file is looked up as term-timer looks it up — `TERM_TIMER_CONFIG`,
or `config.toml` in `TERM_TIMER_HOME`, or `~/.term_timer/config.toml` —
so a window shows the very cube the terminal next to it shows, with
nothing typed twice.

Nothing of it is compulsory. Every setting is one option away, and the
option wins:

```bash
cube-cast -e ipc://~/.term_timer/cube.ipc -p dracula
```

A term-timer that was never configured — or a client run on another
machine than the session — leaves `-e` required, there being no stream
to be found otherwise. A palette or an orientation this client cannot
draw is dropped with a warning rather than refused: the file belongs to
term-timer, and a client ignores what it does not know.

Any command that talks to a cube feeds it — `solve`, `train`, `ghost`,
`daily`, `bt-info` — and so does a replay. Nothing has to be started in
any particular order: the window waits for a session, follows the next
one when term-timer is restarted, and can be closed and reopened
without the session ever noticing.

A window that opens on a cube nobody has described yet shows the ball
core alone, the pieces of the cube blown out of the frame. They implode
around the core the moment a cube connects and says what it looks like,
and they are blasted away from it again when the link drops — the state
underneath is kept, and it is the one the next connection starts from.

```
Usage: cube-cast [-h] [-e ENDPOINT] [-o ORIENTATION] [-p PALETTE] [-m MODE]
                 [-r ROTATION] [-w WIDTHxHEIGHT] [-t] [--no-msaa]

Watch a cube in 3D, from the term-timer event stream.

Options:
  -h, --help            Show this help message and exit.
  -e ENDPOINT, --endpoint ENDPOINT
                        Connect to this ZeroMQ endpoint, one of those the
                        [publisher] section of the configuration binds.
                        Default: the first one it binds.
  -o ORIENTATION, --orientation ORIENTATION
                        Set the cube orientation used.
                        Default: the faces the cube is held by.
  -p PALETTE, --palette PALETTE
                        Set the colors of the cube.
                        Default: the colors of a cube.
  -m MODE, --mode MODE  Show only what a step of the solve is about, e.g. oll.
                        Default: the whole cube.
  -r ROTATION, --rotation ROTATION
                        Set the angle the camera looks the cube from,
                        as AXISDEGREES parts, e.g. y45x-34.
                        Default: the framing of cubing-algs.
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

`--rotation` says where the camera stands when the window opens, as
the axis and angle parts `python -m cubing_algs apply --rotation`
takes: `y45x-34` is the framing of the library, `y90x-20` opens on the
R face, `y0x0` looks the cube straight in the F face. It frames the
cube rather than turning it — the cube is turned by the hardware
alone — and `Space` comes back to it, so a window opened on an angle
stays on it.

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

## tt-tail

`cube-cast` shows a cube and says nothing of the session around it.
`tt-tail` says all of it: it subscribes to both planes and writes every
message down as it arrives, in a block of its own.

```bash
tt-tail
```

It reads its endpoint where `cube-cast` reads its own, in the
`[publisher]` section of the configuration of term-timer, and `-e` is
required only when nothing configured one.

```
── session a3f1c8d2 · solve ─────────────────────────────────────────
┌ 12:04:31.220 · cube.move · +1.204s · Δcube.move 0.512s · #4213
│ move             R'
│ serial           42
│ face             1
│ direction        0
│ cube_timestamp   20.370 s
│ local_timestamp  12:04:31.220
└
┌ 12:04:32.001 · session.state · +0.781s · #4214
│ state     solving
│ previous  inspected
│ at        1274839201847
└
```

The head of a block says when the message was published, what it is,
and where it sits in what the publisher counted. The two gaps are what
the cadence of a solve is read from: `+1.204s` since the block before,
and `Δcube.move 0.512s` since the block before of that same topic. A
break in the sequence numbers is a loss, and it is reported on a line
of its own — nothing else would say that a message was published and
never read.

Values are written in the unit a reader counts in rather than in the
one the wire carries: an epoch float becomes a time of day, the
nanoseconds of a solve or of a record become seconds, the milliseconds
of a cube become seconds too, and the facelets are spaced out into the
six faces they describe. What carries something of its own is laid out
under its name — a quaternion on one line, the steps of a solve as one
sub-block each — and what is too wide hangs under itself rather than
running the next field off the screen.

None of this is decided on the topic: a field is shaped by its name and
by what it holds, so a topic added to the protocol tomorrow is readable
today. **Every topic is printed, the unknown ones included.** Ignoring
what it does not know is what a client owes the protocol, but a tail
that hid the one message its reader opened it for would be of no use to
anyone.

The gyroscope is the one exception. It publishes tens of times a
second, and a block each time is a window where nothing else can be
seen, so it is held back — `--all` gives it up. What it hid is still
counted: a loss behind a message never printed is reported all the
same.

`--record` keeps the stream instead of merely reading it: every message
that arrives is appended to a file, one JSON envelope per line, exactly
as the publisher wrote it.

```bash
tt-tail --record ~/session.jsonl
```

Reading and recording are two gestures, and the filters of one are not
the filters of the other: the file holds the gyroscope whether or not
`--all` shows it, the topics this client knows nothing about, and even
the messages of a protocol version it cannot read. What a capture is
worth is being what passed on the wire rather than what a reading made
of it — a stream that can be replayed, `jq`-ed, or sent along the day
the two sides of it disagree.

The file is appended to rather than started over. A tail is stopped and
started again all day long, and the sessions tell themselves apart by
the identifier of their envelopes on the disk exactly as they do on the
screen, so no run of it ever costs a capture. Each line is flushed as
it is written, for the reason a capture exists at all: what is still in
a buffer when the session is killed is the very part nobody has. A file
that cannot be opened stops the client there and then — a recording
asked for and silently not made would be found missing the day it is
read, and by then what it was to hold is gone.

```
Usage: tt-tail [-h] -e ENDPOINT [-a] [-r FILE] [--no-color]

Read the term-timer event stream as it goes by.

Options:
  -h, --help            Show this help message and exit.
  -e ENDPOINT, --endpoint ENDPOINT
                        Connect to this ZeroMQ endpoint, one of those the
                        [publisher] section of the configuration binds.
                        Default: the first one it binds.
  -a, --all             Show every message, the gyroscope included.
                        Default: False.
  -r FILE, --record FILE
                        Append every message that arrives to this file, one
                        JSON envelope per line, the gyroscope included and
                        whatever --all shows or hides.
                        Default: nothing is recorded.
  --no-color            Write the stream without any color, as it already is
                        when the output is not a terminal or NO_COLOR is set.
                        Default: False.
```

The colors go out on their own when the output is not a terminal, and
`NO_COLOR` is answered too, so `tt-tail > session.log` writes text and
nothing else. Every block is flushed as it is written: a tail left to
its own buffering is a tail that says nothing for pages at a time.

## Writing another client

Everything a client needs is in [PROTOCOL.md](PROTOCOL.md), and a
useful one is short: a recorder writing down what it hears, a bridge to
a WebSocket overlay, a script announcing personal bests.
`term_timer_clients/protocol.py` holds what they share — the envelope,
the endpoints, and a subscription read in a thread — and
`term_timer_clients/config.py` reads the configuration of term-timer,
so that a client is configured where the session is.

## Development

```bash
pip install -e .[dev]

ruff check term_timer_clients
mypy term_timer_clients --strict
pytest term_timer_clients --cov=term_timer_clients
```

The suite needs neither a GPU, a cube nor a terminal: it plays recorded
captures into a mocked viewer and into a reader writing to a list, and
real sockets on a real thread for the stream.
