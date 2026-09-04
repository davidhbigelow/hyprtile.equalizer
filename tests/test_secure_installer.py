#!/usr/bin/python3

import os
import pathlib
import sys
import tempfile
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "scripts"))
import _equalize_install as installer


class SecureInstallerTests(unittest.TestCase):
    def test_migrates_legacy_nohup_entry(self):
        old = (
            b"local o = {}\n"
            b"-- hyprtile.equalize: live grid watcher\n"
            b'o.exec_on_start("nohup /tmp/equalize-watch >/dev/null 2>&1 &")\n'
        )
        result = installer.replace_plugin_entry(
            old,
            (
                "-- hyprtile.equalize: live grid watcher",
                "-- hyprtile.equalize: supervised live grid watcher",
            ),
            "o.exec_on_start(",
            "equalize-watch",
            "-- hyprtile.equalize: supervised live grid watcher",
            'o.exec_on_start("/usr/bin/systemd-run equalize-watch")',
        )
        self.assertNotIn(b"nohup", result)
        self.assertEqual(result.count(b"hyprtile.equalize:"), 1)
        self.assertEqual(result.count(b"equalize-watch"), 1)

    def test_preserves_unmanaged_matching_lines_and_comments(self):
        original = (
            b"-- user note about equalize-watch behavior\n"
            b'o.exec_on_start("/opt/custom/equalize-watch-helper")\n'
            b'-- equalize-toggle is configured elsewhere\n'
        )
        result = installer.replace_plugin_entry(
            original,
            ("-- hyprtile.equalize: live grid watcher",),
            "o.exec_on_start(",
            "equalize-watch",
            "-- hyprtile.equalize: supervised live grid watcher",
            'o.exec_on_start("/usr/bin/systemd-run equalize-watch")',
        )
        for line in original.splitlines():
            self.assertIn(line, result)

    def test_rejects_symlink_and_hardlinked_config(self):
        with tempfile.TemporaryDirectory() as directory:
            dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                target = pathlib.Path(directory, "target")
                target.write_text("safe")
                pathlib.Path(directory, "linked.lua").symlink_to(target)
                with self.assertRaises(installer.InstallError):
                    installer.read_original(dir_fd, "linked.lua", os.getuid())

                os.link(target, pathlib.Path(directory, "hardlinked.lua"))
                with self.assertRaises(installer.InstallError):
                    installer.read_original(dir_fd, "hardlinked.lua", os.getuid())
            finally:
                os.close(dir_fd)

    def test_atomic_write_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory, "bindings.lua")
            path.write_bytes(b"original\n")
            os.chmod(path, 0o640)
            dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                original = installer.read_original(dir_fd, path.name, os.getuid())
                installed = installer.atomic_write(
                    dir_fd,
                    path.name,
                    b"updated\n",
                    original.mode,
                    os.getuid(),
                    original,
                )
                self.assertEqual(path.read_bytes(), b"updated\n")
                installer.restore(dir_fd, path.name, original, installed, os.getuid())
                self.assertEqual(path.read_bytes(), b"original\n")
                self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            finally:
                os.close(dir_fd)

    def test_refuses_to_overwrite_concurrent_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory, "bindings.lua")
            path.write_bytes(b"original\n")
            dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                original = installer.read_original(dir_fd, path.name, os.getuid())
                path.write_bytes(b"external edit\n")
                with self.assertRaisesRegex(installer.InstallError, "changed concurrently"):
                    installer.atomic_write(
                        dir_fd,
                        path.name,
                        b"installer update\n",
                        original.mode,
                        os.getuid(),
                        original,
                    )
                self.assertEqual(path.read_bytes(), b"external edit\n")
            finally:
                os.close(dir_fd)

    def test_refuses_concurrent_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory, "bindings.lua")
            dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                missing = installer.read_original(dir_fd, path.name, os.getuid())
                path.write_bytes(b"external creation\n")
                with self.assertRaisesRegex(installer.InstallError, "appeared concurrently"):
                    installer.atomic_write(
                        dir_fd,
                        path.name,
                        b"installer update\n",
                        0o600,
                        os.getuid(),
                        missing,
                    )
                self.assertEqual(path.read_bytes(), b"external creation\n")
            finally:
                os.close(dir_fd)

    def test_refuses_to_overwrite_concurrent_edit_during_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory, "autostart.lua")
            path.write_bytes(b"original\n")
            dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                original = installer.read_original(dir_fd, path.name, os.getuid())
                installed = installer.atomic_write(
                    dir_fd,
                    path.name,
                    b"installer update\n",
                    original.mode,
                    os.getuid(),
                    original,
                )
                path.write_bytes(b"external edit\n")
                with self.assertRaisesRegex(installer.InstallError, "changed concurrently"):
                    installer.restore(
                        dir_fd, path.name, original, installed, os.getuid()
                    )
                self.assertEqual(path.read_bytes(), b"external edit\n")
            finally:
                os.close(dir_fd)


if __name__ == "__main__":
    unittest.main()
