---
paths:
  - "term_timer_clients/viewer/**"
---

# cube-cast

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
