# Security

HyprTile Equalizer manages window geometry for a single user on their own
Hyprland session. It is not a network service and stores no credentials. This
file documents the trust boundary and the hardening measures the plugin applies.

## Trust model

- The plugin runs as the invoking user and talks only to that user's own
  Hyprland instance over local Unix sockets.
- The threat model is a **same-machine process** that could plant files,
  sockets, or symlinks in user-writable locations, or spam the Hyprland event
  stream, in order to feed the watcher crafted input.
- Hyprland itself and the compositor-side socket endpoints are trusted.

## Hardening

### No shell execution

The plugin never shells out. All process spawning uses `subprocess` with an
explicit argument list (`shell=False`), fixed absolute tool paths, a locked
`PATH=/usr/bin` environment, output caps, and timeouts. There is no
`os.system`, `os.popen`, `eval`, or dynamic module loading.

### Socket trust checks

- The Hyprland instance signature must be alphanumeric and the runtime
  directory must be the user's own, owned by them.
- Both the event socket (`.socket2.sock`) and the command socket (`.socket.sock`)
  are resolved with `realpath` and rejected unless they land on the exact
  expected path under the user's `XDG_RUNTIME_DIR`, are real `S_ISSOCK`
  sockets, and are owned by the invoking uid. Symlink redirects or planted
  sockets cause the watcher to refuse to connect (falling back to `hyprctl`).

### Strict input validation

- Every dispatch command passes a single validated chokepoint that coerces
  window addresses to a strict `0x` hexadecimal form and window geometry to
  bounded integers; anything else is dropped.
- Event lines are parsed against a fixed grammar and only recognized window
  events are acted on; unrecognized or malformed lines are ignored.
- The event loop drains at most `MAX_EVENT_LINES_PER_TICK` lines per tick, so
  a hostile event burst cannot starve the layout loop.

### Local-file safety

- State persists under `~/.local/state/hyprtile.equalizer/` in a private
  `0700` directory; reads and writes are opened with `O_NOFOLLOW`, writes go
  through a temp file plus atomic rename, and a lock guards concurrent access.
- The `SUPER+E` binding is the plugin's only edit to the user's Hyprland
  config. It lives inside `~/.config/hypr/bindings.lua` delimited by explicit
  begin/end markers, is applied atomically, and is removed when the plugin is
  disabled or removed.
- The binding service resolves the config location from the passwd database
  (never `$HOME`) and walks `~`, `~/.config`, and `~/.config/hypr` one
  component at a time. Every component must be a real directory owned by the
  invoking user and not group/world-writable; a symlinked or swapped ancestor
  aborts the operation.
- `bindings.lua` / `autostart.lua` are read through the verified directory's
  file descriptor with `O_NOFOLLOW` and must be singly-linked regular files
  owned by the user. Updates are staged and fsynced inside the same directory,
  then committed with `renameat2` as a compare-and-swap that refuses to
  clobber concurrent edits; a failing half of the two-file update is rolled
  back. A user-owned lock file serializes the read-modify-write cycle.

## Reporting

Security issues can be reported by opening an issue on the
[upstream repository](https://github.com/davidhbigelow/hyprtile.equalizer).