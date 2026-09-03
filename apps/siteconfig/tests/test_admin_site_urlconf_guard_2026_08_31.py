"""Both admin sites must pin the request's urlconf before building the app dict.

``set_urlconf`` is THREAD-LOCAL. Django's handler sets it per request, so normal
traffic is fine -- but any in-process caller that renders both sites in one
process (a management command, a preview generator, an audit script, a test)
leaves it pointing at whichever site ran last. Django's own ``_build_app_dict``
then reverses ``admin:app_list`` against the WRONG url tree and raises
``NoReverseMatch``.

``BaseRunMyCampusAdminSite.get_app_list`` has always pinned it.
``PlatformAdminSite.get_app_list`` did not, and caught only ``LookupError`` --
so with a stale thread-local the operator site raised while the tenant site
self-corrected. Reproduced 2026-08-31:

    set_urlconf("config.tenant_urls")            # stale ambient state
    request.urlconf = "config.manager_urls"      # request is CORRECT
    platform_admin_site.get_app_list(request)
    -> NoReverseMatch: Reverse for 'app_list' ... {'app_label': 'customers'}

It is not a live 500 on normal traffic, and that is exactly what made it
expensive: it made TOOLING lie. A catalog-coverage audit reported a phantom
mismatch on the operator site until the urlconf was corrected per call.

Static by design: the runtime reproduction needs a database and two urlconfs,
and this pins the cheaper invariant -- that neither sibling can silently lose
the guard again.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
ADMIN_PY = REPO_ROOT / "config" / "admin.py"

# Every AdminSite subclass here that overrides get_app_list must carry the guard.
EXPECTED_SITES = {"BaseRunMyCampusAdminSite", "PlatformAdminSite"}


def _get_app_list_methods(source: str) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(source)
    found: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "get_app_list":
                found[node.name] = item
    return found


def _pins_urlconf(fn: ast.FunctionDef) -> bool:
    """Does the body call set_urlconf(...) before anything else meaningful?"""
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            name = getattr(f, "id", None) or getattr(f, "attr", None)
            if name == "set_urlconf":
                return True
    return False


def _catches_noreversematch(fn: ast.FunctionDef) -> bool:
    for node in ast.walk(fn):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        names = []
        t = node.type
        if isinstance(t, ast.Tuple):
            names = [getattr(e, "id", getattr(e, "attr", "")) for e in t.elts]
        else:
            names = [getattr(t, "id", getattr(t, "attr", ""))]
        if "NoReverseMatch" in names:
            return True
    return False


class AdminSiteUrlconfGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = ADMIN_PY.read_text(encoding="utf-8", errors="ignore")
        self.methods = _get_app_list_methods(self.source)

    def test_both_admin_sites_override_get_app_list(self) -> None:
        missing = sorted(EXPECTED_SITES - set(self.methods))
        self.assertEqual(
            missing, [], f"expected get_app_list on {missing} -- renamed or removed?"
        )

    def test_every_get_app_list_pins_the_request_urlconf(self) -> None:
        offenders = [
            name for name, fn in self.methods.items() if not _pins_urlconf(fn)
        ]
        self.assertEqual(
            offenders,
            [],
            f"{offenders} build the app dict without set_urlconf(request.urlconf); "
            "with a stale thread-local they reverse admin:app_list against the "
            "wrong url tree",
        )

    def test_every_get_app_list_catches_noreversematch(self) -> None:
        offenders = [
            name for name, fn in self.methods.items()
            if not _catches_noreversematch(fn)
        ]
        self.assertEqual(
            offenders,
            [],
            f"{offenders} catch only LookupError around _build_app_dict, but "
            "Django reverses admin:app_list there unguarded",
        )

    def test_the_readers_actually_discriminate(self) -> None:
        # Both assertions above pass by finding nothing, which is also how a
        # broken reader passes. Plant both defects and require a catch.
        bad = (
            "class S:\n"
            "    def get_app_list(self, request, app_label=None):\n"
            "        try:\n"
            "            d = self._build_app_dict(request, app_label)\n"
            "        except LookupError:\n"
            "            d = {}\n"
            "        return d\n"
        )
        good = (
            "class S:\n"
            "    def get_app_list(self, request, app_label=None):\n"
            "        u = getattr(request, 'urlconf', None)\n"
            "        if u:\n"
            "            set_urlconf(u)\n"
            "        try:\n"
            "            d = self._build_app_dict(request, app_label)\n"
            "        except (LookupError, NoReverseMatch):\n"
            "            d = {}\n"
            "        return d\n"
        )
        bad_fn = _get_app_list_methods(bad)["S"]
        good_fn = _get_app_list_methods(good)["S"]
        self.assertFalse(_pins_urlconf(bad_fn))
        self.assertFalse(_catches_noreversematch(bad_fn))
        self.assertTrue(_pins_urlconf(good_fn))
        self.assertTrue(_catches_noreversematch(good_fn))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
