#!/usr/bin/env python3
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
import tempfile
import time
from typing import Callable, Iterable, Optional, Set

STATE_HOME = os.environ.get("XDG_STATE_HOME") or os.path.join(
    os.path.expanduser("~"), ".local", "state"
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


def _ensure_state_dir() -> None:
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    try:
        st_mode = os.stat(STATE_DIR).st_mode & 0o777
        if st_mode != 0o700:
            os.chmod(STATE_DIR, 0o700)
    except OSError:
        pass


def _atomic_write(path: str, text: str, max_bytes: int) -> bool:
    """Write `text` to `path` atomically and enforce a size cap.

    The bytes are staged as an unpredictable `mkstemp` file (0600) in the
    private state dir, fsync'd, then atomically `os.replace`'d over `path`.
    This guarantees a reader never observes a truncated or torn file even if
    the process crashes mid-write, and prevents an unbounded payload from ever
    being persisted. Returns False (and leaves `path` untouched) if the payload
    exceeds `max_bytes`.
    """
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        return False
    _ensure_state_dir()
    tmp_fd, tmp_path = tempfile.mkstemp(dir=STATE_DIR, prefix="tmp-", text=False)
    try:
        os.fchmod(tmp_fd, 0o600)
        with os.fdopen(tmp_fd, "wb") as tmp:
            tmp.write(encoded)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, path)
        return True
    except OSError:
        return False
    finally:
        try:
            os.remove(tmp_path)
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
    _ensure_state_dir()
    data = ""
    try:
        lock_fd = os.open(WORKSPACE_LOCK, _secure_flags(os.O_RDWR | os.O_CREAT), 0o600)
    except OSError:
        lock_fd = None
    try:
        if lock_type is not None and lock_fd is not None:
            fcntl.flock(lock_fd, lock_type)
        try:
            fd = os.open(WORKSPACE_FILE, _secure_flags(os.O_RDONLY))
        except FileNotFoundError:
            return set()
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            data = handle.read(MAX_SET_BYTES + 1)
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            except OSError:
                pass
    if len(data) > MAX_SET_BYTES:
        return set()
    return _parse_ids(data)


def load_workspace_ids() -> Set[int]:
    """Return the set of workspace ids currently marked equalized."""

    return _read_ids(fcntl.LOCK_SH)


def _update_ids(mutator: Callable[[Set[int]], Set[int]]) -> Set[int]:
    _ensure_state_dir()
    lock_fd = os.open(WORKSPACE_LOCK, _secure_flags(os.O_RDWR | os.O_CREAT), 0o600)
    try:
        os.fchmod(lock_fd, 0o600)
    except OSError:
        pass
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            fd = os.open(WORKSPACE_FILE, _secure_flags(os.O_RDONLY))
        except FileNotFoundError:
            data = ""
        else:
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                data = handle.read(MAX_SET_BYTES + 1)
        if len(data) > MAX_SET_BYTES:
            ids = set()
        else:
            ids = _parse_ids(data)
        new_ids = mutator(set(ids))
        body = ""
        if new_ids:
            body = "\n".join(str(i) for i in sorted(new_ids)) + "\n"
        _atomic_write(WORKSPACE_FILE, body, MAX_SET_BYTES)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except OSError:
            pass
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

    _ensure_state_dir()
    flags = _secure_flags(os.O_RDWR | os.O_CREAT)
    fd = os.open(LOCK_FILE, flags, 0o600)
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
    _ensure_state_dir()
    record = {
        "pid": int(pid),
        "script": os.path.realpath(script_path),
        "start": proc_start_time(pid),
        "timestamp": time.time(),
    }
    tmp_fd, tmp_path = tempfile.mkstemp(dir=STATE_DIR, prefix="pid-", text=True)
    try:
        os.fchmod(tmp_fd, 0o600)
    except OSError:
        pass
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
            json.dump(record, tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, PID_FILE)
    finally:
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass


def read_pid_record() -> Optional[dict]:
    try:
        fd = os.open(PID_FILE, _secure_flags(os.O_RDONLY))
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        data = handle.read(MAX_PID_BYTES + 1)
    if len(data) > MAX_PID_BYTES:
        return None
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
    try:
        os.unlink(PID_FILE)
    except FileNotFoundError:
        pass


def load_config() -> dict:
    _ensure_state_dir()
    data = ""
    lock_fd = None
    try:
        lock_fd = os.open(CONFIG_LOCK, _secure_flags(os.O_RDWR | os.O_CREAT), 0o600)
    except OSError:
        pass
    try:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_SH)
        try:
            fd = os.open(CONFIG_FILE, _secure_flags(os.O_RDONLY))
        except FileNotFoundError:
            return dict(CONFIG_DEFAULTS)
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            data = handle.read(MAX_CONFIG_BYTES + 1)
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            except OSError:
                pass
    if len(data) > MAX_CONFIG_BYTES:
        return dict(CONFIG_DEFAULTS)
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
    _ensure_state_dir()
    lock_fd = os.open(CONFIG_LOCK, _secure_flags(os.O_RDWR | os.O_CREAT), 0o600)
    try:
        os.fchmod(lock_fd, 0o600)
    except OSError:
        pass
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        data = ""
        try:
            fd = os.open(CONFIG_FILE, _secure_flags(os.O_RDONLY))
        except FileNotFoundError:
            pass
        else:
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                data = handle.read(MAX_CONFIG_BYTES + 1)
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
        _atomic_write(CONFIG_FILE, payload, MAX_CONFIG_BYTES)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except OSError:
            pass
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


def _snapshot_path(workspace_id: int) -> str:
    return os.path.join(STATE_DIR, f"snapshot-{int(workspace_id)}.json")


def save_snapshot(workspace_id: int, entries) -> None:
    """Persist the pre-grid layout for `workspace_id`.

    `entries` is an iterable of dicts, one per managed window on the workspace,
    each with keys: address, floating, x, y, w, h. Stored atomically in the
    private state dir so a shell/compositor restart does not lose the layout.
    """
    _ensure_state_dir()
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
    data = json.dumps(payload)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=STATE_DIR, prefix="snap-", text=True)
    try:
        os.fchmod(tmp_fd, 0o600)
    except OSError:
        pass
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, _snapshot_path(workspace_id))
    finally:
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass


def load_snapshot(workspace_id: int) -> list:
    """Return the saved pre-grid layout for `workspace_id` as a list of dicts."""
    try:
        fd = os.open(_snapshot_path(workspace_id), _secure_flags(os.O_RDONLY))
    except FileNotFoundError:
        return []
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        data = handle.read(MAX_SNAPSHOT_BYTES + 1)
    if len(data) > MAX_SNAPSHOT_BYTES:
        return []
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
    try:
        os.unlink(_snapshot_path(workspace_id))
    except FileNotFoundError:
        pass


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
