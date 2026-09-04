#!/usr/bin/python3
"""Secure, transactional installer for hyprtile.equalize."""

from __future__ import annotations

import fcntl
import os
import pwd
import re
import secrets
import shlex
import stat
import subprocess
import sys
from dataclasses import dataclass


PYTHON = "/usr/bin/python3"
HYPRCTL = "/usr/bin/hyprctl"
SYSTEMCTL = "/usr/bin/systemctl"
SYSTEMD_RUN = "/usr/bin/systemd-run"
UNIT = "hyprtile-equalize.service"
MAX_CONFIG_BYTES = 4 * 1024 * 1024
LOCK_NAME = ".hyprtile.equalize.install.lock"
SIGNATURE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class InstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class Original:
    exists: bool
    data: bytes = b""
    mode: int = 0o600


def require_fixed_tool(path: str) -> None:
    try:
        info = os.stat(path)
    except OSError as exc:
        raise InstallError(f"required tool is unavailable: {path}: {exc}") from exc
    if not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK):
        raise InstallError(f"required tool is not an executable regular file: {path}")
    if info.st_uid != 0:
        raise InstallError(f"required tool is not root-owned: {path}")


def open_owned_dir(path: str, uid: int) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise InstallError(f"refusing unsafe directory {path}: {exc}") from exc
    info = os.fstat(fd)
    if info.st_uid != uid or info.st_mode & 0o022:
        os.close(fd)
        raise InstallError(f"directory must be owned by uid {uid} and not group/world-writable: {path}")
    return fd


def open_or_create_owned_dir(parent_fd: int, name: str, uid: int) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise InstallError(f"could not securely create directory {name}: {exc}") from exc
    except OSError as exc:
        raise InstallError(f"refusing unsafe directory {name}: {exc}") from exc
    info = os.fstat(fd)
    if info.st_uid != uid or info.st_mode & 0o022:
        os.close(fd)
        raise InstallError(
            f"directory must be owned by uid {uid} and not group/world-writable: {name}"
        )
    return fd


def validate_plugin_file(path: str, uid: int) -> None:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise InstallError(f"refusing unsafe plugin file {path}: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid:
            raise InstallError(f"plugin file must be a regular file owned by uid {uid}: {path}")
    finally:
        os.close(fd)


def read_original(dir_fd: int, name: str, uid: int) -> Original:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        return Original(False)
    except OSError as exc:
        raise InstallError(f"refusing unsafe config file {name}: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_nlink != 1:
            raise InstallError(
                f"config must be a singly-linked regular file owned by uid {uid}: {name}"
            )
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, MAX_CONFIG_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_CONFIG_BYTES:
                raise InstallError(f"config exceeds {MAX_CONFIG_BYTES} bytes: {name}")
        return Original(True, b"".join(chunks), stat.S_IMODE(info.st_mode))
    finally:
        os.close(fd)


def atomic_write(dir_fd: int, name: str, data: bytes, mode: int) -> None:
    if len(data) > MAX_CONFIG_BYTES:
        raise InstallError(f"refusing oversized config write: {name}")
    tmp_name = f".hyprtile.equalize.{secrets.token_hex(16)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(tmp_name, flags, mode & 0o777, dir_fd=dir_fd)
    try:
        os.fchmod(fd, mode & 0o777)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(tmp_name, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        os.fsync(dir_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp_name, dir_fd=dir_fd)
        except FileNotFoundError:
            pass


def restore(dir_fd: int, name: str, original: Original) -> None:
    if original.exists:
        atomic_write(dir_fd, name, original.data, original.mode)
    else:
        try:
            os.unlink(name, dir_fd=dir_fd)
            os.fsync(dir_fd)
        except FileNotFoundError:
            pass


def lua_quote(value: str) -> str:
    if any(ord(char) < 32 for char in value):
        raise InstallError("plugin path contains a control character")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def replace_plugin_entry(data: bytes, needle: bytes, comment: str, line: str) -> bytes:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InstallError("Hyprland configuration is not valid UTF-8") from exc
    kept = []
    for existing in text.splitlines():
        encoded = existing.encode("utf-8")
        if needle in encoded or existing.startswith("-- hyprtile.equalize:"):
            continue
        kept.append(existing)
    body = "\n".join(kept).rstrip("\n")
    if body:
        body += "\n"
    body += f"\n{comment}\n{line}\n"
    encoded = body.encode("utf-8")
    if len(encoded) > MAX_CONFIG_BYTES:
        raise InstallError("updated Hyprland configuration is too large")
    return encoded


def run_checked(args: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    uid = os.getuid()
    env = {
        "HOME": pwd.getpwuid(uid).pw_dir,
        "PATH": "/usr/bin",
        "XDG_RUNTIME_DIR": f"/run/user/{uid}",
    }
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    if SIGNATURE_RE.fullmatch(signature):
        env["HYPRLAND_INSTANCE_SIGNATURE"] = signature
    bus_address = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    if bus_address.startswith("unix:path=/run/user/") and "\n" not in bus_address:
        env["DBUS_SESSION_BUS_ADDRESS"] = bus_address
    try:
        return subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallError(f"command failed: {args[0]}: {exc}") from exc


def watcher_command(watcher: str) -> list[str]:
    return [
        SYSTEMD_RUN,
        "--user",
        f"--unit={UNIT}",
        "--collect",
        "--property=Type=exec",
        "--property=TimeoutStopSec=5s",
        "--setenv=HYPRLAND_INSTANCE_SIGNATURE",
        "--setenv=XDG_RUNTIME_DIR",
        "--setenv=PATH=/usr/bin",
        PYTHON,
        watcher,
    ]


def main() -> int:
    if len(sys.argv) != 2:
        raise InstallError("usage: install.sh")
    uid = os.getuid()
    home = pwd.getpwuid(uid).pw_dir
    plugin_dir = os.path.realpath(sys.argv[1])
    scripts_dir = os.path.join(plugin_dir, "scripts")
    toggle = os.path.join(scripts_dir, "equalize-toggle")
    watcher = os.path.join(scripts_dir, "equalize-watch")

    for tool in (PYTHON, HYPRCTL, SYSTEMCTL, SYSTEMD_RUN):
        require_fixed_tool(tool)
    for plugin_file in (toggle, watcher):
        validate_plugin_file(plugin_file, uid)
    plugin_fd = open_owned_dir(plugin_dir, uid)
    scripts_fd = open_owned_dir(scripts_dir, uid)
    os.close(scripts_fd)
    os.close(plugin_fd)

    home_fd = open_owned_dir(home, uid)
    config_fd = hypr_fd = lock_fd = -1
    try:
        config_fd = open_or_create_owned_dir(home_fd, ".config", uid)
        hypr_fd = open_or_create_owned_dir(config_fd, "hypr", uid)
        lock_flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            lock_flags |= os.O_NOFOLLOW
        lock_fd = os.open(LOCK_NAME, lock_flags, 0o600, dir_fd=hypr_fd)
        lock_info = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(lock_info.st_mode)
            or lock_info.st_uid != uid
            or lock_info.st_nlink != 1
        ):
            raise InstallError("installer lock must be a singly-linked, user-owned regular file")
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        originals = {
            "bindings.lua": read_original(hypr_fd, "bindings.lua", uid),
            "autostart.lua": read_original(hypr_fd, "autostart.lua", uid),
        }
        bind_command = f"{PYTHON} {shlex.quote(toggle)}"
        start_command = " ".join(shlex.quote(arg) for arg in watcher_command(watcher))
        binding = (
            'o.bind("SUPER + E", "Toggle live equalize mode", '
            f"{lua_quote(bind_command)})"
        )
        autostart = f"o.exec_on_start({lua_quote(start_command)})"
        updates = {
            "bindings.lua": replace_plugin_entry(
                originals["bindings.lua"].data,
                b"equalize-toggle",
                "-- hyprtile.equalize: toggle live grid (SUPER + E)",
                binding,
            ),
            "autostart.lua": replace_plugin_entry(
                originals["autostart.lua"].data,
                b"equalize-watch",
                "-- hyprtile.equalize: supervised live grid watcher",
                autostart,
            ),
        }

        changed = []
        signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
        if signature and not SIGNATURE_RE.fullmatch(signature):
            raise InstallError("invalid HYPRLAND_INSTANCE_SIGNATURE")
        hypr_socket = os.path.join(
            f"/run/user/{uid}", "hypr", signature, ".socket2.sock"
        )
        try:
            for name, data in updates.items():
                original = originals[name]
                if original.exists and original.data == data:
                    continue
                changed.append(name)
                atomic_write(hypr_fd, name, data, original.mode if original.exists else 0o600)

            if os.path.exists(hypr_socket):
                run_checked([HYPRCTL, "reload"])
                errors = run_checked([HYPRCTL, "configerrors"]).stdout.strip()
                if errors:
                    raise InstallError(f"Hyprland reported configuration errors:\n{errors}")
                run_checked([PYTHON, watcher, "--stop"], timeout=7.0)
                active = subprocess.run(
                    [SYSTEMCTL, "--user", "is-active", "--quiet", UNIT],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=7.0,
                    env={
                        "HOME": home,
                        "PATH": "/usr/bin",
                        "XDG_RUNTIME_DIR": f"/run/user/{uid}",
                    },
                )
                if active.returncode == 0:
                    run_checked([SYSTEMCTL, "--user", "stop", UNIT], timeout=7.0)
                run_checked(watcher_command(watcher))
                run_checked(
                    [SYSTEMCTL, "--user", "is-active", "--quiet", UNIT], timeout=7.0
                )
                print("  Hyprland reloaded; supervised watcher restarted.")
            else:
                print("  Hyprland is not running; changes will apply at next login.")
        except Exception as original_error:
            rollback_errors = []
            for name in reversed(changed):
                try:
                    restore(hypr_fd, name, originals[name])
                except Exception as exc:
                    rollback_errors.append(f"restore {name}: {exc}")
            if os.path.exists(hypr_socket):
                try:
                    run_checked([HYPRCTL, "reload"])
                except Exception as exc:
                    rollback_errors.append(f"reload restored configuration: {exc}")
            if rollback_errors:
                details = "; ".join(rollback_errors)
                raise InstallError(
                    f"installation failed ({original_error}); rollback failed ({details})"
                ) from original_error
            raise

        print(f"Plugin: {plugin_dir}")
        print("Installed SUPER+E binding and supervised watcher autostart.")
        return 0
    finally:
        for fd in (lock_fd, hypr_fd, config_fd, home_fd):
            if fd >= 0:
                os.close(fd)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
