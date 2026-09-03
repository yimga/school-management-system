"""The tenant-queryset scanner must catch a real leak and ignore a real scope.

This scanner reads ONE call expression. That made it cry at four shapes that
cannot cross a tenant - a primary-key lookup, a scope that arrives through a
related field, a scope applied on the next line to the same name, and a scope
applied by the wrapper the queryset is handed to. 36 of its findings were of
that kind, so its baseline was frozen at zero and it was never wired into the
pre-push hook. An unkeepable gate and a bypassed gate produce the same thing:
no signal.

Both directions are asserted here on purpose. Teaching a scanner to stay quiet
is easy; the only thing that makes the quiet worth anything is the other half of
this file, which fails the moment the scanner stops seeing a genuine leak.
"""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

_SCANNER = Path(__file__).resolve().parents[3] / "scripts" / "scan_tenant_queryset_safety.py"
_spec = importlib.util.spec_from_file_location("scan_tenant_queryset_safety", _SCANNER)
scanner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scanner)

TENANT_MODELS = {"Widget"}


def _scan(snippet: str):
    """Run the real scanner over a snippet and return its findings."""
    # Inside the repo: scan_file() reports paths via relative_to(REPO_ROOT),
    # which raises for anything outside it.
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False, encoding="utf-8", dir=scanner.REPO_ROOT / "var"
    )
    try:
        handle.write(snippet)
        handle.close()
        return scanner.scan_file(Path(handle.name), TENANT_MODELS)
    finally:
        Path(handle.name).unlink(missing_ok=True)


class TheScannerStillCatchesARealLeakTests(SimpleTestCase):
    """If any of these stops failing, the scanner has been fixed into silence."""

    def test_a_bare_filter_on_a_tenant_model_is_flagged(self):
        self.assertTrue(_scan("Widget.objects.filter(name='x')\n"))

    def test_objects_all_on_a_tenant_model_is_flagged(self):
        self.assertTrue(_scan("rows = Widget.objects.all()\n"))

    def test_an_unscoped_update_is_flagged(self):
        # The dangerous one: one query rewrites every tenant's row.
        self.assertTrue(_scan("Widget.objects.filter(status='p').update(status='q')\n"))

    def test_an_unscoped_delete_is_flagged(self):
        self.assertTrue(_scan("Widget.objects.filter(status='p').delete()\n"))

    def test_a_non_school_foreign_key_is_not_a_scope(self):
        # user_id is a FK, not this model's identity, and not a school.
        self.assertTrue(_scan("Widget.objects.filter(user_id=uid)\n"))

    def test_a_lookalike_field_is_not_a_scope(self):
        # `schoolyear` merely starts with the word.
        self.assertTrue(_scan("Widget.objects.filter(schoolyear=y)\n"))

    def test_narrowing_a_DIFFERENT_name_does_not_launder_the_leak(self):
        snippet = (
            "def view(request):\n"
            "    rows = Widget.objects.all()\n"
            "    other = other.filter(school=request.school)\n"
            "    return rows\n"
        )
        self.assertTrue(_scan(snippet), "scoping some other queryset must not clear this one")


class TheScannerIgnoresAScopeItCanSeeTests(SimpleTestCase):
    """The four shapes that produced the noise. None can cross a tenant."""

    def test_a_primary_key_lookup_is_scoped(self):
        # A pk is globally unique: you cannot reach another tenant's row with
        # the pk of a row you are already holding.
        self.assertEqual(_scan("Widget.objects.filter(pk=obj.pk)\n"), [])
        self.assertEqual(_scan("Widget.objects.get(pk=obj.pk)\n"), [])
        self.assertEqual(_scan("Widget.objects.filter(pk__in=ids).update(x=1)\n"), [])
        self.assertEqual(_scan("Widget.objects.filter(id=widget_id)\n"), [])

    def test_a_scope_through_a_related_field_is_scoped(self):
        self.assertEqual(_scan("Widget.objects.filter(donor__school_id=sid)\n"), [])
        self.assertEqual(_scan("Widget.objects.filter(bundle__school=school)\n"), [])
        self.assertEqual(_scan("Widget.objects.filter(a__b__school_id=sid)\n"), [])

    def test_a_scope_applied_to_the_same_name_afterwards_is_scoped(self):
        snippet = (
            "def picker(request):\n"
            "    qs = Widget.objects.all()\n"
            "    if request.school:\n"
            "        qs = qs.filter(school=request.school)\n"
            "    return qs\n"
        )
        self.assertEqual(_scan(snippet), [])

    def test_a_queryset_handed_to_a_scoping_wrapper_is_scoped(self):
        snippet = (
            "def feed(request):\n"
            "    return queryset_for_scope(\n"
            "        Widget.objects.filter(is_active=True),\n"
            "        school=school,\n"
            "        platform_scope=platform_scope,\n"
            "    )\n"
        )
        self.assertEqual(_scan(snippet), [])

    def test_the_plain_school_kwarg_still_passes(self):
        self.assertEqual(_scan("Widget.objects.filter(school=school)\n"), [])
        self.assertEqual(_scan("Widget.objects.filter(school_id=sid)\n"), [])

    def test_a_non_tenant_model_is_never_flagged(self):
        self.assertEqual(_scan("Gadget.objects.all()\n"), [])
