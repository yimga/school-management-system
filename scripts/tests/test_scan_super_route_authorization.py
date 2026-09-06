"""Tests for scripts/scan_super_route_authorization.py.

Both directions, deliberately:
  - routes the scanner MUST flag (unguarded, method-only, unresolvable)
  - routes it MUST NOT flag (common wrapper, def-site decorator, CBV
    method_decorator, access mixin)

A scanner that reports zero because it is broken is worse than no scanner,
so `test_live_super_urls_mutation_is_caught` plants an unguarded route into a
copy of the REAL apps/schools/super_urls.py and asserts it is caught.

Run: python -m unittest scripts.tests.test_scan_super_route_authorization -v
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCANNER = ROOT / "scripts" / "scan_super_route_authorization.py"


def _load():
    spec = importlib.util.spec_from_file_location("_scan_super_route_auth", SCANNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


scan_mod = _load()


VIEWS_SRC = '''
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View


def wide_open(request):
    """No decorator at all."""
    return None


@staff_member_required
def staff_gated(request):
    return None


@require_GET
def method_only(request):
    return None


@csrf_exempt
def csrf_only(request):
    return None


@method_decorator(staff_member_required, name="dispatch")
class GatedClassView(View):
    pass


class MixinGatedView(LoginRequiredMixin, View):
    pass


class BareClassView(View):
    pass


class DispatchGatedView(View):
    @method_decorator(staff_member_required)
    def dispatch(self, request, *args, **kwargs):
        return None


def aliased_target(request):
    return None
'''


class FixtureTree:
    """A temp package tree the scanner can resolve against."""

    def __init__(self, urls_src: str, views_src: str = VIEWS_SRC, extra=None):
        self.tmp = Path(tempfile.mkdtemp(prefix="rmc_super_scan_"))
        pkg = self.tmp / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "views.py").write_text(views_src, encoding="utf-8")
        (pkg / "urls_fixture.py").write_text(urls_src, encoding="utf-8")
        for rel, src in (extra or {}).items():
            target = self.tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(src, encoding="utf-8")
        self.urlconf = pkg / "urls_fixture.py"

    def rows(self):
        return scan_mod.scan(self.urlconf, self.tmp)

    def by_name(self):
        return {r["url_name"]: r for r in self.rows()}

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class MustNotFlagTests(unittest.TestCase):
    """Correctly-guarded routes must come back AUTHZ_PROVEN."""

    def setUp(self):
        self.tree = FixtureTree(
            """
from django.urls import path
from apps.schools.control_plane import require_super_access_with_host
from . import views
from .views import staff_gated, GatedClassView, MixinGatedView, DispatchGatedView

urlpatterns = [
    path("wrapped/", require_super_access_with_host(views.wide_open), name="wrapped"),
    path("defsite/", staff_gated, name="defsite"),
    path("cbv/", GatedClassView.as_view(), name="cbv"),
    path("mixin/", MixinGatedView.as_view(), name="mixin"),
    path("dispatch/", DispatchGatedView.as_view(), name="dispatch_gated"),
]
"""
        )
        self.addCleanup(self.tree.cleanup)

    def test_common_wrapper_is_proven(self):
        row = self.tree.by_name()["wrapped"]
        self.assertEqual(row["status"], "AUTHZ_PROVEN")
        self.assertEqual(row["guard_family"], "common_wrapper")
        self.assertIn("require_super_access_with_host", row["authz_guards"])

    def test_defsite_decorator_is_proven(self):
        row = self.tree.by_name()["defsite"]
        self.assertEqual(row["status"], "AUTHZ_PROVEN")
        self.assertEqual(row["guard_family"], "specialised_defsite")
        self.assertIn("staff_member_required", row["authz_guards"])

    def test_cbv_method_decorator_is_proven(self):
        row = self.tree.by_name()["cbv"]
        self.assertEqual(row["status"], "AUTHZ_PROVEN")
        self.assertEqual(row["view_kind"], "class")
        self.assertIn("staff_member_required", row["authz_guards"])

    def test_access_mixin_is_proven(self):
        row = self.tree.by_name()["mixin"]
        self.assertEqual(row["status"], "AUTHZ_PROVEN")
        self.assertIn("LoginRequiredMixin", row["authz_guards"])

    def test_decorated_dispatch_method_is_proven(self):
        row = self.tree.by_name()["dispatch_gated"]
        self.assertEqual(row["status"], "AUTHZ_PROVEN")
        self.assertIn("staff_member_required", row["authz_guards"])

    def test_none_of_these_are_unclassified(self):
        rows = self.tree.rows()
        self.assertEqual(scan_mod.unclassified_keys(rows), [])
        self.assertEqual(scan_mod.partial_keys(rows), [])


class MustFlagTests(unittest.TestCase):
    """Routes with no authorization must NOT be reported as proven."""

    def setUp(self):
        self.tree = FixtureTree(
            """
from django.urls import path
from .views import wide_open, method_only, csrf_only, BareClassView
from .nowhere import ghost_view

urlpatterns = [
    path("open/", wide_open, name="open"),
    path("method/", method_only, name="method"),
    path("csrf/", csrf_only, name="csrf"),
    path("bare-cbv/", BareClassView.as_view(), name="bare_cbv"),
    path("ghost/", ghost_view, name="ghost"),
]
"""
        )
        self.addCleanup(self.tree.cleanup)

    def test_undecorated_function_is_unguarded(self):
        row = self.tree.by_name()["open"]
        self.assertEqual(row["status"], "UNGUARDED")
        self.assertEqual(row["authz_guards"], [])

    def test_method_guard_alone_is_not_authorization(self):
        row = self.tree.by_name()["method"]
        self.assertEqual(row["status"], "METHOD_ONLY")
        self.assertEqual(row["authz_guards"], [])
        self.assertIn("require_GET", row["method_guards"])

    def test_csrf_exempt_alone_is_not_authorization(self):
        row = self.tree.by_name()["csrf"]
        self.assertEqual(row["status"], "METHOD_ONLY")
        self.assertEqual(row["authz_guards"], [])
        self.assertIn("csrf_exempt", row["csrf"])

    def test_bare_cbv_is_unguarded(self):
        row = self.tree.by_name()["bare_cbv"]
        self.assertEqual(row["status"], "UNGUARDED")

    def test_unresolvable_view_is_unresolved_not_proven(self):
        """A resolver failure must never read as safe."""
        row = self.tree.by_name()["ghost"]
        self.assertEqual(row["status"], "UNRESOLVED")
        self.assertEqual(row["authz_guards"], [])

    def test_unclassified_set_contains_the_unguarded_routes(self):
        rows = self.tree.rows()
        unc = scan_mod.unclassified_keys(rows)
        self.assertIn("urls_fixture.py::open::open/", unc)
        self.assertIn("urls_fixture.py::bare_cbv::bare-cbv/", unc)
        self.assertIn("urls_fixture.py::ghost::ghost/", unc)
        part = scan_mod.partial_keys(rows)
        self.assertIn("urls_fixture.py::method::method/", part)
        self.assertIn("urls_fixture.py::csrf::csrf/", part)

    def test_summary_counts_are_honest(self):
        summary = scan_mod.summarise(self.tree.rows())
        self.assertEqual(summary["fully_classified"], 0)
        self.assertEqual(summary["partially_classified"], 2)
        self.assertEqual(summary["unclassified"], 3)


class ResolutionTests(unittest.TestCase):
    """Import-shape resolution the /super/ urlconf actually uses."""

    def test_aliased_symbol_import(self):
        tree = FixtureTree(
            """
from django.urls import path
from .views import aliased_target as renamed

urlpatterns = [path("a/", renamed, name="a")]
"""
        )
        self.addCleanup(tree.cleanup)
        row = tree.by_name()["a"]
        self.assertEqual(row["view_symbol"], "aliased_target")
        self.assertEqual(row["view_module"], "pkg.views")

    def test_module_alias_attribute(self):
        tree = FixtureTree(
            """
from django.urls import path
from . import views

urlpatterns = [path("b/", views.staff_gated, name="b")]
"""
        )
        self.addCleanup(tree.cleanup)
        self.assertEqual(tree.by_name()["b"]["status"], "AUTHZ_PROVEN")

    def test_partial_is_unwrapped_to_the_inner_view(self):
        tree = FixtureTree(
            """
from functools import partial
from django.urls import path
from apps.schools.control_plane import require_super_access_with_host
from . import views

urlpatterns = [
    path("c/", require_super_access_with_host(partial(views.wide_open, k=1)), name="c"),
]
"""
        )
        self.addCleanup(tree.cleanup)
        row = tree.by_name()["c"]
        self.assertEqual(row["view_symbol"], "wide_open")
        self.assertEqual(row["status"], "AUTHZ_PROVEN")

    def test_reexport_hop_is_followed(self):
        tree = FixtureTree(
            """
from django.urls import path
from .facade import staff_gated

urlpatterns = [path("d/", staff_gated, name="d")]
""",
            extra={"pkg/facade.py": "from .views import staff_gated\n"},
        )
        self.addCleanup(tree.cleanup)
        row = tree.by_name()["d"]
        self.assertEqual(row["status"], "AUTHZ_PROVEN")
        self.assertEqual(row["view_module"], "pkg.views")

    def test_include_is_a_mount_not_a_leaf(self):
        tree = FixtureTree(
            """
from django.urls import include, path

urlpatterns = [path("sub/", include("pkg.other_urls"))]
"""
        )
        self.addCleanup(tree.cleanup)
        rows = tree.rows()
        self.assertEqual(rows[0]["status"], "MOUNT")
        self.assertEqual(rows[0]["view_module"], "pkg.other_urls")
        self.assertEqual(scan_mod.unclassified_keys(rows), [])


class AstOrderingTests(unittest.TestCase):
    """The repo has been bitten by assuming ast.walk order. Verify, don't assume."""

    def test_ast_walk_is_breadth_first(self):
        """Verified, not assumed."""
        tree = ast.parse("x = [f(a(1)), g(2)]")
        names = [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]
        # Depth-first would yield x, f, a, g. Breadth-first yields the whole
        # shallower level (f, g) before descending to the nested a.
        self.assertEqual(names, ["x", "f", "g", "a"])
        self.assertLess(names.index("g"), names.index("a"))

    def test_augmented_urlpatterns_are_collected(self):
        """`urlpatterns +=` / `.append()` must not be a blind spot."""
        tree = FixtureTree(
            """
from django.urls import path
from .views import staff_gated, wide_open

urlpatterns = [path("base/", staff_gated, name="base")]
urlpatterns += [path("added/", staff_gated, name="added")]
urlpatterns.append(path("appended/", wide_open, name="appended"))
"""
        )
        self.addCleanup(tree.cleanup)
        rows = tree.rows()
        self.assertEqual(
            sorted(r["url_name"] for r in rows), ["added", "appended", "base"]
        )
        self.assertIn(
            "urls_fixture.py::appended::appended/", scan_mod.unclassified_keys(rows)
        )

    def test_scanner_output_is_line_ordered_not_walk_ordered(self):
        tree = FixtureTree(
            """
from django.urls import path
from .views import staff_gated

urlpatterns = [
    path("one/", staff_gated, name="one"),
    path("two/", staff_gated, name="two"),
    path("three/", staff_gated, name="three"),
]
"""
        )
        self.addCleanup(tree.cleanup)
        rows = tree.rows()
        self.assertEqual([r["url_name"] for r in rows], ["one", "two", "three"])
        self.assertEqual([r["line"] for r in rows], sorted(r["line"] for r in rows))


class CompareModeTests(unittest.TestCase):
    """The ratchet must fail on a NEW unclassified route and pass on a baselined one."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rmc_super_cmp_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tree = FixtureTree(
            """
from django.urls import path
from .views import wide_open

urlpatterns = [path("open/", wide_open, name="open")]
"""
        )
        self.addCleanup(self.tree.cleanup)
        self.baseline = self.tmp / "baseline.json"
        self.out = self.tmp / "out.json"

    def _run(self, *extra):
        return scan_mod.main(
            [
                "--urlconf", str(self.tree.urlconf),
                "--source-root", str(self.tree.tmp),
                "--out", str(self.out),
                "--baseline", str(self.baseline),
                "--quiet",
                *extra,
            ]
        )

    def test_compare_fails_when_no_baseline_exists(self):
        self.assertEqual(self._run("--compare"), 1)

    def test_compare_fails_on_a_route_missing_from_baseline(self):
        self.baseline.write_bytes(
            json.dumps({"unclassified": [], "partially_classified": []}).encode("utf-8")
        )
        self.assertEqual(self._run("--compare"), 1)

    def test_compare_passes_once_the_route_is_baselined(self):
        self.assertEqual(self._run("--write-baseline"), 0)
        self.assertEqual(self._run("--compare"), 0)

    def test_written_baseline_records_the_unclassified_route(self):
        self._run("--write-baseline")
        data = json.loads(self.baseline.read_bytes().decode("utf-8"))
        self.assertEqual(data["unclassified"], ["urls_fixture.py::open::open/"])

    def test_baseline_is_written_with_crlf(self):
        """var/*.json follows the repo default (CRLF working tree)."""
        self._run("--write-baseline")
        raw = self.baseline.read_bytes()
        self.assertIn(b"\r\n", raw)
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))

    def test_inventory_json_is_written_with_lf(self):
        """docs/generated/*.json is `text eol=lf` in .gitattributes."""
        self._run()
        raw = self.out.read_bytes()
        self.assertNotIn(b"\r\n", raw)


class LiveTreeTests(unittest.TestCase):
    """Calibration against the real control plane."""

    URLCONF = ROOT / "apps" / "schools" / "super_urls.py"

    @unittest.skipUnless(URLCONF.is_file(), "super_urls.py not present")
    def test_route_count_matches_the_urlconf(self):
        rows = scan_mod.scan(self.URLCONF, ROOT)
        src = self.URLCONF.read_bytes().decode("utf-8")
        raw = sum(
            1
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in {"path", "re_path"}
        )
        self.assertEqual(len(rows), raw)
        self.assertGreater(
            len(rows), 200, "corpus collapsed - a zero here would prove nothing"
        )

    @unittest.skipUnless(URLCONF.is_file(), "super_urls.py not present")
    def test_resolver_actually_resolves(self):
        """Guard against a resolver that fails open and calls everything proven."""
        rows = scan_mod.scan(self.URLCONF, ROOT)
        leaf = [r for r in rows if r["status"] != "MOUNT"]
        resolved = [r for r in leaf if r["view_kind"]]
        self.assertGreater(
            len(resolved) / len(leaf),
            0.95,
            "view-definition resolution collapsed; guard counts cannot be trusted",
        )

    @unittest.skipUnless(URLCONF.is_file(), "super_urls.py not present")
    def test_live_super_urls_mutation_is_caught(self):
        """MUTATION: plant an unguarded route into the real urlconf."""
        clean = scan_mod.scan(self.URLCONF, ROOT)
        clean_flagged = set(scan_mod.unclassified_keys(clean)) | set(
            scan_mod.partial_keys(clean)
        )

        src = self.URLCONF.read_bytes()
        digest_before = hashlib.sha256(src).hexdigest()

        # Keep the mutant inside apps/schools so its relative imports resolve
        # exactly as the real file's do.
        mutant = self.URLCONF.parent / "_super_urls_mutant_tmp.py"
        self.addCleanup(lambda: mutant.unlink(missing_ok=True))

        # A view defined right here: no decorator, no URL wrapper.
        planted = chr(10).join(
            [
                "",
                "",
                "def _planted_unguarded_view(request):",
                "    return None",
                "",
                "",
                "urlpatterns.append(",
                "    path(",
                '        "planted-unguarded/",',
                "        _planted_unguarded_view,",
                '        name="planted_unguarded",',
                "    )",
                ")",
                "",
            ]
        ).encode("utf-8")
        mutant.write_bytes(src + planted)

        # The real file must be untouched by this test.
        self.assertEqual(
            hashlib.sha256(self.URLCONF.read_bytes()).hexdigest(), digest_before
        )

        rows = scan_mod.scan(mutant, ROOT)
        planted_rows = [r for r in rows if r["url_name"] == "planted_unguarded"]
        self.assertEqual(len(planted_rows), 1, "planted route was not seen at all")
        row = planted_rows[0]
        self.assertEqual(
            row["status"],
            "UNGUARDED",
            "planted unguarded route was scored {}".format(row["status"]),
        )
        self.assertEqual(row["authz_guards"], [])

        mutant_flagged = set(scan_mod.unclassified_keys(rows)) | set(
            scan_mod.partial_keys(rows)
        )
        new = mutant_flagged - clean_flagged
        self.assertTrue(new, "mutation produced no new finding - the gate cannot fail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
