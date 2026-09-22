---
paths:
  - "term_timer_clients/tail/**"
---

# tt-tail

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

`tt-tail` reads the stream in the main thread — `stream.receive()` in a
loop rather than `stream.start()` — because nothing here needs that
thread for itself. One reader and one writer means no lock, and
`STREAM_POLL_TIMEOUT` is what a `Ctrl-C` costs. `cube-cast` is the
other case, and the reason is glfw rather than taste.
