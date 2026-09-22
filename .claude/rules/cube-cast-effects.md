---
paths:
  - "term_timer_clients/viewer/assembly.py"
  - "term_timer_clients/viewer/flare.py"
---

# cube-cast — the effects

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
- **`viewer/flare.py`** — the four pieces of news a window tells about
  itself, and the only thing `cube-cast` says beyond whether a cube is
  there: a **breath** — the pieces part briefly on their own rays while
  the light rises and the cube takes a color — played on a scramble
  being laid, on a solve landing, and on either end of an attempt on a
  trained case: cold blue for the first, warm amber for the second,
  violet and crimson for the two ends of the third. Written in the
  shape of `assembly.py` for the reason it shares its arithmetic: a
  scene comes in and a scene comes out, its pieces moved, and nothing
  here touches a viewer or a window.
  **No protocol changed for any of it.** Every topic already exists
  and is already published; what changed is the list `cube-cast`
  subscribes to. Two constraints decide the shape of the first two,
  and neither is a taste. **`cube.solved` is noisy by contract** —
  `PROTOCOL.md` says a GAN republishes it every time the cube happens to
  be solved, "scrambling and idle fiddling included — nine times in one
  session" — so it is read **through `session.state`** and honored only
  in `SOLVING_STATES`, the states where a cube saying it is solved is a
  cube somebody was solving. The three and not `solving` alone: nothing
  orders the `stop` term-timer publishes against the `solved` the cube
  publishes — one crosses a bluetooth link and the other does not — and
  both orders have to land. And **`scrambled` has no `cube.*` topic at
  all**, being a value of `session.state`, which is why that whole
  topic name joins `session.end` in the prefixes. A `cube.solved`
  arriving while **no session has ever spoken** is honored, and that is
  a decision rather than an oversight: it is the rule a client lives by
  — ignore what you do not know — read on the permissive side, and it
  is what keeps the effect visible under `bt-info` and under
  `publishers/realistic_cube.py`, which publishes `cube.solved` and, by
  contract, nothing of the session plane. Without it the breath would
  only ever be settled with a real term-timer session at hand.
  A **training session says it another way**, and that is the whole of
  the third and fourth: under `src == 'train'` — the source
  `CubeLink` writes down off the envelope *before* the handler is
  called — `cube.solved` says nothing at all, and `session.train` is
  what the window answers instead. A drilled case ends on a solved
  cube whether or not the case came out, so the solved state is a
  consequence there rather than a piece of news, and the attempt is
  the only thing knowing which case it was and whether it was worth
  anything; **two breaths for one attempt would be the window
  stuttering**. The topic publishes *every* attempt that was executed,
  a DNF and a free play run included, so a failure is a flavour of its
  own rather than a silence — a piece of news is a piece of news, and
  two outcomes are two flavours, which is the very shape `FLARES` has.
  Only `dnf` is read of the payload — what the rating, the state, the
  due date and the free play flag say is what the training file keeps
  — and an absent or unreadable one is read as *not* a DNF, the
  permissive side `celebrate()` is already written on. **The violet
  and the crimson are neighbours on the wheel where the amber and the
  blue are opposites**, and that is the argument rather than what was
  left of it: the two ends of one attempt read as two versions of a
  thing, where the start and the end of a solve read as two things —
  a DNF is not the contrary of a case landed, it is its other end.
  What makes the failure dull is its **`glow`**, the lowest of the
  four, rather than merely the shortest breath: the rim barely rises,
  so the cube gives a start instead of lighting up: a miss is told,
  never announced. Its reach and its tumble stay under everything else
  for the reason `WAVEFRONT` documents — the shells keep their order
  for any reach at or under one, and a piece of news one regrets does
  not open the cube.
  **The color travels on the plastic and on the core, never on the
  stickers**: `Scene.plastic` tints the edges, the chamfers and the
  grooves of every piece, `Look.core_color` tints the ball the gust
  uncovers by parting them, and the fifty-four facelets keep exactly
  what their palette gives them. That is the principle cubing-algs is
  built on — the color of a cube is what one reads to know where it
  stands, and a client moving it for the length of an animation makes
  the window lie about the state of the cube. Both channels are
  uniforms, and the instance buffer is being re-uploaded anyway while
  the pieces move, so neither costs anything. `swell()` is the curve,
  read in two around `ATTACK_SHARE`: a smoothstep over the first
  quarter and the same one backwards over the rest — **exactly zero at
  both ends and exactly one at the top**, which is what makes the
  return to rest an equality rather than an approach. A sharp attack
  and a long fall, because what is told is news and news arrives; an
  even swell in and out beats like a metronome, which is the shape a
  *wait* is already drawn with next door. `Flare` is the flavour, and
  the only thing the two differ by — duration, reach, tumble, the `hue`
  they carry (named so rather than `tint`, which is already the method
  an effect paints a look by here) and the `glow` they are told with.
  Everything else is the breath itself and is shared, two
  announcements made in two shapes being two effects rather than one
  word said twice. `FLARES` maps every word `CubeCast` writes down
  to the flavour the host plays, and **both sides live in this file**
  for the reason `orders.py` holds both sides of an order. `Gust` is the
  frame of one moment, the counterpart of `Flight`: **a piece only ever
  travels its own ray**, shells handed their turn by their distance to
  the core as `SHOCKWAVE` does it, and the `Mat4` composed exactly as
  `Flight.place()` composes it — the push around the model, the tumble
  inside it. It is also what lets the two effects be **composed at
  all**: the assembly places the pieces and the breath pushes them out
  from where they stand, both along the very same ray, so a solve
  landing in the middle of an implosion adds to it without a piece ever
  meeting another. Nothing is scaled, unlike the blast: a piece pushed
  a third of its own radius never comes near enough the camera to loom,
  and pieces shrinking as they part would read as a cube going away.
  `tint()` is one `look.blended(flared(look), swell)` and never one mix
  per knob — the very argument `dormant()` is written on: the flavour
  describes a look built **on the one it is handed**, so the two differ
  by the terms that move and a knob added upstream travels without a
  line written here. It is the **rim** that rises and nothing else, for
  the reason the breath of a waiting core is spent on the rim: it
  multiplies the color, where the highlight is added on top and added
  white — a sheen swelling over the cube glows the color of the lamp
  and washes the palette out. **The idle contract is the hard
  constraint**: outside a breath `apply()` hands the scene back
  `is`-identical and `tint()` the look `is`-identical. The renderer
  recognizes a scene by identity and skips its instance upload, and
  that is the state the window spends its life in — which is why
  `BurstTestCase` and `FlareTintTestCase` assert it with `assertIs`,
  as `AssemblyTestCase` and `CoreTintTestCase` already do.
