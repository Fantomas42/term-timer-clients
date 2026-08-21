# The term-timer event stream, version 1

This document is the whole contract between a publisher and its
clients. It says nothing about Python, and nothing about term-timer
beyond the names of the things it publishes: anything speaking it can
produce the stream, and anything speaking it can consume it.

It lives in this repository, the one of the clients, and
[term-timer][tt] publishes against it: the version above is the whole
of what the two sides have to agree on.

[tt]: https://github.com/Fantomas42/term-timer

## Transport

ZeroMQ `PUB`/`SUB`, with no broker in between. The publisher **binds**,
every client **connects**, so clients come and go in any order and none
of them holds the publisher back. A publisher with nobody listening
drops its messages, which is the intended behaviour rather than an
incident.

term-timer binds the endpoints listed in the `[publisher]` section of
its configuration file:

```toml
[publisher]
active = false
endpoints = [
  "ipc://~/.term_timer/cube.ipc",
  "tcp://127.0.0.1:5555",
]
```

An endpoint is a ZeroMQ `<transport>://<address>`. Both ends must spell
it the same way, so the address of an `ipc` endpoint has its leading
`~` expanded before it reaches ZeroMQ — a subscriber connected to a
socket that does not exist waits in silence forever, and says nothing
about it.

Nothing is republished when a client joins: a subscriber arriving mid
session hears the stream from that moment on, and catches up on the
next spontaneous message.

## The envelope

Every message is two ZeroMQ frames: the topic, then a compact UTF-8
JSON object.

```json
{
  "v": 1,
  "seq": 4213,
  "ts": 1755500000.123456,
  "src": "solve",
  "sid": "a3f1c8d2",
  "topic": "cube.move",
  "data": { "move": "R'", "serial": 42, "clock": 128734 }
}
```

| Field | Meaning |
|---|---|
| `v` | Version of the protocol. Bumped only on a break, see below |
| `seq` | Monotonic counter of the publishing process, from 0. A hole means messages were lost — high water mark reached, or a late subscription |
| `ts` | Time of publication, epoch seconds, on the clock of the publisher |
| `src` | The command publishing: `solve`, `train`, `ghost`, `daily`, `bt-info`… |
| `sid` | Session identifier, constant for the life of the process. A change means the publisher restarted, and a client starts over |
| `topic` | Repeats the topic frame on purpose, so a logged, replayed or bridged message stays self-describing |
| `data` | The payload, always an object, never an array nor a scalar |

`src` and `sid` travel in every message rather than in a greeting, so
that a client joining late is immediately operational.

## Topic names

Topics are hierarchical, dot separated, and ZeroMQ filters them by
prefix:

```python
socket.subscribe(b'')                # everything
socket.subscribe(b'cube.')           # the hardware plane only
socket.subscribe(b'session.record')  # records only
```

**No complete topic name is a prefix of another.** That is why the
catch-up of missed moves is `cube.history` and not `cube.move_history`,
which a subscriber to `cube.move` would have caught.

## `cube.*` — what the hardware produces

These are the driver events, published as they are: the payload is the
event minus its name, which the topic already tells, with timestamps
turned into epoch seconds. A replay feeds the very same stream as a
real cube.

`clock` is the clock of the cube, in milliseconds, and travels with
every one of them.

| Topic | `data` |
|---|---|
| `cube.facelets` | `facelets` (54 characters, URFDLB), `serial`, `state`, `clock`, `timestamp` |
| `cube.move` | `move` (notation), `serial`, `face`, `direction`, `cube_timestamp`, `local_timestamp`, `clock`, `timestamp` |
| `cube.history` | Same as `cube.move`: the moves a cube reports after the fact, to fill a gap |
| `cube.gyro` | `quaternion` `{w,x,y,z}`, `velocity` `{x,y,z}`, `clock`, `timestamp` |
| `cube.hardware` | `hardware_name`, `hardware_version`, `software_version`, `gyroscope_enabled`, `gyroscope_ready`, `gyroscope_supported`, … |
| `cube.battery` | `level`, `charging_state` |
| `cube.config` | `gyroscope_enabled`, `gyroscope_ready`, `gyroscope_supported` |
| `cube.reset` | `{}` |
| `cube.link` | `connected` (bool), `reason` (`opened`, `closed`, `lost`) |

A cube announces its departure and never its arrival, so `cube.link` is
published by the application rather than by a driver. Fields a given
cube does not report are simply absent: a client reads what it needs
and ignores the rest.

Rotations are **not** in this plane: they are derived downstream of the
drivers, and a client orienting a cube does it from the raw quaternion
of `cube.gyro`. Applying both would turn the cube twice.

## `session.*` — what only term-timer knows

| Topic | `data` |
|---|---|
| `session.state` | `state`, `previous`, `at` — the nine states of a solve: `configure`, `init`, `scrambling`, `scrambled`, `inspecting`, `inspected`, `solving`, `stop`, `saving` |
| `session.scramble` | `scramble`, `oriented`, `rotation`, `facelets`, `cube_size`, `index`, `total` |
| `session.solve` | The solve as the session file writes it — `time` in nanoseconds, `moves`, `scramble`, `device`, `flag`… — plus `dnf`, `counter`, `session`, `cube_size`, `free_play` and `steps` |
| `session.record` | `kind` (`single`, `ao5`, `ao12`, …), `scope` (`session`), `value`, `previous`, `delta`, `counter` |
| `session.train` | `step`, `family`, `case`, `name`, `algorithm`, `time`, `dnf`, `counter`, `rating`, `state`, `due` |
| `session.end` | `reason` (`closed`, `interrupted`, `crashed`) — the last message of the stream |
| `session.step` | Reserved. Waits for a live method detection, which does not exist yet |
| `session.rotation` | Reserved. Waits for a subscriber asking for the rotations built downstream of the drivers |

`session.solve` is spelled like the stored solve on purpose: a client
writing down what it receives records a readable session, without a
single field to translate.

## The end of a stream

`session.end` is published on the way out, before the socket closes, and
nothing of the session follows it. It is the only message a publisher
owes its subscribers, because it is the only one no later message makes
up for: a publisher that stops simply falls silent, and silence is what
a session where nothing happens looks like.

| `reason` | What ended the session |
|---|---|
| `closed` | The command is over |
| `interrupted` | Ctrl+C |
| `crashed` | An error carried the process away |

Whatever the reason, the stream is over and the state a client built
from it can go: `closed` is a session to forget, `interrupted` and
`crashed` are sessions that may well come back. What comes back is told
apart by the `sid` of the envelope, a new one meaning a new session to
start over on.

**The farewell can go missing**, so no client may wait for it forever.
A process killed outright — `SIGKILL`, a `SIGTERM` nobody handles, a
machine going down — publishes nothing at all, and a subscriber that
stopped reading is dropped rather than waited for. A client that has to
know whether a publisher is still there times out on the silence, and
takes the farewell as what spares it the wait.

## Evolution rules

These are what make a client written today keep working tomorrow:

1. **Adding a topic breaks nobody.** Ignoring what it does not know is
   an obligation of a client, not a courtesy.
2. **Adding a field to `data` breaks nobody**, same rule.
3. **Renaming or removing a topic or a field breaks everybody**, so it
   bumps `v` — and it is the only thing that does. In practice nothing
   is ever removed: a new field is added next to the old one, which
   stays alive.
4. **`data` is always an object**, so that rule 2 always applies.
5. **A client checks `v`** and stays quiet on a major it does not know.

## A client, in full

```python
import json

import zmq

socket = zmq.Context.instance().socket(zmq.SUB)
socket.setsockopt(zmq.SUBSCRIBE, b'cube.')
socket.connect('ipc:///home/you/.term_timer/cube.ipc')

while True:
    topic, payload = socket.recv_multipart()
    message = json.loads(payload)

    if message['v'] != 1:
        continue

    print(message['topic'], message['data'])
```
