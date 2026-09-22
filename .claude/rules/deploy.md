---
paths:
  - "deploy/**"
---

# Deployment

`deploy/` is what starts `cube-tray` with the session, and it is a
**template and a script** rather than a unit: the file that is
versioned names no path at all — `__ROOT__`, `__PROGRAM__` and
`__ARGUMENTS__` are stamped into a copy by `install.sh` — because a
unit holding the path of one machine is a unit that is wrong on the
next, and a checkout run from where it was cloned is exactly such a
machine. The program is looked for **beside the checkout before the
`PATH`**, the very rule `cast_program()` is written on and for the
same reason: a tray of one virtualenv opening the window of another is
two versions of this repository in one picture. It is wanted by
`graphical-session.target` and never by `default.target` — a bus and a
display are what an icon and its window are made of, and neither
exists before gnome-session hands them to the user manager — and
`PartOf=` is what takes the window away with the session, the end of
the pipe being the third order. `Restart=on-failure` is **not about
crashes**: the tray of GNOME is an extension of the shell rather than
a unit, so `register()` is answered while there is still no watcher to
answer it and the client stops as it is written to, which makes the
retry the whole of what puts an icon up at login. The window needs no
such thing, being opened by the tray rather than by the session:
`cube-cast` is started by `Popup.launch()` and closed by the pipe, and
a unit of its own would be a second one nothing shows. Nothing here is
tested and nothing imports it, as in `publishers/`: what it is worth
is read in the bar it puts the icon in.
