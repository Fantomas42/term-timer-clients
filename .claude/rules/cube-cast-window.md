---
paths:
  - "term_timer_clients/viewer/main.py"
  - "term_timer_clients/viewer/host.py"
  - "term_timer_clients/viewer/framing.py"
---

# cube-cast — window, framing and options

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
- **`--managed`** — a window opened for **somebody else to show**, and
  it is one flag and not three because the three hold together: a
  window nobody has shown yet has to open hidden, one shown from
  outside is hidden from outside, and one that is only ever put away is
  one somebody else closes. What it buys is the whole of why
  `cube-tray` opens a window nobody asked for yet — a client that has
  followed the stream from the start has heard the cube describe
  itself, where one opened in the middle of a session has heard nothing
  and never will.
  The same three things are owed to it, and each is somewhere different
  on purpose. **Hiding a window belongs to cubing-algs**: `visible`,
  `show()`, `hide()` and the `idle()` turn that advances the cube
  without drawing it know nothing about a cube or a stream, and a
  window drawing into a screen nobody is shown is a window whose swap
  no vsync paces any more — the loop would spin as fast as the machine
  reads its events, which is the one thing a hidden window must not
  cost. **The orders belong to `orders.py`**, both sides of the pipe in
  one place. What is left here is the *decision*: `order()` writes the
  wish down and `obey()` does it at the next turn — the very
  arrangement the title travels by, a window belonging to the thread
  that opened it and the reader having a thread of its own — and
  `on_close()`, the seam cubing-algs opened for exactly this, is where
  `Q` and `Escape` are answered by **doing nothing at all**. Not by
  hiding, which was the first answer and the wrong one: whether the
  window is on the screen is held by whoever shows it — it is what the
  icon writes in its menu and what its next click does — so a key
  putting it away behind that back would be **a second answer to the
  one question**, with nothing on a one-way pipe for the window to say
  otherwise with. Closing itself would be worse still: what it takes
  away is a cube nothing is following any more, which is the whole of
  what the window was kept open for. The list it prints says so by
  leaving that line out — `MANAGED_SHORTCUTS` is `VIEWER_SHORTCUTS`
  minus the line the library names by `HELP_CLOSE`, **found by the keys
  and never by the words**, so a gesture reworded upstream costs
  nothing here.
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
