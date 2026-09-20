#!/usr/bin/env bash
#
# Install (or refresh) the cube-tray systemd user service.
#
# The unit is a template: the program and the arguments of the window
# are stamped in here so the checked-in file stays free of anything
# machine-specific.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/cube-tray.service"

# What is typed after the program, the window included: everything
# after -- is handed to cube-cast as it stands.
#     CUBE_TRAY_ARGUMENTS='-w 320x320 -- --palette rgb' deploy/install.sh
ARGUMENTS="${CUBE_TRAY_ARGUMENTS:-}"

# The client next to this checkout wins over the one on the PATH, for
# the very reason cast_program() prefers it: a tray installed in a
# virtualenv opens the window of that virtualenv, where the PATH may
# well name another one - or an older one, which is worse than none.
if [ -x "$ROOT/bin/cube-tray" ]; then
    PROGRAM="$ROOT/bin/cube-tray"
else
    PROGRAM="$(command -v cube-tray || true)"
fi

if [ -z "$PROGRAM" ]; then
    echo "cube-tray is missing: run 'pip install .[tray]' first." >&2
    exit 1
fi

mkdir -p "$UNIT_DIR"
sed -e "s|__ROOT__|$ROOT|g" \
    -e "s|__PROGRAM__|$PROGRAM|g" \
    -e "s|__ARGUMENTS__|$ARGUMENTS|g" \
    "$ROOT/deploy/cube-tray.service" > "$UNIT"

systemctl --user daemon-reload
systemctl --user enable --now cube-tray.service

# An icon registers with org.kde.StatusNotifierWatcher, and on GNOME
# that name is owned by the AppIndicator extension rather than by the
# shell: without one the client stops on every try instead of running
# with nothing to show, and the unit is what keeps trying.
if ! busctl --user status org.kde.StatusNotifierWatcher >/dev/null 2>&1; then
    echo
    echo "No system tray on this session: cube-tray has nowhere to register."
    echo "On GNOME, turn the AppIndicator extension on with:"
    echo "    gnome-extensions enable ubuntu-appindicators@ubuntu.com"
fi

echo
systemctl --user --no-pager status cube-tray.service || true
