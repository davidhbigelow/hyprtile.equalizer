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
- Installer writes are transactional: configuration edits are bounded by
  explicit begin/end markers and replaced atomically (`RENAME_EXCHANGE`),
  and the lifecycle unit is a transient user systemd service.

## Reporting

Security issues can be reported by opening an issue on the
[upstream repository](https://github.com/davidhbigelow/hyprtile.equalizer).