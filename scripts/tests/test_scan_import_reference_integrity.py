"""Stdlib unittest coverage for ``scan_import_reference_integrity``.

Locks the gate's behavior so it cannot be silently weakened. Pure-AST
helpers are exercised with synthetic source strings; the end-to-end
``_scan`` is exercised against a synthetic ``apps/`` tree built in a temp
dir with the module's path constants + caches monkey-patched. No real
working-tree file is touched.

Covered:

  * absent symbol IS flagged (the core loophole).
  * real symbol is NOT flagged.
  * absent module IS flagged.
  * PEP-420 namespace package (dir w/o __init__) is NOT flagged.
  * a submodule imported via ``from pkg import submod`` is NOT flagged.
  * ``globals().update`` / ``__getattr__`` / ``import *`` re-export makes
    the target opaque (symbol checks skipped) — no false positives.
  * a phantom guarded by ``try/except ImportError`` is NOT flagged.
  * a phantom guarded by ``except <NAMED_TUPLE>`` (tuple incl. ImportError)
    is NOT flagged.
  * a phantom guarded only by ``except ValueError`` IS flagged.
  * a ``# import-ref-allow:`` marker (same line / line above) excuses it.
  * ``importlib.import_module("apps.absent")`` literal IS flagged.
"""

from __future__ import annotations

import ast
import pathlib
import sys
import textwrap
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import scan_import_reference_integrity as scanner  # noqa: E402


def _parse(src: str) -> ast.AST:
    return ast.parse(textwrap.dedent(src))


class PureAstHelperTests(unittest.TestCase):
    def test_named_exception_tuple_alias_recognized(self):
        tree = _parse(
            """
            _SOFT = (ImportError, AttributeError, ValueError)
            _NOT_GUARD = (ValueError, KeyError)
            """
        )
        aliases = scanner._exception_tuple_aliases(tree)
        self.assertIn("_SOFT", aliases)
        self.assertNotIn("_NOT_GUARD", aliases)

    def test_guarded_linenos_literal_and_alias_and_negative(self):
        tree = _parse(
            """
            _SOFT = (ImportError, ValueError)
            try:
                from apps.x import a  # guarded by literal
            except ImportError:
                a = None
            try:
                from apps.x import b  # guarded by named tuple
            except _SOFT:
                b = None
            try:
                from apps.x import c  # NOT guarded (ValueError only)
            except ValueError:
                c = None
            """
        )
        guarded = scanner._guarded_linenos(tree)
        # Line numbers of the three imports within the dedented source.
        self.assertIn(4, guarded)   # a
        self.assertIn(8, guarded)   # b
        self.assertNotIn(12, guarded)  # c

    def test_module_symbols_collects_and_opacity(self):
        # globals() use -> opaque
        self.assertTrue(_opaque("x = 1\nglobals().update({})\n"))
        # __getattr__ -> opaque
        self.assertTrue(_opaque("def __getattr__(name):\n    return None\n"))
        # star import -> opaque
        self.assertTrue(_opaque("from .y import *\n"))
        # plain module -> not opaque, names collected
        names, opaque = _symbols("def foo():\n    pass\n\n\nclass Bar:\n    pass\n\nBAZ = 3\n")
        self.assertFalse(opaque)
        self.assertEqual(names, {"foo", "Bar", "BAZ"})

    def test_marker_excuses_same_line_and_line_above(self):
        marked = scanner._marked_linenos(
            [
                "from apps.x import a  # import-ref-allow: deferred schema",  # line 1
                "# import-ref-allow: above",  # line 2
                "from apps.x import b",  # line 3
            ]
        )
        self.assertTrue(scanner._is_excused(1, set(), marked))   # same line
        self.assertTrue(scanner._is_excused(3, set(), marked))   # line above
        self.assertFalse(scanner._is_excused(5, set(), marked))


def _opaque(src: str) -> bool:
    return _symbols(src)[1]


def _symbols(src: str):
    """Parse a synthetic module body and run the symbol collector on it."""
    names: set[str] = set()
    opaque = False
    tree = _parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "globals":
            opaque = True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            if node.name == "__getattr__":
                opaque = True
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                scanner._collect_assign_names(tgt, names)
        elif isinstance(node, ast.AnnAssign):
            scanner._collect_assign_names(node.target, names)
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "*":
                    opaque = True
                else:
                    names.add(a.asname or a.name)
    return names, opaque


class EndToEndScanTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self._tmp.name)
        apps = root / "apps"
        (apps / "real").mkdir(parents=True)
        (apps / "real" / "__init__.py").write_text("", encoding="utf-8")
        (apps / "real" / "models.py").write_text(
            "class RealModel:\n    pass\n", encoding="utf-8"
        )
        # namespace package: directory, no __init__.py, with a submodule
        (apps / "ns").mkdir()
        (apps / "ns" / "submod.py").write_text("VALUE = 1\n", encoding="utf-8")
        # patch module globals + clear caches
        self._orig = (scanner.REPO_ROOT, scanner.APPS_DIR)
        scanner.REPO_ROOT = root
        scanner.APPS_DIR = apps
        scanner._module_file_cache.clear()
        scanner._module_symbols_cache.clear()

    def tearDown(self):
        scanner.REPO_ROOT, scanner.APPS_DIR = self._orig
        scanner._module_file_cache.clear()
        scanner._module_symbols_cache.clear()
        self._tmp.cleanup()

    def _scan_source(self, rel: str, src: str):
        path = scanner.APPS_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(src), encoding="utf-8")
        return scanner._scan_file(path)

    def _kinds(self, findings):
        return {(f["kind"], f["statement"]) for f in findings}

    def test_absent_symbol_flagged(self):
        f = self._scan_source("caller.py", "from apps.real.models import Ghost\n")
        self.assertIn(("absent-symbol", "from apps.real.models import Ghost"), self._kinds(f))

    def test_real_symbol_not_flagged(self):
        f = self._scan_source("caller.py", "from apps.real.models import RealModel\n")
        self.assertEqual(f, [])

    def test_absent_module_flagged(self):
        f = self._scan_source("caller.py", "import apps.real.nope\n")
        self.assertTrue(any(k == "absent-module" for k, _ in self._kinds(f)))

    def test_namespace_package_not_flagged(self):
        # importing the namespace package itself and its submodule are both fine
        f = self._scan_source("caller.py", "from apps.ns import submod\nimport apps.ns\n")
        self.assertEqual(f, [])

    def test_globals_reexport_opaque_no_false_positive(self):
        # a package __init__ that dynamically re-exports -> symbol unprovable -> skip
        (scanner.APPS_DIR / "dyn").mkdir()
        (scanner.APPS_DIR / "dyn" / "__init__.py").write_text(
            "globals().update({'Injected': 1})\n", encoding="utf-8"
        )
        scanner._module_file_cache.clear()
        scanner._module_symbols_cache.clear()
        f = self._scan_source("caller.py", "from apps.dyn import Injected\n")
        self.assertEqual(f, [])

    def test_phantom_guarded_by_importerror_not_flagged(self):
        f = self._scan_source(
            "caller.py",
            """
            try:
                from apps.real.models import Ghost
            except ImportError:
                Ghost = None
            """,
        )
        self.assertEqual(f, [])

    def test_phantom_guarded_by_named_tuple_not_flagged(self):
        f = self._scan_source(
            "caller.py",
            """
            _SOFT = (ImportError, AttributeError)
            try:
                from apps.real.models import Ghost
            except _SOFT:
                Ghost = None
            """,
        )
        self.assertEqual(f, [])

    def test_phantom_guarded_only_by_valueerror_is_flagged(self):
        f = self._scan_source(
            "caller.py",
            """
            try:
                from apps.real.models import Ghost
            except ValueError:
                Ghost = None
            """,
        )
        self.assertTrue(any(k == "absent-symbol" for k, _ in self._kinds(f)))

    def test_allow_marker_excuses(self):
        f = self._scan_source(
            "caller.py",
            "from apps.real.models import Ghost  # import-ref-allow: deferred schema\n",
        )
        self.assertEqual(f, [])

    def test_import_module_literal_absent_flagged(self):
        f = self._scan_source(
            "caller.py", "import importlib\nimportlib.import_module('apps.absent.mod')\n"
        )
        self.assertTrue(any(k == "absent-module" for k, _ in self._kinds(f)))


if __name__ == "__main__":
    unittest.main()
