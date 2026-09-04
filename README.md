# Equalize Toggle

Toggle live window-equalize mode on any Hyprland workspace with `SUPER+E`.
Press once to lock every window into a perfectly tiled floating grid; press
again to return to normal Hyprland tiling.

<table>
  <tr>
    <th>Normal Hyprland Tiling</th>
    <th>Equalized (SUPER+E)</th>
  </tr>
  <tr>
    <td><img width="3838" height="2400" alt="Normal tiling" src="https://github.com/user-attachments/assets/cd48e948-4de1-4fe1-9c62-549770b02b95" /></td>
    <td><img width="3838" height="2400" alt="Equalized grid" src="https://github.com/user-attachments/assets/1f525cc6-4cf3-4d39-a234-c2ae1217b6f7" /></td>
  </tr>
</table>

---

## Install

After the plugin is placed in `~/.config/omarchy/plugins/hyprtile.equalize/`:

```bash
~/.config/omarchy/plugins/hyprtile.equalize/install.sh
```

Then enable the bar widget:

```bash
omarchy plugin enable hyprtile.equalize --section right --index end
```

The installer adds the `SUPER+E` binding, sets up a systemd-supervised
autostart for the watcher, and reloads Hyprland. It rolls back automatically
if anything fails.

### Re-adding after removal

If you removed the plugin through the Omarchy plugin manager:

1. Copy/clone the repo into `~/.config/omarchy/plugins/hyprtile.equalize/`.
2. Run `~/.config/omarchy/plugins/hyprtile.equalize/install.sh`.
3. `omarchy-shell shell rescanPlugins`
4. `omarchy plugin enable hyprtile.equalize --section right --index end`

---

## What it does

- Press `SUPER+E` or click the toolbar icon to toggle equalize on the current
  workspace. Each desktop remembers its own state independently.
- When equalize turns off, every window is de-floated in one batch and
  Hyprland's native tiling takes over again.
- All helper scripts live under `scripts/` and are referenced by absolute path
  so the plugin is fully self-contained.

---

## Features

- **Per-workspace toggle** -- opt specific desktops into grid mode while
  others remain stock Hyprland.
- **Drop-aware layout** -- dragging a window to a new slot re-balances the
  grid around the drop target after a short debounce.
- **Resize pinning** -- resizing a tile with `SUPER +/-` keeps that tile's
  new size while the rest of the grid re-equalizes around it.
- **Clean toggle-off** -- turning equalize off de-floats every window and
  Hyprland re-tiles from scratch; nothing is left stranded.
- **Toolbar widget** -- mirrors the keyboard shortcut and shows current state
  via icon glyph (grid vs dashboard).
- **Fill leftover space** -- a segmented control in the panel lets you choose
  `Off`, `Horizontal`, or `Vertical` to stretch a tile across the unused slot
  in an incomplete row.

---

## Configuration

The "Fill leftover space" direction is available in the toolbar panel and
from the command line:

```bash
scripts/equalize-settings get fill-remainder
scripts/equalize-settings set fill-remainder vertical   # or horizontal / off
scripts/equalize-settings list                          # dump all settings as JSON
```

A legacy `true`/`false` value resolves to `horizontal`/`off`.

---

## Requirements

- Hyprland 0.44+ with `hl.dsp.*` dispatch helpers.
- Omarchy shell / Quickshell 1.6+ (any recent Omarchy build).
- `/usr/bin/python3`, `/usr/bin/hyprctl`, systemd user manager.

---

## Uninstall

1. Remove the plugin directory:
   `rm -rf ~/.config/omarchy/plugins/hyprtile.equalize/`
2. Delete the lines the installer appended to `hypr/bindings.lua` and
   `hypr/autostart.lua`, or re-source your config with
   `hyprctl reload`.

---

## Development

- Run `scripts/equalize-watch` manually from a terminal to see tracebacks on
  stderr.
- Hyprland config changes reload via `hyprctl reload`; the installer does
  this automatically.
- The shell plugin auto-reloads on save; if Quickshell caches old code, run
  `omarchy restart shell`.

---

## Changelog

### 1.1.2
- Installer-managed configuration uses explicit begin/end markers. Only
  those blocks and narrowly identified historical plugin blocks are replaced;
  unrelated lines mentioning equalize helpers are preserved.
- Existing files are atomically exchanged with the staged update, then the
  displaced version is validated against the version originally read and
  restored on mismatch.

### 1.1.1
- Hardened installer: fixed trusted paths, type/ownership checks, atomic
  replace with rollback on Hyprland reload failure.
- Replaced detached `nohup` watcher with a systemd-supervised transient
  user service. Legacy autostart entries are migrated automatically.

### 1.1.0
- "Fill leftover space" is now a direction picker (`off` | `horizontal` |
  `vertical`) with a segmented control in the panel.
- Toggle-off returns windows to native Hyprland tiling with a single batched
  de-float.
- Security hardening: strict dispatch validation, `/proc`-verified watcher
  lifecycle, atomic state writes with `flock`, bounded `hyprctl` timeouts.
