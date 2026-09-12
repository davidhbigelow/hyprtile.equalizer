#!/usr/bin/python3
"""Shared state helpers for HyprTile equalizer scripts.

This module centralizes access to the private state directory, which keeps the
set of equalized workspace ids as well as the watcher PID/lock files. The
directory lives under XDG_STATE_HOME (fallback: ~/.local/state) and is created
with mode 700 so no other users can interfere with its contents.
"""

from __future__ import annotations

import fcntl
import json
import os
import pwd
import secrets
import stat
import time
from typing import Callable, Iterable, Optional, Set

STATE_HOME = os.environ.get("XDG_STATE_HOME") or os.path.join(
    pwd.getpwuid(os.getuid()).pw_dir, ".local", "state"
)
STATE_DIR = os.path.join(STATE_HOME, "hyprtile.equalizer")
WORKSPACE_FILE = os.path.join(STATE_DIR, "equalized-workspaces")
PID_FILE = os.path.join(STATE_DIR, "watcher.pid")
LOCK_FILE = os.path.join(STATE_DIR, "watcher.lock")
CONFIG_FILE = os.path.join(STATE_DIR, "config.json")
# Dedicated, never-replaced lock files guaranteeing mutual exclusion across
# readers and writers even when the data files are atomically replaced.
WORKSPACE_LOCK = os.path.join(STATE_DIR, "workspaces.lock")
CONFIG_LOCK = os.path.join(STATE_DIR, "config.lock")

MAX_SET_BYTES = 64 * 1024
MAX_PID_BYTES = 4 * 1024
MAX_CONFIG_BYTES = 32 * 1024
MAX_SNAPSHOT_BYTES = 256 * 1024

CONFIG_DEFAULTS = {
    "fill_remainder": "off",
}

# Valid values for the fill_remainder choice: how the last/above-empty tile is
# stretched to consume leftover workspace space.
FILL_CHOICES = ("off", "horizontal", "vertical")


def _secure_flags(flags: int) -> int:
    flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW  # type: ignore[attr-defined]
    return flags


def _open_state_dir(create: bool = True) -> int:
    """Open the private state directory without following any path symlink."""
    path = os.path.abspath(STATE_DIR)
    if not path.startswith(os.sep):
        raise OSError("state directory must be absolute")
    uid = os.getuid()
    fd = os.open(os.sep, _secure_flags(os.O_RDONLY | os.O_DIRECTORY))
    try:
        for component in (part for part in path.split(os.sep) if part):
            try:
                child = os.open(
                    component,
                    _secure_flags(os.O_RDONLY | os.O_DIRECTORY),
                    dir_fd=fd,
                )
            except FileNotFoundError:
                if not create:
                    os.close(fd)
                    return -1
                os.mkdir(component, 0o700, dir_fd=fd)
                child = os.open(
                    component,
                    _secure_flags(os.O_RDONLY | os.O_DIRECTORY),
                    dir_fd=fd,
                )
            info = os.fstat(child)
            writable = info.st_mode & 0o022
            sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in (0, uid)
                or (writable and not sticky_root)
            ):
                os.close(child)
                raise OSError("unsafe state directory component")
            os.close(fd)
            fd = child
        final = os.fstat(fd)
        if final.st_uid != uid:
            raise OSError("state directory must be user-owned")
        os.fchmod(fd, 0o700)
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_regular(dir_fd: int, name: str, flags: int, mode: int = 0o600) -> int:
    fd = os.open(name, _secure_flags(flags), mode, dir_fd=dir_fd)
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_nlink != 1
        or info.st_mode & 0o022
    ):
        os.close(fd)
        raise OSError(f"unsafe state file: {name}")
    return fd


def _read_file(dir_fd: int, name: str, max_bytes: int) -> str:
    try:
        fd = _open_regular(dir_fd, name, os.O_RDONLY)
    except FileNotFoundError:
        return ""
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        data = handle.read(max_bytes + 1)
    return data if len(data) <= max_bytes else ""


def _atomic_write(dir_fd: int, name: str, text: str, max_bytes: int) -> bool:
    """Write `text` to `name` atomically and enforce a size cap.

    The bytes are staged under an unpredictable exclusive name (0600) in the
    open private-state descriptor, fsync'd, then published with a
    descriptor-relative `os.replace`.
    This guarantees a reader never observes a truncated or torn file even if
    the process crashes mid-write, and prevents an unbounded payload from ever
    being persisted. Returns False (and leaves `path` untouched) if the payload
    exceeds `max_bytes`.
    """
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        return False
    tmp_name = f".tmp-{secrets.token_hex(16)}"
    tmp_fd = _open_regular(
        dir_fd, tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    try:
        os.fchmod(tmp_fd, 0o600)
        with os.fdopen(tmp_fd, "wb") as tmp:
            tmp.write(encoded)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        os.fsync(dir_fd)
        return True
    except OSError:
        return False
    finally:
        try:
            os.unlink(tmp_name, dir_fd=dir_fd)
        except FileNotFoundError:
            pass


def _parse_ids(raw: str) -> Set[int]:
    ids: Set[int] = set()
    for token in raw.split():
        token = token.strip()
        if not token:
            continue
        if token.lstrip("-").isdigit():
            try:
                ids.add(int(token))
            except ValueError:
                continue
    return ids


def _read_ids(lock_type: Optional[int]) -> Set[int]:
    dir_fd = _open_state_dir()
    data = ""
    try:
        lock_fd = _open_regular(
            dir_fd, os.path.basename(WORKSPACE_LOCK), os.O_RDWR | os.O_CREAT
        )
    except OSError:
        lock_fd = None
    try:
        if lock_type is not None and lock_fd is not None:
            fcntl.flock(lock_fd, lock_type)
        data = _read_file(dir_fd, os.path.basename(WORKSPACE_FILE), MAX_SET_BYTES)
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            except OSError:
                pass
        os.close(dir_fd)
    return _parse_ids(data)


def load_workspace_ids() -> Set[int]:
    """Return the set of workspace ids currently marked equalized."""

    return _read_ids(fcntl.LOCK_SH)


def _update_ids(mutator: Callable[[Set[int]], Set[int]]) -> Set[int]:
    dir_fd = _open_state_dir()
    try:
        lock_fd = _open_regular(
            dir_fd, os.path.basename(WORKSPACE_LOCK), os.O_RDWR | os.O_CREAT
        )
    except Exception:
        os.close(dir_fd)
        raise
    try:
        os.fchmod(lock_fd, 0o600)
    except OSError:
        pass
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            data = _read_file(dir_fd, os.path.basename(WORKSPACE_FILE), MAX_SET_BYTES)
        except OSError:
            data = ""
        ids = _parse_ids(data)
        new_ids = mutator(set(ids))
        body = ""
        if new_ids:
            body = "\n".join(str(i) for i in sorted(new_ids)) + "\n"
        _atomic_write(dir_fd, os.path.basename(WORKSPACE_FILE), body, MAX_SET_BYTES)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except OSError:
            pass
        os.close(dir_fd)
    return new_ids


def replace_workspace_ids(new_ids: Iterable[int]) -> Set[int]:
    new_set = set(int(i) for i in new_ids)
    return _update_ids(lambda _old: new_set)


def clear_workspace_ids() -> None:
    _update_ids(lambda _old: set())


def toggle_workspace_id(workspace_id: int) -> bool:
    """Toggle workspace_id membership; return True if the id is now enabled."""

    workspace_id = int(workspace_id)
    enabled = False

    def mutate(prev: Set[int]) -> Set[int]:
        nonlocal enabled
        if workspace_id in prev:
            prev.remove(workspace_id)
            enabled = False
        else:
            prev.add(workspace_id)
            enabled = True
        return prev

    _update_ids(mutate)
    return enabled


def workspace_is_equalized(workspace_id: int) -> bool:
    return workspace_id in load_workspace_ids()


def acquire_watcher_lock() -> int:
    """Return an exclusive-lock fd that enforces a single watcher instance."""

    dir_fd = _open_state_dir()
    flags = _secure_flags(os.O_RDWR | os.O_CREAT)
    try:
        fd = _open_regular(dir_fd, os.path.basename(LOCK_FILE), flags, 0o600)
    except Exception:
        os.close(dir_fd)
        raise
    os.close(dir_fd)
    try:
        os.fchmod(fd, 0o600)
    except OSError:
        pass
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise
    return fd


def proc_start_time(pid: int) -> Optional[int]:
    """Return `/proc/PID/stat` field 22 (start time, clock ticks), or None.

    A process ID can be recycled by the kernel, so cmdline/realpath matching
    alone cannot prove a PID still names our own long-running watcher. The
    start time is unique to a process incarnation and is stable for its whole
    life, making it a reliable fingerprint against a PID-reuse race.
    """
    try:
        with open(f"/proc/{int(pid)}/stat", "rb") as handle:
            data = handle.read(4096)
    except (OSError, ValueError):
        return None
    rparen = data.rfind(b")")
    if rparen < 0:
        return None
    fields = data[rparen + 1:].split()
    if len(fields) < 20:
        return None
    # After the ')' of the comm field (field 2), the next field is state
    # (field 3). Field 22 (starttime) is therefore at index 22 - 3 = 19.
    try:
        return int(fields[19])
    except (IndexError, ValueError):
        return None


def write_pid_record(pid: int, script_path: str) -> None:
    record = {
        "pid": int(pid),
        "script": os.path.realpath(script_path),
        "start": proc_start_time(pid),
        "timestamp": time.time(),
    }
    payload = json.dumps(record) + "\n"
    dir_fd = _open_state_dir()
    try:
        _atomic_write(dir_fd, os.path.basename(PID_FILE), payload, MAX_PID_BYTES)
    finally:
        os.close(dir_fd)


def read_pid_record() -> Optional[dict]:
    dir_fd = _open_state_dir(create=False)
    if dir_fd < 0:
        return None
    try:
        data = _read_file(dir_fd, os.path.basename(PID_FILE), MAX_PID_BYTES)
    finally:
        os.close(dir_fd)
    try:
        record = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict):
        return None
    pid = record.get("pid")
    script = record.get("script")
    if not isinstance(pid, int) or not isinstance(script, str):
        return None
    result = {"pid": pid, "script": script}
    ts = record.get("timestamp")
    if isinstance(ts, (int, float)):
        result["timestamp"] = float(ts)
    start = record.get("start")
    if isinstance(start, int):
        result["start"] = start
    return result


def remove_pid_record() -> None:
    dir_fd = _open_state_dir(create=False)
    if dir_fd < 0:
        return
    try:
        try:
            os.unlink(os.path.basename(PID_FILE), dir_fd=dir_fd)
            os.fsync(dir_fd)
        except FileNotFoundError:
            pass
    finally:
        os.close(dir_fd)


def load_config() -> dict:
    dir_fd = _open_state_dir()
    data = ""
    lock_fd = None
    try:
        lock_fd = _open_regular(
            dir_fd, os.path.basename(CONFIG_LOCK), os.O_RDWR | os.O_CREAT
        )
    except OSError:
        pass
    try:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_SH)
        try:
            data = _read_file(dir_fd, os.path.basename(CONFIG_FILE), MAX_CONFIG_BYTES)
        except OSError:
            data = ""
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            except OSError:
                pass
        os.close(dir_fd)
    try:
        raw = json.loads(data) if data else {}
    except json.JSONDecodeError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    merged = dict(CONFIG_DEFAULTS)
    for key, value in raw.items():
        if isinstance(key, str):
            merged[key] = value
    return merged


def _update_config(mutator: Callable[[dict], dict]) -> dict:
    dir_fd = _open_state_dir()
    try:
        lock_fd = _open_regular(
            dir_fd, os.path.basename(CONFIG_LOCK), os.O_RDWR | os.O_CREAT
        )
    except Exception:
        os.close(dir_fd)
        raise
    try:
        os.fchmod(lock_fd, 0o600)
    except OSError:
        pass
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        data = ""
        try:
            data = _read_file(dir_fd, os.path.basename(CONFIG_FILE), MAX_CONFIG_BYTES)
        except OSError:
            data = ""
        try:
            raw = json.loads(data) if data else {}
        except json.JSONDecodeError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        merged = dict(CONFIG_DEFAULTS)
        for key, value in raw.items():
            if isinstance(key, str):
                merged[key] = value
        new_cfg = mutator(dict(merged))
        if not isinstance(new_cfg, dict):
            new_cfg = dict(CONFIG_DEFAULTS)
        payload = json.dumps(new_cfg) + "\n"
        _atomic_write(dir_fd, os.path.basename(CONFIG_FILE), payload, MAX_CONFIG_BYTES)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except OSError:
            pass
        os.close(dir_fd)
    return new_cfg


def set_config_value(key: str, value) -> dict:
    key = str(key)

    def mutate(cfg: dict) -> dict:
        cfg[key] = value
        return cfg

    return _update_config(mutate)


def toggle_config_bool(key: str) -> bool:
    key = str(key)

    def mutate(cfg: dict) -> dict:
        current = bool(cfg.get(key, CONFIG_DEFAULTS.get(key, False)))
        cfg[key] = not current
        return cfg

    cfg = _update_config(mutate)
    return bool(cfg.get(key, False))


def get_config_bool(key: str) -> bool:
    cfg = load_config()
    return bool(cfg.get(key, CONFIG_DEFAULTS.get(key, False)))


def get_config_choice(key: str, choices: tuple = FILL_CHOICES, default: str = "off") -> str:
    """Read an enum-style config value, coercing legacy booleans to a choice."""
    cfg = load_config()
    value = cfg.get(key, default)
    if value in (True, "true", "1"):
        return "horizontal" if "horizontal" in choices else choices[1]
    if value in (False, "false", "0"):
        return default
    return value if value in choices else default


def set_config_choice(key: str, value: str, choices: tuple = FILL_CHOICES, default: str = "off") -> str:
    """Set an enum-style config value; normalizes and returns the stored value."""
    value = str(value).strip().lower()
    if value not in choices:
        value = default
    set_config_value(key, value)
    return value


def cycle_config_choice(key: str, choices: tuple = FILL_CHOICES, default: str = "off") -> str:
    """Advance an enum-style config value to the next choice; returns it."""
    current = get_config_choice(key, choices, default)
    try:
        idx = choices.index(current)
    except ValueError:
        idx = -1
    next_idx = (idx + 1) % len(choices)
    next_value = choices[next_idx]
    set_config_value(key, next_value)
    return next_value


def _snapshot_name(workspace_id: int) -> str:
    return f"snapshot-{int(workspace_id)}.json"


def save_snapshot(workspace_id: int, entries) -> None:
    """Persist the pre-grid layout for `workspace_id`.

    `entries` is an iterable of dicts, one per managed window on the workspace,
    each with keys: address, floating, x, y, w, h. Stored atomically in the
    private state dir so a shell/compositor restart does not lose the layout.
    """
    payload = [
        {
            "address": str(e.get("address", "")),
            "floating": bool(e.get("floating", False)),
            "x": int(e.get("x", 0)),
            "y": int(e.get("y", 0)),
            "w": int(e.get("w", 0)),
            "h": int(e.get("h", 0)),
        }
        for e in entries
    ]
    data = json.dumps(payload) + "\n"
    dir_fd = _open_state_dir()
    try:
        _atomic_write(
            dir_fd, _snapshot_name(workspace_id), data, MAX_SNAPSHOT_BYTES
        )
    finally:
        os.close(dir_fd)


def load_snapshot(workspace_id: int) -> list:
    """Return the saved pre-grid layout for `workspace_id` as a list of dicts."""
    dir_fd = _open_state_dir(create=False)
    if dir_fd < 0:
        return []
    try:
        data = _read_file(dir_fd, _snapshot_name(workspace_id), MAX_SNAPSHOT_BYTES)
    finally:
        os.close(dir_fd)
    try:
        raw = json.loads(data) if data else []
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    result = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        addr = str(e.get("address", ""))
        if not addr:
            continue
        result.append(
            {
                "address": addr,
                "floating": bool(e.get("floating", False)),
                "x": int(e.get("x", 0)),
                "y": int(e.get("y", 0)),
                "w": int(e.get("w", 0)),
                "h": int(e.get("h", 0)),
            }
        )
    return result


def clear_snapshot(workspace_id: int) -> None:
    dir_fd = _open_state_dir(create=False)
    if dir_fd < 0:
        return
    try:
        try:
            os.unlink(_snapshot_name(workspace_id), dir_fd=dir_fd)
            os.fsync(dir_fd)
        except FileNotFoundError:
            pass
    finally:
        os.close(dir_fd)


__all__ = [
    "STATE_DIR",
    "WORKSPACE_FILE",
    "PID_FILE",
    "LOCK_FILE",
    "MAX_SET_BYTES",
    "MAX_PID_BYTES",
    "MAX_CONFIG_BYTES",
    "load_workspace_ids",
    "replace_workspace_ids",
    "clear_workspace_ids",
    "toggle_workspace_id",
    "workspace_is_equalized",
    "acquire_watcher_lock",
    "proc_start_time",
    "write_pid_record",
    "read_pid_record",
    "remove_pid_record",
    "load_config",
    "set_config_value",
    "toggle_config_bool",
    "get_config_bool",
    "get_config_choice",
    "set_config_choice",
    "cycle_config_choice",
    "FILL_CHOICES",
    "save_snapshot",
    "load_snapshot",
    "clear_snapshot",
]
