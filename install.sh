#!/bin/bash
#
# Make the hyprtile.equalize plugin self-contained on this machine.
#
# The whole feature lives in this one folder:
#   ~/.config/omarchy/plugins/hyprtile.equalize/
#     ├── manifest.json        # shell plugin manifest (bar widget)
#     ├── EqualizeToggle.qml   # toolbar toggle (runs scripts/ by plugin-relative path)
#     ├── install.sh           # this script
#     └── scripts/
#         ├── equalize-watch   # live grid watcher (autostart + SUPER+E backend)
#         ├── equalize-toggle  # SUPER+E handler / toolbar click
#         └── equalize-state   # reports active-workspace equalize state to the icon
#
# Running this script wires the Hyprland keybinding and autostart to this
# folder's absolute paths. It is idempotent: safe to run again (it will not
# duplicate lines), and safe on a machine where the plugin already works.
#
# Usage: ~/.config/omarchy/plugins/hyprtile.equalize/install.sh

set -euo pipefail

PLUG_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$PLUG_DIR/scripts"
BINDINGS="$HOME/.config/hypr/bindings.lua"
AUTOSTART="$HOME/.config/hypr/autostart.lua"
HYPR_SOCKET="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/hypr/${HYPRLAND_INSTANCE_SIGNATURE}/.socket2.sock"

chmod +x "$SCRIPTS_DIR"/equalize-* 2>/dev/null || true

BIND_LINE="o.bind(\"SUPER + E\", \"Toggle live equalize mode\", \"$SCRIPTS_DIR/equalize-toggle\")"
AUTO_LINE="o.exec_on_start(\"nohup $SCRIPTS_DIR/equalize-watch >/dev/null 2>&1 &\")"

echo "Plugin: $PLUG_DIR"
echo "Wiring SUPER+E and autostart into Hyprland config..."

if [[ ! -f "$BINDINGS" ]]; then
  echo "  warning: $BINDINGS missing; creating it"
  mkdir -p "$(dirname "$BINDINGS")"
  touch "$BINDINGS"
fi
if ! grep -qF "equalize-toggle" "$BINDINGS"; then
  {
    echo ""
    echo "-- hyprtile.equalize: toggle live grid (SUPER + E)"
    echo "$BIND_LINE"
  } >> "$BINDINGS"
  echo "  added binding to $BINDINGS"
else
  echo "  binding already present ($BINDINGS); leaving as-is"
fi

if [[ ! -f "$AUTOSTART" ]]; then
  echo "  warning: $AUTOSTART missing; creating it"
  mkdir -p "$(dirname "$AUTOSTART")"
  touch "$AUTOSTART"
fi
if ! grep -qF "equalize-watch" "$AUTOSTART"; then
  {
    echo ""
    echo "-- hyprtile.equalize: live grid watcher"
    echo "$AUTO_LINE"
  } >> "$AUTOSTART"
  echo "  added autostart to $AUTOSTART"
else
  echo "  autostart already present ($AUTOSTART); leaving as-is"
fi

# Validate Hyprland config and apply, only if Hyprland is running.
if [[ -S "$HYPR_SOCKET" ]]; then
  hyprctl reload >/dev/null 2>&1 || true
  if ! hyprctl configerrors 2>/dev/null | grep -qi "error"; then
    echo "  Hyprland reloaded with no config errors."
  else
    echo "  warning: Hyprland config errors reported; please check 'hyprctl configerrors'."
  fi
else
  echo "  Hyprland not running right now; config will apply at next login."
fi

# (Re)start the watcher in the background, detached from this script's session.
start_watcher() {
  python3 - "$SCRIPTS_DIR/equalize-watch" <<'PY'
import os, signal, subprocess, sys, time
watch = sys.argv[1]
self, ppid = os.getpid(), os.getppid()
out = subprocess.run(["ps","-eo","pid,args"], capture_output=True, text=True).stdout
for line in out.splitlines():
    parts = line.split(None, 1)
    if len(parts) < 2:
        continue
    try:
        pid = int(parts[0])
    except ValueError:
        continue
    if pid in (self, ppid):
        continue
    if "equalize-watch" in parts[1] and "python3" in parts[1]:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
time.sleep(0.5)
subprocess.Popen([watch], start_new_session=True,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                 stdin=subprocess.DEVNULL)
PY
}
if [[ -S "$HYPR_SOCKET" ]]; then
  start_watcher
  echo "  watcher restarted ($SCRIPTS_DIR/equalize-watch)."
else
  echo "  watcher will start at next login (Hyprland not running)."
fi

echo "Done. The equalize feature is now this single folder: $PLUG_DIR"
