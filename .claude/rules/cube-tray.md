---
paths:
  - "term_timer_clients/tray/**"
---

# cube-tray

- **`tray/`** — `cube-tray`, the cube in the bar of the desktop, and
  **two processes rather than one**: the icon holds no cube and draws
  none, a `cube-cast` of its own is opened with it, and the two meet
  nowhere but on the stream they both subscribe to — which is exactly
  what a publisher binding for everybody is for. They are two because
  they are two loops, glfw wanting the thread that opened its window
  and the bus wanting one of its own, and the split is what spares this
  client an OpenGL stack it would carry to draw twenty-two pixels. The
  window is opened `--transparent`, which is already the popup: no
  decoration, no background, floating above what it is glanced at over.
  **The window is shown and hidden, never opened and closed**, and that
  is not an optimisation but the only way it can be right: a cube
  describes itself when it connects and *announces its departure and
  never its arrival*, so `cube.facelets` is published once and a window
  started in the middle of a session hears it never — `present` stays
  false, and the ball core is alone in it until the cube connects
  again. A window opened with the icon has heard all of it, and it goes
  on hearing it while nobody looks: `--managed` is what makes it one,
  and a click is a word on a pipe rather than a process, a context and
  a first frame. What a hidden window costs is `GlfwHost.idle()`, which
  advances the cube and draws nothing — the drawing is the GPU half of
  a frame and the only half a hidden window can do without.
  **Where it opens is the compositor's business and nobody else's** —
  the tray protocol never says where a shell drew the icon, so a window
  under it cannot be aimed at, and a placement guessed at is a window
  landing somewhere else on the next screen. `Ctrl` drag carries it,
  and a window hidden rather than closed comes back where it was left.
  **Following a cube is not a state of that window**, and it is what
  lets `--auto` be a checkbox next to the gesture rather than a third
  word inside it: `popup.shown` says whether the window is up, `auto`
  says who is putting it there, and two lines answering two questions
  never contradict each other the way one line with three states
  would. What is followed is the **transition** of the link and never
  its level — a cube that is there says so tens of times a second, and
  a window shown on each of them is a window shown for nothing — which
  is also what leaves a hand free in between: shown and hidden by
  clicks that the next arrival or departure simply overrides. What it
  does not survive is that hand. `toggle()` clears the box, because a
  window asked for by a click is a window somebody is deciding about
  and a box left ticked over one the cube is about to take back is a
  box that lied; and it is exactly why **the automatic side never goes
  through `toggle()`** — a following that cleared its own box on the
  way out would last one single cube. A departure is answered
  `BLAST_DELAY` late, and that is the one number here that is about
  the *other* client: `cube-cast` blows the cube apart when the link
  drops, and that blast is the whole of what a window has to say about
  a cube that is gone, so hiding on the very message that ended the
  link hides the one picture worth showing. It is written above the
  animation rather than imported from it — reaching into the viewer
  for a duration would drag cubing-algs and an OpenGL stack into a
  process that draws twenty-two pixels. The link is read in `follow()`
  at the turn of the loop and never in the stream, the arrangement
  every thread boundary of this repository is made of, and the clock
  is **handed to it** rather than read inside it: a delay measured by
  the caller is one the suite walks through instead of waiting out.
  Nothing is ever reopened by `settle()`, whatever the box says — a
  window that died once dies again, and a following answering its
  death by opening it back is a loop rather than a client.
  The box is `toggle-type` and `toggle-state` on the wire, and those
  two are the reason to read `dbusMenu.js` again rather than guess:
  GNOME draws the tick off the state and only where the type says
  there is one, and it redraws it on either of them arriving — so the
  tick travels in `ItemsPropertiesUpdated` like the labels do, which
  is the same rule that was learned the hard way there. `checked` is
  `None` and not `False` on every other line, what is not sent being
  what a shell draws with its own defaults: a cleared checkmark on
  each of them indents the whole menu behind a column of nothing.
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
