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

The standard Omarchy install from the plugin marketplace:

```bash
omarchy plugin add https://github.com/davidhbigelow/hyprtile.equalizer.git --enable
```

That clones the plugin, places its toolbar widget in the bar, and enables it.
No installer script and no extra steps: enabling the plugin registers the
`SUPER+E` toggle and equalize-aware `SUPER+SHIFT+Arrow` movement bindings,
starts the layout watcher, and rolls everything back when the plugin is
disabled.

You can place the widget in a specific section:

```bash
omarchy plugin enable hyprtile.equalize --section right --index end
```

### How it manages itself

- The toggle and four directional movement bindings live in
  `~/.config/hypr/bindings.lua` inside a
  `-- BEGIN/END hyprtile.equalize managed block`. The plugin writes or updates
  that block when enabled and removes it when disabled, so the binding always
  matches the running plugin location and never leaves a dead shortcut behind.
- The layout watcher is spawned by the Omarchy shell (the plugin declares a
  `service` entry point). It stops when the Hyprland session ends, when the
  plugin is disabled, or when the plugin is removed.
- Disabling the plugin (`omarchy plugin disable hyprtile.equalize`) or removing
  it always restores your `bindings.lua` to its previous contents.

### Troubleshooting

- If the binding or watcher ever seems stale after a manual config edit, run
  `scripts/equalize-binding ensure` from the plugin directory to re-sync, or
  simply restart the shell: `omarchy restart shell`.

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
- **Localized resizing** -- `SUPER +/-` adjusts width within the active row;
  `SUPER+SHIFT +/-` adjusts shared row heights. Neighboring tiles absorb the
  change without rebuilding unrelated rows.
- **Geometry-aware movement** -- `SUPER+SHIFT+Arrow` swaps logical slots,
  including incomplete stretched rows. Windows inherit destination geometry,
  and app minimum sizes are measured before the move is displayed.
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
- `/usr/bin/python3` and `/usr/bin/hyprctl`.

---

## License

MIT — see [`LICENSE`](./LICENSE). Copyright (c) 2026 David Bigelow.

---

## Development

- Run `scripts/equalize-watch` manually from a terminal to see tracebacks on
  stderr.
- `scripts/equalize-binding` manages the binding lifecycle; inspect its state
  with `scripts/equalize-binding status`.
- Run the test suite with `python3 -m unittest discover -s tests -v`.
- The shell plugin auto-reloads on save; if Quickshell caches old code, run
  `omarchy restart shell`.

---

## Changelog

### 1.3.0
- Replaced column-wide resize pinning with persistent slot geometry: width
  changes stay within one row, while height changes rebalance complete row
  bands without overlap.
- Added equalize-aware `SUPER+SHIFT+Arrow` movement. Keyboard swaps target the
  next occupied logical slot, preserve stretched remainder behavior, and fall
  back to Hyprland's native swap outside equalize mode.
- Windows now inherit destination-slot geometry during keyboard and pointer
  moves. A fast preflight measures application minimum sizes and adjusts
  neighboring slots before displaying the move.
- Preserved custom layout state independently per equalized workspace and
  repaired marked grids if an external event unexpectedly de-floats a tile.
- Added a private, per-Hyprland-instance Unix socket for validated local
  movement requests bound to the initiating workspace and focused window.
- Added geometry, movement, minimum-size, socket-trust, and binding regression
  coverage.
- Reworked automatic state storage to walk owner-checked, no-follow directory
  descriptors and publish every state file atomically relative to the verified
  state directory, closing ancestor and destination-swap races.

### 1.2.2
- Moving a window from an equalized workspace now re-balances the source
  workspace and adapts the window to the target workspace's state.
- Windows moved to native or newly-created workspaces are de-floated so
  Hyprland tiles them normally instead of preserving their old equalized
  geometry.
- Windows moved into an already-equalized workspace are incorporated into its
  grid, including when the active workspace changes before the move event is
  processed.
- Fixed Hyprland event-address parsing: bare hexadecimal addresses from the
  event socket are now normalized to canonical `0x...` addresses.

### 1.2.1
- Hardened the binding service against config-location attacks: the
  `SUPER+E` binding is now written through a descriptor-relative, owner-checked
  transaction. `~/.config/hypr` is walked component-by-component with
  `O_NOFOLLOW`, each directory must be user-owned and not group/world-writable,
  config files must be singly-linked user-owned regular files, and updates are
  committed with an atomic `renameat2` compare-and-swap with rollback.

### 1.2.0
- Marketplace-standard installation: the plugin is now added entirely with
  `omarchy plugin add <repo>.git --enable`. The installer script and the
  systemd-supervised watcher autostart are gone.
- The plugin declares a `service` entry point: the Omarchy shell launches the
  layout watcher when the plugin is enabled and stops it when it is disabled.
- The `SUPER+E` binding is managed idempotently inside `bindings.lua` with
  explicit markers and an atomic swap, replacing legacy entries from the old
  installer on first run.

### 1.1.4
- Hardened the Hyprland socket trust: the watcher now refuses to read or write
  sockets that are not real, self-owned sockets resolving to the exact path
  under the user's `XDG_RUNTIME_DIR`, and falls back to `hyprctl` if the
  command socket fails the check.
- Added [`SECURITY.md`](./SECURITY.md) documenting the trust model and the
  input-validation, no-shell, and local-file hardening applied throughout.

### 1.1.3
- Equalized grids now fit apps that refuse to shrink below a minimum size
  (e.g. Krita): columns and rows grow to fit them and flexible tiles split
  the leftover, so oversized windows no longer overlap their neighbours.
- Toggling equalize mode applies the layout exactly once — move/float events
  generated by the apply no longer trigger a second, visible re-layout.
- Fixed a race where the fresh grid could fight with windows still settling
  into floating mode after the toggle.
- Marketplace listing: rewritten install-first README, preview image, and
  license documented in both `manifest.json` and the README.

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
- Replaced a detached helper-spawn with a supervised lifecycle. Legacy
  autostart entries are migrated automatically.

### 1.1.0
- "Fill leftover space" is now a direction picker (`off` | `horizontal` |
  `vertical`) with a segmented control in the panel.
- Toggle-off returns windows to native Hyprland tiling with a single batched
  de-float.
- Security hardening: strict dispatch validation, `/proc`-verified watcher
  lifecycle, atomic state writes with `flock`, bounded `hyprctl` timeouts.
