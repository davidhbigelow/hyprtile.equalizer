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
- Session-remembered layouts: toggling off/on without changing the tile set
  restores the exact (x, y, w, h) layout that was last organized.
- Toolbar toggle button mirrors the keyboard shortcut and shows the current
  state via the icon glyph (grid vs dashboard).
- Optional "Fill leftover space" mode stretches the last tile to cover the
  unused slot when a grid row is incomplete.

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
- When live-equalize turns off, the active tile is briefly emphasized before
  every window returns to stock tiling.
- All helper scripts live under `scripts/` and are referenced by absolute path
  so the plugin remains self-contained. You can run them manually while
  developing (e.g., `scripts/equalize-watch --help`).
- Click the toolbar icon to open a mini control panel. From there you can
  toggle live equalize and enable/disable the "Fill leftover space" option,
  which widens the last tile to fill any empty slot in the grid when the window
  count leaves a gap.

## Packaging a Release Tarball
Run `./package.sh` from this directory. The script:

1. Reads the version from `manifest.json`.
2. Creates `dist/hyprtile.equalize-<version>.tar.gz` containing:
   `manifest.json`, `EqualizeToggle.qml`, `install.sh`, `scripts/`, and this
   README under a top-level `hyprtile.equalize/` folder.

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
