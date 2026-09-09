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
- **`viewer/client.py`** — `CubeCast`, the whole of `cube-cast`, and it
  touches neither a socket nor a window. An envelope comes in and a
  viewer method is called: topics are dispatched through a
  `self.handlers` dict. This is where a new topic is handled. Two of
  them take the cube down and they end in the same `unlink()`: a link
  that drops, and `session.end`, the farewell of the publisher. What
  ended the session only ever reaches the log — a session `closed`,
  `interrupted` or `crashed` leaves the very same window behind,
  because a stream that is over publishes no state and no move
  whatever carried it away.
- **`MoveClock`, of cubing-algs** — where the clock of the cube stands
  next to the clock of the client, and the whole of what makes
  `cube-cast` answer a hand rather than trail it. It lives in the
  library rather than here because it is the companion of the
  `Viewer.push(age=)` the library documents: any producer stamping on
  a clock of its own — a replay, another driver — reads its age the
  same way, and none of the arithmetic knows a cube from a socket.
  **A move is over by
  the time it is heard of**: the cube reports a face once it has
  stopped turning, the report crosses a bluetooth link and a stream,
  and the hand is elsewhere when the window finally hears about it. So
  a move is handed to `Viewer.push()` with the **age** it has already
  reached, and the animation starts the turn where it would already
  stand instead of at zero. A cube stamps on a counter of its own,
  sharing no origin with anything here, but two clocks with no common
  origin still tell the same *durations*: the offset is read as the
  smallest delay ever observed between a stamp and its arrival, and
  what a later arrival exceeds it by is the delay that move alone
  suffered. **What is measured is therefore the jitter and never the
  latency** — the minimum absorbs whatever the link costs every single
  time, and no reading from this side can tell a constant delay from a
  difference of origins, which is why the constant is `lead`, a setting
  argued with on the command line rather than a measurement. What the
  measurement buys is the cadence of the fingers in place of the
  cadence of the radio: a stack batching two moves into one packet
  hands them over at the very same instant, and the stamps the cube
  wrote are what puts them back where they happened. A delay is only
  ever known against a **younger** move, so the head of the very first
  burst is handed over younger than it is — it lasts one burst, and it
  errs on the side of the cube being behind rather than ahead. The
  reading belongs to the connection it was taken in and goes with it,
  in `restart()` as in `unlink()`: a counter runs whether or not
  anybody listens, and the cube coming back may not even be the one
  that left.
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
  travel it has covered (`Mat4.scaling()`), because one ray points at the
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
  dimmed and spread by the `DORMANT_*` terms, weighed by what is
  missing of the glow so the sheen comes back exactly as the color
  does. **One mix and never one per knob**: `dormant()` describes that
  ball as a `Look` built on the one the viewer holds — differing by
  the terms of the core alone — and `Look.blended()`, which cubing-algs
  owns, reads every term of the two part of the way at once. So a knob
  added to a look tomorrow travels without a line written here, and
  nothing but the core can move. The lamp is the one thing left out of
  it, and for a reason of shape: it is *turned* around the ball by an
  angle, where everything else is read along a straight line. It
  travels
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
  tens of times a second, and `--all` gives it up. `session.end` is
  the one topic that is more than its block: the farewell is drawn
  across the terminal under it, the way the session was opened, because
  a stream that is over and one where nothing happens both look like
  silence and nothing else tells them apart. The tail goes on reading
  all the same — a publisher binds the endpoint a subscriber is already
  connected to, and the next session announces itself by the `sid` of
  its envelopes. A message held back
  is still counted in the sequence, so a loss it hid is reported
  rather than blamed on the topic that comes next; the two prefixes
  cover everything the publisher emits, which is what makes a break in
  `seq` a loss at all. **Reading and recording are two gestures**, and
  the filters of one are not the filters of the other: `--record`
  appends every envelope that arrives to a file, one JSON object per
  line and the envelope whole, before the version is even looked at —
  the gyroscope whatever `--all` says, an unknown topic, and a stream
  this client cannot speak, which is exactly what a capture is opened
  for. A recorder is injected next to the writer, so `main.py` stays
  the only thing that knows about a file as it is the only thing that
  knows about `sys.stdout`. Appended and never started over — a tail is
  stopped and started again all day long, and a `sid` tells the
  sessions apart on the disk as it does on the screen — and a file that
  cannot be opened stops the client rather than being read as an
  absence: a recording asked for on a command line and silently not
  made is found missing the day it is read, when what it was to hold is
  already gone. The gaps are measured on **what is printed**,
  not on what arrived: a cadence counting invisible messages would say
  nothing about the blocks being read. Colors are asked for the same
  way whether or not any are worn — a disabled `Paint` hands its text
  back untouched — so the rendering has one shape, and the whole suite
  asserts on bare text; wrapping is measured on the bare text and the
  color worn by each piece afterwards, an escape being counted as a
  column by anything that counts characters.
- **`tray/`** — `cube-tray`, the cube in the bar of the desktop, and
  **two processes rather than one**: the icon holds no cube and draws
  none, a click on it opens a `cube-cast` of its own, and the two meet
  nowhere but on the stream they both subscribe to — which is exactly
  what a publisher binding for everybody is for. They are two because
  they are two loops, glfw wanting the thread that opened its window
  and the bus wanting one of its own, and the split is what spares this
  client an OpenGL stack it would carry to draw twenty-two pixels. The
  window is opened `--transparent`, which is already the popup: no
  decoration, no background, floating above what it is glanced at over.
  **Where it opens is the compositor's business and nobody else's** —
  the tray protocol never says where a shell drew the icon, so a window
  under it cannot be aimed at, and a placement guessed at is a window
  landing somewhere else on the next screen. `Ctrl` drag carries it,
  and nothing remembers where.
  The same split as `tail/` runs through it: `icon.py` draws and
  touches no bus, `client.py` decides what the icon says and what a
  click does and touches neither bus nor process, `cast.py` is the only
  thing that names `subprocess`, `item.py` and `bus.py` the only ones
  that name D-Bus, and `main.py` the only one that reads `sys.argv`.
  So the whole of what this client decides is asserted without a bus
  and without a window.
  The icon is **drawn in code** rather than shipped as a file: three
  rhombi around a center are a cube seen by its corner, the outline is
  the very same cube drawn wider — so no edge is a line and the rim has
  no gap — and it is what makes the icon readable on a dark bar and a
  light one alike. A cube that is not there is the same cube in greys
  and **never a fainter one**: an icon dimmed by its alpha reads as a
  bar that is busy, where a cube gone grey reads as a cube that is not
  there. Drawn once and kept, a cube sampled pixel by pixel being tens
  of milliseconds and a shell being free to read the icon back whenever
  it likes.
  `state` is what the bar is written again for — the icon, the tooltip
  and whether the window is up — and it is compared rather than pushed:
  the gyroscope alone publishes tens of times a second, and an icon
  redrawn that often is an icon redrawn for nothing. Both signals go
  out and the properties with them, because a shell caches what it read
  and the specification signals alone carry no value. **The words are
  sent and not merely the revision**, and the reason is in the tray of
  GNOME rather than in the protocol: it asks the layout for the shape
  of the menu alone — `GetLayout` with `type` and `children-display`
  and nothing else — and takes the words of a line from the properties
  it was last handed, so a menu announcing itself by its revision only
  goes on offering to show a window that has been up for a while. So
  `TrayMenu.refresh()` sends `ItemsPropertiesUpdated`, carrying the
  labels themselves, next to the `LayoutUpdated` that carries the
  revision — **anything added to a line of the menu has to travel in
  that signal or it will not be seen to change.** That is a bug this
  client shipped, and the way it was found is worth as much as the
  fix: the consumer was read, in
  `/usr/share/gnome-shell/extensions/ubuntu-appindicators@ubuntu.com/`,
  where `dbusMenu.js` and `indicatorStatusIcon.js` say what that
  desktop truly does with an icon. It is where to look again rather
  than guessing, and it costs nothing to read.
  The menu carries the show gesture itself, and that is not a
  duplicate of the click: **a plain left click on GNOME drops the
  menu**, whatever `ItemIsMenu` says — the extension never reads it,
  and keeps `Activate` for a *double* click and `SecondaryActivate` for
  the middle button. So the menu is the left click here, and an icon
  whose only gesture were `Activate` would be an icon that does nothing
  on the desktop it was written for. Its lines are numbered rather than counted, separators
  included, and **never at zero** — zero is the root of the menu, and a
  line sharing it is a line a shell is free to take for the whole menu.
  A tray that comes back is registered with again: a shell that
  restarts takes every icon with it and remembers none of them, and an
  icon that registered once and never again is a process running on
  with nothing to show for it.
- **`viewer/main.py` / `viewer/host.py`** — the entry point assembles
  window, viewer and stream; `CubeCastHost` extends the cubing-algs
  `GlfwHost` with a window title, and takes the keyboard moves back
  off. The stream is the only thing entitled to turn this cube: a face
  played from the keyboard — or a `Backspace` putting the cube back
  together — would drift the window away from the hardware with nothing
  to bring the two back together, so the host is built `moves=False`
  and cubing-algs refuses them **at the door** rather than having a
  key claimed one by one here. That flag also takes them out of the
  list the window prints, which is the whole of why it is one flag and
  not two: a window that answers fewer keys and a list that offers
  fewer keys are the same decision, and they were two copies of it for
  as long as the list was a block recopied here. `VIEWER_SHORTCUTS` is
  now **composed** — `viewer_entries()` for the lines this window
  inherits, `HelpEntry` for the three it adds, `help_block()` to write
  them out — so a gesture reworded upstream is reworded here, and
  `ShortcutsTestCase` compares the whole inherited half rather than
  two lines of it. The three view keys are answered in
  `on_viewer_key()` and everything else falls through to the host —
  they are answered there rather than in the viewer because cubing-algs
  has no notion of a view to stand in, and `reframe()` is the whole of
  what they do: the framing into `Viewer.rotation`, then
  `reset_camera()`.
  **Nothing here paints the ground**, and that is
  the whole of the subject: the window is cleared with the cold slate
  `VIEWER_BACKGROUND` of cubing-algs, and a client setting a ground of
  its own would be one window disagreeing with every other one the
  library opens. It was a constant here for exactly one commit, and the
  measurement that moved it into the library is worth keeping: a rim
  raised to give the silhouette back what a dark ground takes came out
  **invisible**, the rim being `pow(1 - dot(normal, view), rim_power)`
  and so reaching the chamfers of the outline alone, where the stickers
  face the camera and take none of it. What draws a cube against a dark
  ground is the outer stickers, so the look is left exactly as
  cubing-algs ships it — `Viewer` is handed no `look=` at all. What this
  client still owes the arrangement is a single assertion,
  `DormantGroundTestCase`: the ground belongs to the library and the
  graphite of `DORMANT_CORE` belongs here, so this is the only side that
  can notice the day a window is cleared darker than the one thing a
  waiting client is left showing. Only a transparency actually *granted*
  takes the ground away, and the library default is what a refused one
  falls back on.
- **`viewer/framing.py`** — `Framing`, where the camera stands and
  what the `1`, `2` and `3` keys move it between. Pure: a view name
  comes in and a rotation string comes out, and the viewer is what
  builds a camera from it. **Two views and a flag, never three views**
  — looking from behind is a way of looking at the view one is in
  rather than a view of its own, so it applies to either of them
  instead of being written against the one it was thought of on, it
  survives a change of view, and there is one place saying what
  passing behind means instead of one per view. `demo` is the framing
  of cubing-algs, imported as `ROTATION` rather than recopied — a demo
  view drifting away from the framing it is the demo of is the one
  thing it may not do — and `user` is that elevation with the yaw
  taken out, **computed** and not written down: what the view names is
  a way of *holding* a cube, about which a library changing its three
  quarter view has nothing to say, but the height it is held at is
  exactly what that library decides. So the yaw of `ROTATION` is
  folded out of it rather than `x-34` being typed here, which would go
  on saying `x-34` the day cubing-algs says something else. `flipped()` **adds the half turn to the yaw and
  writes the framing out again** rather than appending `y180` to it:
  the parts of a rotation do add up per axis, so appending would frame
  the very same thing, but what comes out is then a pile of the turns
  that were asked for — `y45x-34y180` — instead of the angle the
  camera ends up at. The arithmetic itself is
  `cubing_algs.display.rotation.turned_rotation()`, the grammar of a
  framing belonging to the library that reads it: what is said here is
  only that passing behind a cube is half a turn of the yaw and
  nothing else, the elevation being what makes the view. What comes
  out is written into
  `Viewer.rotation` and never into the camera, `reset_camera()`
  reading it: the view being watched is the view `Space` comes back
  to, mirror included.
- **`--view` / `--rotation` / `--mirror`** — where the camera stands
  when the window opens, and the very same views and flag the keys
  reach. They are the framing string of cubing-algs and **not** a cube
  rotation: `--orientation` translates the moves, these only move the
  eye, and the gyroscope keeps turning the cube under them.
  `--rotation` **replaces the demo view** rather than standing beside
  it as a third framing: an angle typed and left behind by the first
  key pressed would be one nothing could ever return to, so `1` comes
  back to it, and `3` passes behind it like behind any other. The
  command line and the keyboard say the same three things because
  `--mirror` is a flag and not a view — a mirror named among the views
  would be the mirror of *one* of them, and the other one could never
  be seen from behind at all. cubing-algs falls back on its default
  for a string it cannot read, which would open the very window the
  option was meant to change and say nothing about it, so the option
  is typed `rotation_argument`, which refuses one instead. It is the
  library that holds it, next to the `valid_rotation()` it is written
  on: the grammar belongs to whoever reads it, a renderer wants the
  fallback where a command line wants the refusal, and the `--rotation`
  of cubing-algs itself had the very same hole.
- **`--no-gyroscope`** — a cube deaf to what turns it, and the option
  is *the absence of a tracker* rather than a topic dropped as it
  arrives: `build_host()` hands `None` to `Viewer` and to `CubeCast`
  alike, which is the very state a client that never orients itself is
  already in — `turn_cube()` has nothing to feed a quaternion to, and
  the window is framed by the view and the mouse alone. Filtering
  it on the wire is what cannot be done and what is not wanted:
  ZeroMQ subscribes by prefix, so dropping one topic of the `cube.`
  plane would mean naming every other one, and a gyroscope that stops
  arriving is a cube that stops saying it is there — `dispatch()`
  reads `connected` off the cube talking at all. What it drops is the
  orientation and never the cube: the moves keep arriving and keep
  being played.
- **`--beat` / `--lead`** — how fast the cube answers, and the one
  place two options are a single subject. `--beat` is how long a
  quarter turn is given to turn, `--lead` how much of a move is
  reckoned already over when the window hears of it. Measured on the
  `cadence.py` harness of cubing-algs against a simulated 80 ms link,
  the delay from the gesture to the cube landing is
  **`latency + beat − lead`**, which says two things at once: that
  every millisecond of visible turn is a millisecond of retard, so the
  only real choice is how much of the turn one wants to look at; and
  that a lead is not a knob of its own. **Compensating alone changes
  nothing at all** — 0.33 s either way at 8 TPS — because an age only
  reaches the schedule while the beat is shorter than the gap between
  two moves: above it the queue saturates, `start = max(date, end)`
  pins each move behind the one before it, and the dates are never
  read. Hence the defaults, 100 ms and 50 ms against the 280 ms of
  cubing-algs, which is a beat written for an algorithm one reads
  rather than for a hand one follows: 0.16 s of measured lag against
  0.33 s, and a beat that stays under the gap of a hand up to ten
  turns a second. The ceiling on the age is read on the beat for the
  same reason — an age reaching the whole of a turn starts it where it
  ends, and the face lands without ever being seen to move — and it
  has to sit **above** the lead rather than on it: what it bounds is
  the delay measured on top of the lead, so a ceiling equal to the
  lead clamps every measurement away and leaves the reading of the
  clock doing nothing at all. Three quarters of the beat is what keeps
  a visible quarter of the turn in the worst case while leaving the
  jitter room to be worth measuring. A lead **typed** is honored
  whatever it says, asking for a cube that snaps being a thing one may
  want.
- **`--transparent` / `--no-msaa`** — a cube laid on the desktop, and
  **two flags handed to `GlfwHost`** rather than a window opened here:
  the hints, the answer of the compositor read back, the offscreen
  target a transparent visual imposes on the antialiasing and the
  resolve onto the window all belong to cubing-algs, none of them
  knowing anything about a cube or a stream. It was written here for a
  while, and the whole of that was the host **reaching around**
  `GlfwHost` instead of under it — hints posted before
  `super().open()`, `viewer.look` dropped to zero samples for the
  length of the call and put back — because `create_window()` had no
  word for them. It has one now, and the detour it needs lives in
  `tick()` rather than in `frame()`, so the seam this client overrides
  stays the cube and nothing else. What is still owed is the *title*: a
  window with no bar has nowhere to show it, and it is written all the
  same for a taskbar and an alt-tab to read.
- **The mouse** — a drag orbits the cube and `Ctrl` held at the press
  carries the window, and **both are inherited**: which button orbits
  is what no mode may change, the drag being the one gesture a viewer
  is made of. What this side still owes the arrangement is that
  `VIEWER_SHORTCUTS` — the lines of the library with the keys turning a
  cube taken out, and three of its own added — says what the window it
  opens truly answers, and `ShortcutsTestCase` is the assertion holding
  it: every line this window did not add is compared to the
  `viewer_help(moves=False)` it was composed from, so a gesture
  reworded upstream is noticed here rather than described wrongly.

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
next `frame()`, through the `set_title()` of `GlfwHost`: renaming a
window belongs to the host that owns it, and what is written there is
the base the debug counter appends its numbers to rather than the bar
alone.

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
one that will be spelled two ways.

A client subscribes to the prefixes it needs (`CUBE_PREFIX`,
`SESSION_PREFIX`) — ZeroMQ filters by prefix, and no complete topic
name is a prefix of another, which is why the move catch-up is
`cube.history` and not
`cube.move_history`. A whole topic name filters just as well, which is
what `cube-cast` subscribes with: `SESSION_END_TOPIC` next to the cube
plane, the one message of the session plane a window has any use for,
and the rest of what term-timer knows alone stays on the wire.

## Publishers

`publishers/` is the other side of the stream, and it is debug material
rather than a client: `phantom_cube.py` binds where term-timer binds
and publishes the frames a cube would, so a window is watched with no
hardware and no session at all. It sits outside `term_timer_clients`
and outside `[project.scripts]` on purpose — nothing imports it,
nothing installs it, and **nothing tests it**: what it is worth is
read in the window it opens, and a test of it would be a test of the
protocol written twice. It still passes `ruff`, and its prints — the
whole of what a debug script says — are what the `# ruff: noqa: T201`
of its header is for.

It publishes in the frame of the *hardware*: `--setup` and
`--algorithm` are written the way the hands write them, and
`--orientation` turns them back the way a cube held that way would
report them, so the very translation `CubeCast.translate()` undoes is
done there first. Each pause of the cycle is an argument of its own,
because what is being debugged is never the same moment twice. `sid`
is drawn at every run, which is what makes `CubeCast.restart()`
reachable by restarting the script, and Ctrl+C drops the link rather
than merely falling silent. It publishes the `cube.*` plane and
nothing else — the plane a cube produces by itself, and the whole of
what a script with no session behind it can honestly say; what only
term-timer knows waits for a publisher of its own.

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

`test_tray_bus.py` starts a **session bus of its own** — a
`dbus-daemon` for the suite, torn down with it — and never speaks to
the bus of the desktop. It is not a nicety, and the reason is worth
keeping: a shell draws a tray icon by *asking the process behind it*,
synchronously, and a test that registers an icon and then takes its
process away leaves the shell waiting on a service that will never
answer. **A shell waiting is a desktop that has stopped**, and the way
out of it is the power button. So the icon is registered, read and
clicked on a bus nothing else is listening to, and anything asserted by
hand against the real bar is a hang waiting to happen. The suite skips
itself where there is no `dbus-daemon` to start, and it is where the
two service interfaces are read back exactly as a shell reads them —
which is how `AboutToShowGroup` was found declaring one structure where
the protocol declares two arguments.

It is also the **only** way they can be read at all, and that is not a
matter of taste: the `@method()` of dbus-next wraps the function in one
that calls it and returns nothing, so `menu.get_layout(0, -1, [])` in a
test hands back `None` however right the method is. Only the bus calls
the real one. The same goes for the signals — a revision that moves
proves nothing, and `ItemsPropertiesUpdated` was missing for a while
under a test asserting exactly that. **What a shell would see is what
has to be asserted**: the properties as they come back over the bus,
and the signals as they arrive. What is left to assert in plain
unittest is everything that decides — `client.py` and `icon.py`, which
is why they hold no bus.

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

`tray/item.py` is the one file where none of that holds, and its header
says why: the annotations of a service method are **DBus signature
strings** and not Python types, which is where dbus-next reads the type
of every argument. A `@no_type_check` under each decorator is what
keeps `mypy --strict` from reading them as forward declarations, and
the `# ruff: file-ignore` at the top covers the three shapes the two
specifications impose — arguments handed over whether or not there is
anything to do with them, interfaces answering for a constant with no
state to answer from, and a variant carrying its value where it is
given. **A new file talking to the bus needs the same two**, and
neither is a shortcut around a weakness of the code.
