---
paths:
  - "publishers/**"
---

# Publishers

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

`flare_cube.py` is that publisher, and it is there because two of them
cannot bind the same endpoint: settling the breaths of
`viewer/flare.py` takes a script saying **both planes at once**, and
nothing else here says the session one. It rehearses no honest attempt
— `realistic_cube.py` already does that for the cube plane — it
**replays the moments in a loop**, which is what a duration, a
reach, a curve and two hues are settled with: `scrambling`, the
scramble published as facelets, `scrambled`, the moves putting it back
together, then `stop`. The solve is the **inverse** of the scramble,
so the cube truly is solved when the attempt ends — a bench landing a
solve on a cube that is not one would be settling the effect on
something else. **It publishes no `cube.solved`**: both breaths are
values of `session.state`, a window reads nothing of that topic, and a
bench publishing it would be settling nothing. Nor is there a training
mode: a trained case ends on the very same `stop` and breathes the
very same breath, so a second bench of it would show nothing the
first does not. It follows the conventions of the directory that
`phantom_cube.py` carries in its header: outside `term_timer_clients`,
outside `[project.scripts]`, nothing imports it and **nothing tests
it**, what it is worth being read in the window it opens. Each pause
is an argument of its own, `sid` is drawn at every run, and Ctrl+C
drops the link rather than falling silent.
`realistic_cube.py` stays the second bench, and it is the check
`flare_cube.py` does not make: it publishes `cube.solved` with no
`session.state` anywhere, so a window watching it **breathes on
nothing at all** — the cube seeing itself solved is not an attempt
being over.
