#!/usr/bin/python3

import importlib.machinery
import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest

_scripts = str(pathlib.Path(__file__).parents[1] / "scripts")
_loader = importlib.machinery.SourceFileLoader(
    "equalize_binding", os.path.join(_scripts, "equalize-binding")
)
_spec = importlib.util.spec_from_loader("equalize_binding", _loader)
b = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b)


class EqualizeBindingTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._original_bindings = b.BINDINGS
        cls._original_autostart = b.AUTOSTART
        b._reload = lambda: None

    @classmethod
    def tearDownClass(cls):
        b.BINDINGS = cls._original_bindings
        b.AUTOSTART = cls._original_autostart

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        b.BINDINGS = os.path.join(self.tmp.name, "bindings.lua")
        b.AUTOSTART = os.path.join(self.tmp.name, "autostart.lua")
        pathlib.Path(b.BINDINGS).write_text(
            "local o = {}\n"
            f"{b.BEGIN}\n"
            "-- hyprtile.equalize: toggle live grid (SUPER + E)\n"
            'o.bind("SUPER + E", "Toggle live equalize mode", "/usr/bin/python3 /old/path/scripts/equalize-toggle")\n'
            f"{b.END}\n"
            'o.bind("SUPER + A", "Other", "something-else")\n'
        )
        pathlib.Path(b.AUTOSTART).write_text(
            "local o = {}\n"
            f"{b.BEGIN}\n"
            "-- hyprtile.equalize: supervised live grid watcher\n"
            'o.exec_on_start("/usr/bin/python3 /old/path/scripts/equalize-watch")\n'
            f"{b.END}\n"
        )

    def test_ensure_migrates_legacy_binding_and_autostart(self):
        self.assertEqual(b.ensure(), 0)
        bindings = pathlib.Path(b.BINDINGS).read_text()
        self.assertIn(b._block(), bindings)
        self.assertNotIn("/old/path", bindings)
        self.assertIn('o.bind("SUPER + A", "Other", "something-else")', bindings)
        autostart = pathlib.Path(b.AUTOSTART).read_text()
        self.assertNotIn("equalize-watch", autostart)
        self.assertNotIn("hyprtile", autostart)

    def test_ensure_is_idempotent(self):
        b.ensure()
        first = pathlib.Path(b.BINDINGS).read_text()
        b.ensure()
        self.assertEqual(first, pathlib.Path(b.BINDINGS).read_text())
        self.assertEqual(first.count(b.BEGIN), 1)

    def test_remove_cleans_binding_but_keeps_other_content(self):
        b.ensure()
        self.assertIn(b.BEGIN, pathlib.Path(b.BINDINGS).read_text())
        self.assertEqual(b.remove(), 0)
        bindings = pathlib.Path(b.BINDINGS).read_text()
        self.assertNotIn("equalize", bindings)
        self.assertIn('o.bind("SUPER + A", "Other", "something-else")', bindings)
        self.assertNotIn("equalize-watch", pathlib.Path(b.AUTOSTART).read_text())

    def test_status_reports_absence(self):
        b.remove()
        self.assertEqual(b.status(), 0)

    def test_missing_files_are_created_on_ensure(self):
        os.unlink(b.BINDINGS)
        os.unlink(b.AUTOSTART)
        b.ensure()
        self.assertIn(b._block(), pathlib.Path(b.BINDINGS).read_text())


if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "scripts"))
    unittest.main()