---
paths:
  - "term_timer_clients/tests/**"
---

# Tests

`tests/replays/gan_gen2/*.json` are real captures: a list of driver
events, each with an `event` key naming its type. `test_viewer.py`
turns them into envelopes (`event` stripped, mapped through `TOPICS`)
and plays them into a mocked `Viewer` — that is how cube behaviour is
tested without hardware. `test_protocol.py` uses real ZeroMQ sockets on
a real thread instead of mocking the transport, and `test_orders.py`
opens a real `os.pipe()` for the same reason: what is being asserted
there is that the *end* of the pipe is heard, and a mock ends whenever
the test says so.

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
