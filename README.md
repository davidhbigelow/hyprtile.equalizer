# hyprtile.equalize

## A simple Plugin for Omarchy Quatro
Inspiration after seeing a great idea to address some accepted friction with Hyprland.

https://www.youtube.com/watch?v=KO2T0oET9go


## What it does
- SUPERKEY + E = Toggle from Default Hyprland Tile Layout to Equal Window Size Layout.

<table>
  <tr>
    <th>BEFORE/AFTER Toggle</th>
    <th>BEFORE/AFTER Toggle</th>
  </tr>
  <tr>
    <td><img width="3838" height="2400" alt="allWindows" src="https://github.com/user-attachments/assets/cd48e948-4de1-4fe1-9c62-549770b02b95" /></td>
    <td><img width="3838" height="2400" alt="allWindows2" src="https://github.com/user-attachments/assets/1f525cc6-4cf3-4d39-a234-c2ae1217b6f7" /></td>
  </tr>
</table>






Floating grid equalizer for Hyprland desktops. The toolbar toggle and
`SUPER+E` keybinding keep whichever workspace you opt into a perfectly tiled,
floating grid that re-centers windows after drags/resizes and restores normal
tiling when you turn it off.

## Highlights
- Live per-workspace equalize: opt specific desktops into grid mode; others
  remain stock Hyprland.
- Drop-aware layout: dragging a window to a new slot re-balances the grid
  around the drop target after a short debounce.
- Resize pinning: when you resize a tile with `SUPER +/-`, that tile keeps the
  new size while the rest of the grid re-equalizes around it.
- Clean toggle-off: turning equalize off de-floats every window on the
  desktop in one batch, and Hyprland's native layout engine re-tiles the
  workspace from scratch (no reconstruction, nothing left stranded).
- Toolbar toggle button mirrors the keyboard shortcut and shows the current
  state via the icon glyph (grid vs dashboard).
- Optional "Fill leftover space" mode stretches a tile to cover the unused
  slot when a grid row is incomplete. The stretch direction is a picker
  (`off` | `horizontal` | `vertical`): horizontal widens the bottom-right tile
  to the row end, vertical pulls the tile above the empty corner down to the
  bottom of the work area. Changing direction adjusts only the affected
  tile(s) in place, without re-laying-out the grid.

## Requirements
- Hyprland with the `hl.dsp.*` dispatch helpers (0.44+ recommended).
- Omarchy shell / Quickshell 1.6+ (any recent Omarchy build works).
- `python3`, `bash`, and the `hyprctl` CLI in `PATH`.

## Installation
1. Copy this folder to `~/.config/omarchy/plugins/hyprtile.equalize/`. The
   plugin hot-reloads from this location; no omarchy command is required.
2. Run `~/.config/omarchy/plugins/hyprtile.equalize/install.sh`.
   - Adds/updates the `SUPER+E` binding that calls `scripts/equalize-toggle`.
   - Adds an autostart entry for the `scripts/equalize-watch` daemon.
   - Reloads Hyprland (if running) and restarts the watcher in-place.
3. Add the widget to your bar if it did not show up automatically:
   `omarchy plugin enable hyprtile.equalize --section right --index end`.

### Re-adding after Omarchy removal
If you removed the plugin through the Omarchy plugin manager, the shell forgets
its manifest and bar placement. To bring it back without restarting the whole
shell:

1. Copy/clone this repo into `~/.config/omarchy/plugins/hyprtile.equalize/`.
2. Re-run `~/.config/omarchy/plugins/hyprtile.equalize/install.sh`.
3. Refresh the shell's plugin index: `omarchy-shell shell rescanPlugins`.
4. Re-enable the bar widget: `omarchy plugin enable hyprtile.equalize --section right --index end`.

Those commands only touch this plugin; other widgets keep running.

The plugin lives entirely inside that directory. Removing it and deleting the
lines the installer appended to `hypr/bindings.lua` and `hypr/autostart.lua`
uninstalls it cleanly.

## Usage
- Toggle with the toolbar button or `SUPER+E`. Each desktop remembers its own
  state so you can leave development workspaces equalized while keeping others
  untouched.
- When live-equalize turns off, every window on the desktop is de-floated in
  one batch and Hyprland's native tiling takes over again.
- All helper scripts live under `scripts/` and are referenced by absolute path
  so the plugin remains self-contained. You can run them manually while
  developing (e.g., `scripts/equalize-watch --help`).
- Click the toolbar icon to open a mini control panel. From there you can
  toggle live equalize and pick the "Fill leftover space" direction with a
  segmented control: `Off` leaves incomplete rows as they are, `Horizontal`
  widens the last tile to the row end, and `Vertical` pulls the tile above
  the empty corner down to the bottom of the work area. Changing the
  direction adjusts only the affected tile in place.
- The same setting is scriptable from the command line:
  `scripts/equalize-settings get fill-remainder`,
  `scripts/equalize-settings set fill-remainder vertical` (or
  `horizontal`/`off`), and `scripts/equalize-settings list` dumps all
  settings as JSON. A legacy `true`/`false` value resolves to
  `horizontal`/`off`.

## Packaging a Release Tarball
Run `./package.sh` from this directory. The script:

1. Reads the version from `manifest.json`.
2. Creates `dist/hyprtile.equalize-<version>.tar.gz` containing:
   `manifest.json`, `LICENSE`, `EqualizeToggle.qml`, `install.sh`, `scripts/`,
   and this README under a top-level `hyprtile.equalize/` folder.

You can share that archive directly; the recipient only needs to unpack it into
`~/.config/omarchy/plugins/` and run the bundled `install.sh`.

## Development Tips
- `scripts/equalize-watch` prints Python tracebacks to stderr; run it manually
  from a terminal to debug without the installer auto-restarting it.
- Hyprland configuration changes (`bindings.lua` / `autostart.lua`) reload via
  `hyprctl reload`; the installer already runs this, but it is safe to re-run
  while iterating.
- The shell plugin auto-reloads on save; if Quickshell somehow caches the old
  code, run `omarchy restart shell`.

## Changelog

### 1.1.0
- New: "Fill leftover space" is now a direction picker (`off` |
  `horizontal` | `vertical`) with a segmented control in the panel widget.
  Changing the direction stretches only the affected tile in place instead of
  re-laying-out the whole grid. The legacy boolean setting resolves to
  `horizontal`.
- Fixed: vertical fill no longer triggers a transient off-screen re-fit of the
  bottom row; the watcher now refreshes its size cache after applying a fill
  and suppresses events it generated itself.
- Toggle-off now returns windows to native Hyprland tiling with a single
  batched de-float (no snapshot reconstruction).
- Hardening (from the plugin review):
  - Strict validation is enforced at the `dispatch()` boundary: every window
    address must be a bare `0x` hex id and every geometry value an integer,
    and the whole command must match a narrow `hl.dsp.window.*` grammar
    before it is sent to Hyprland.
  - The watcher lifecycle is verified against `/proc` (cmdline realpath plus
    process start-time fingerprint), so a recycled PID can never be signaled;
    there are no `ps` substring scans anywhere.
  - All state writes (workspace set, config, PID record, snapshots) are
    atomic (`mkstemp` + `os.replace`), size-capped, `fsync`'d, and guarded by
    dedicated `flock` lock files; reads are bounded and use `O_NOFOLLOW` in a
    private `0700` state directory.
  - The long-lived watcher caps `hyprctl` calls with a hard timeout and an
    output-size limit, and processes at most a bounded number of socket
    events per loop tick, so an event flood can never make one iteration do
    unbounded work.
