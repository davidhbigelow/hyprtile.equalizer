#!/usr/bin/python3

import importlib.machinery
import importlib.util
import os
import pathlib
import json
import socket
import sys
import tempfile
import unittest

_scripts = str(pathlib.Path(__file__).parents[1] / "scripts")
sys.path.insert(0, _scripts)
_loader = importlib.machinery.SourceFileLoader(
    "equalize_move", os.path.join(_scripts, "equalize-move")
)
_spec = importlib.util.spec_from_loader("equalize_move", _loader)
m = importlib.util.module_from_spec(_spec)
_loader.exec_module(m)


class EqualizeMoveTests(unittest.TestCase):

    def test_native_directions_use_full_hyprland_names(self):
        self.assertEqual(m.DIRECTIONS["right"], "right")
        self.assertEqual(m.DIRECTIONS["up"], "up")

    def test_move_request_is_bound_to_workspace_and_window(self):
        with tempfile.TemporaryDirectory() as runtime:
            os.chmod(runtime, 0o700)
            old_runtime = os.environ.get("XDG_RUNTIME_DIR")
            old_signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
            os.environ["XDG_RUNTIME_DIR"] = runtime
            os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = "test_instance"
            self.addCleanup(self._restore_env, "XDG_RUNTIME_DIR", old_runtime)
            self.addCleanup(
                self._restore_env, "HYPRLAND_INSTANCE_SIGNATURE", old_signature
            )
            path = m.move_socket_path()
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                receiver.bind(path)
                self.assertTrue(m.request_move(4, "0xabc", "right"))
                payload = json.loads(receiver.recv(512).decode("ascii"))
            self.assertEqual(payload["workspace"], 4)
            self.assertEqual(payload["address"], "0xabc")
            self.assertEqual(payload["direction"], "right")
            self.assertIsInstance(payload["sent"], float)

    def test_move_request_rejects_unsafe_runtime_directory(self):
        with tempfile.TemporaryDirectory() as runtime:
            os.chmod(runtime, 0o777)
            old_runtime = os.environ.get("XDG_RUNTIME_DIR")
            old_signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
            os.environ["XDG_RUNTIME_DIR"] = runtime
            os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = "test_instance"
            self.addCleanup(self._restore_env, "XDG_RUNTIME_DIR", old_runtime)
            self.addCleanup(
                self._restore_env, "HYPRLAND_INSTANCE_SIGNATURE", old_signature
            )
            self.assertFalse(m.request_move(4, "0xabc", "right"))

    @staticmethod
    def _restore_env(name, value):
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
