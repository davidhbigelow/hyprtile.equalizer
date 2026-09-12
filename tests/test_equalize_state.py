#!/usr/bin/python3

import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "scripts"))
import _equalize_state as state


class EqualizeStateTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.original_state_dir = state.STATE_DIR
        state.STATE_DIR = os.path.join(self.tmp.name, "state", "hyprtile.equalizer")
        self.addCleanup(setattr, state, "STATE_DIR", self.original_state_dir)

    def test_descriptor_relative_state_round_trip(self):
        self.assertEqual(state.replace_workspace_ids({4, 2}), {2, 4})
        self.assertEqual(state.load_workspace_ids(), {2, 4})
        self.assertTrue(state.toggle_workspace_id(3))
        self.assertEqual(state.load_workspace_ids(), {2, 3, 4})

        self.assertEqual(state.set_config_choice("fill_remainder", "vertical"), "vertical")
        self.assertEqual(state.get_config_choice("fill_remainder"), "vertical")

        entries = [
            {"address": "0xabc", "floating": True, "x": 1, "y": 2, "w": 3, "h": 4}
        ]
        state.save_snapshot(2, entries)
        self.assertEqual(state.load_snapshot(2), entries)
        state.clear_snapshot(2)
        self.assertEqual(state.load_snapshot(2), [])

        state.write_pid_record(os.getpid(), __file__)
        self.assertEqual(state.read_pid_record()["pid"], os.getpid())
        state.remove_pid_record()
        self.assertIsNone(state.read_pid_record())

        self.assertEqual(os.stat(state.STATE_DIR).st_mode & 0o777, 0o700)

    def test_refuses_symlinked_state_directory(self):
        parent = os.path.join(self.tmp.name, "parent")
        target = os.path.join(self.tmp.name, "target")
        os.mkdir(parent, 0o700)
        os.mkdir(target, 0o700)
        linked = os.path.join(parent, "hyprtile.equalizer")
        os.symlink(target, linked)
        state.STATE_DIR = linked

        with self.assertRaises(OSError):
            state.load_workspace_ids()

    def test_atomic_publication_replaces_symlink_not_target(self):
        state.replace_workspace_ids({1})
        victim = os.path.join(self.tmp.name, "victim")
        pathlib.Path(victim).write_text("untouched\n")
        workspace_file = os.path.join(state.STATE_DIR, "equalized-workspaces")
        os.unlink(workspace_file)
        os.symlink(victim, workspace_file)

        state.replace_workspace_ids({7})

        self.assertEqual(pathlib.Path(victim).read_text(), "untouched\n")
        self.assertFalse(os.path.islink(workspace_file))
        self.assertEqual(state.load_workspace_ids(), {7})

    def test_refuses_hardlinked_state_file(self):
        state.replace_workspace_ids({1})
        workspace_file = os.path.join(state.STATE_DIR, "equalized-workspaces")
        os.link(workspace_file, os.path.join(self.tmp.name, "second-link"))

        with self.assertRaises(OSError):
            state.load_workspace_ids()


if __name__ == "__main__":
    unittest.main()
