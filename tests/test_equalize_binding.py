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


def _write(path, text):
    pathlib.Path(path).write_text(text)
    os.chmod(path, 0o600)


class EqualizeBindingTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home, mode=0o700)
        self._saved_home = os.environ.get("EQUALIZE_HOME")
        os.environ["EQUALIZE_HOME"] = self.home
        self.addCleanup(lambda: self._restore_home())

    def _restore_home(self):
        if self._saved_home is None:
            os.environ.pop("EQUALIZE_HOME", None)
        else:
            os.environ["EQUALIZE_HOME"] = self._saved_home

    @property
    def hypr(self):
        return os.path.join(self.home, ".config", "hypr")

    def _seed(self, bindings=None, autostart=None):
        if bindings is not None or autostart is not None:
            os.makedirs(self.hypr, mode=0o700)
        if bindings is not None:
            _write(os.path.join(self.hypr, b.BINDINGS), bindings)
        if autostart is not None:
            _write(os.path.join(self.hypr, b.AUTOSTART), autostart)

    def _default_seed(self):
        self._seed(
            bindings=(
                "local o = {}\n"
                f"{b.BEGIN}\n"
                "-- hyprtile.equalize: toggle live grid (SUPER + E)\n"
                'o.bind("SUPER + E", "Toggle live equalize mode", "/usr/bin/python3 /old/path/scripts/equalize-toggle")\n'
                f"{b.END}\n"
                'o.bind("SUPER + A", "Other", "something-else")\n'
            ),
            autostart=(
                "local o = {}\n"
                f"{b.BEGIN}\n"
                "-- hyprtile.equalize: supervised live grid watcher\n"
                'o.exec_on_start("/usr/bin/python3 /old/path/scripts/equalize-watch")\n'
                f"{b.END}\n"
            ),
        )

    @classmethod
    def setUpClass(cls):
        cls._original_reload = b._reload
        b._reload = lambda: None

    @classmethod
    def tearDownClass(cls):
        b._reload = cls._original_reload

    def test_ensure_migrates_legacy_binding_and_autostart(self):
        self._default_seed()
        self.assertEqual(b.ensure(), 0)
        bindings = pathlib.Path(os.path.join(self.hypr, b.BINDINGS)).read_text()
        self.assertIn(b._block(), bindings)
        self.assertNotIn("/old/path", bindings)
        self.assertIn('o.bind("SUPER + A", "Other", "something-else")', bindings)
        autostart = pathlib.Path(os.path.join(self.hypr, b.AUTOSTART)).read_text()
        self.assertNotIn("equalize-watch", autostart)
        self.assertNotIn("hyprtile", autostart)

    def test_ensure_is_idempotent(self):
        self._default_seed()
        b.ensure()
        first = pathlib.Path(os.path.join(self.hypr, b.BINDINGS)).read_text()
        b.ensure()
        self.assertEqual(first, pathlib.Path(os.path.join(self.hypr, b.BINDINGS)).read_text())
        self.assertEqual(first.count(b.BEGIN), 1)

    def test_managed_block_overrides_directional_swaps(self):
        block = b._block()
        self.assertIn('hl.unbind("SUPER + SHIFT + RIGHT")', block)
        self.assertIn("equalize-move right", block)

    def test_remove_cleans_binding_but_keeps_other_content(self):
        self._default_seed()
        b.ensure()
        self.assertIn(b.BEGIN, pathlib.Path(os.path.join(self.hypr, b.BINDINGS)).read_text())
        self.assertEqual(b.remove(), 0)
        bindings = pathlib.Path(os.path.join(self.hypr, b.BINDINGS)).read_text()
        self.assertNotIn("equalize", bindings)
        self.assertIn('o.bind("SUPER + A", "Other", "something-else")', bindings)
        self.assertNotIn("equalize-watch", pathlib.Path(os.path.join(self.hypr, b.AUTOSTART)).read_text())

    def test_status_reports_absence(self):
        self._default_seed()
        b.remove()
        self.assertEqual(b.status(), 0)

    def test_missing_files_are_created_on_ensure(self):
        self._default_seed()
        os.unlink(os.path.join(self.hypr, b.BINDINGS))
        os.unlink(os.path.join(self.hypr, b.AUTOSTART))
        b.ensure()
        self.assertIn(b._block(), pathlib.Path(os.path.join(self.hypr, b.BINDINGS)).read_text())

    def test_ensure_creates_missing_config_dirs(self):
        b.ensure()
        self.assertEqual(os.stat(self.hypr).st_mode & 0o777, 0o700)
        self.assertIn(b._block(), pathlib.Path(os.path.join(self.hypr, b.BINDINGS)).read_text())
        self.assertFalse(os.path.exists(os.path.join(self.hypr, b.AUTOSTART)))

    def test_remove_without_config_dir_is_clean(self):
        self.assertEqual(b.remove(), 0)
        self.assertFalse(os.path.isdir(self.hypr))

    def test_refuses_symlinked_hypr_dir(self):
        os.makedirs(os.path.join(self.tmp.name, "elsewhere"), mode=0o700)
        os.makedirs(os.path.join(self.home, ".config"), mode=0o700)
        os.symlink(
            os.path.join(self.tmp.name, "elsewhere"),
            self.hypr,
        )
        with self.assertRaises(b.BindingError):
            b.ensure()
        with self.assertRaises(b.BindingError):
            b.remove()
        with self.assertRaises(b.BindingError):
            b.status()

    def test_refuses_symlinked_bindings_file(self):
        self._seed(autostart="local o = {}\n")
        _write(os.path.join(self.tmp.name, "decoy"), "local o = {}\n")
        os.symlink(os.path.join(self.tmp.name, "decoy"), os.path.join(self.hypr, b.BINDINGS))
        with self.assertRaises(b.BindingError):
            b.ensure()
        with self.assertRaises(b.BindingError):
            b.remove()

    def test_refuses_group_writable_hypr_dir(self):
        self._seed(bindings="local o = {}\n")
        os.chmod(self.hypr, 0o775)
        with self.assertRaises(b.BindingError):
            b.ensure()
        self.assertEqual(
            pathlib.Path(os.path.join(self.hypr, b.BINDINGS)).read_text(),
            "local o = {}\n",
        )

    def test_refuses_foreign_owned_bindings(self):
        self._seed(bindings="local o = {}\n")
        target = os.path.join(self.hypr, b.BINDINGS)
        try:
            os.chown(target, 0, -1)
        except PermissionError:
            self.skipTest("cannot chown to another uid as non-root")
        with self.assertRaises(b.BindingError):
            b.ensure()

    def test_refuses_multi_link_bindings(self):
        self._seed(bindings="local o = {}\n")
        os.link(
            os.path.join(self.hypr, b.BINDINGS),
            os.path.join(self.hypr, "bindings-backup.lua"),
        )
        with self.assertRaises(b.BindingError):
            b.ensure()

    def test_new_config_files_are_private(self):
        b.ensure()
        mode = os.stat(os.path.join(self.hypr, b.BINDINGS)).st_mode & 0o777
        self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "scripts"))
    unittest.main()
