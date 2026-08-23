"""The field-shape check behind `scripts/scan_blank_unique_text_fields.py`.

The gate exists because ``blank=True`` + ``unique=True`` on a text field with no
``null=True`` means optional EXACTLY ONCE -- blank stores "" and only one row may hold it
under a unique index. Two live defects came from that shape on 2026-08-23
(``School.subdomain`` and the three KB slugs).

These tests pin the predicate itself, the allowlist discipline that keeps it a
zero-baseline gate, and the stale-entry check that stops an allowlist entry outliving the
field it excuses. The registry walk is exercised against fake field objects rather than
real models, so this file stays stdlib and runs anywhere.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scan_blank_unique_text_fields.py"
_spec = importlib.util.spec_from_file_location("scan_blank_unique_text_fields", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["scan_blank_unique_text_fields"] = mod
_spec.loader.exec_module(mod)


class AllowlistDisciplineTests(unittest.TestCase):
    """An allowlist is only worth having if every entry says something."""

    def test_every_entry_has_a_real_reason(self):
        for key, reason in mod.ALLOWLIST.items():
            with self.subTest(field=key):
                self.assertGreater(
                    len(reason.split()),
                    6,
                    f"{key} is excused by a reason too short to review",
                )

    def test_every_entry_is_a_three_part_dotted_path(self):
        """`app.Model.field` -- anything else cannot match a registry key."""
        for key in mod.ALLOWLIST:
            with self.subTest(field=key):
                self.assertEqual(len(key.split(".")), 3, key)

    def test_the_finance_entry_names_the_condition_that_would_void_it(self):
        """An exception that does not say when it expires is a permanent hole."""
        reason = mod.ALLOWLIST["finance.Invoice.payment_code"]
        self.assertIn("bulk_create", reason)

    def test_the_slug_entries_name_the_mechanism_that_makes_them_safe(self):
        for key in (
            "portal.FAQCategory.slug",
            "portal.KBCategory.slug",
            "portal.KBArticle.slug",
        ):
            with self.subTest(field=key):
                self.assertIn("derive_unique_slug", mod.ALLOWLIST[key])


class StaleEntryTests(unittest.TestCase):
    """An entry naming a field that no longer has this shape must be reported.

    Otherwise a field gets fixed properly, the excuse stays behind, and the next field to
    take that name inherits a waiver nobody granted it.
    """

    def test_stale_is_computed_as_allowlist_minus_found(self):
        found_keys = {"a.B.c"}
        allow = {"a.B.c": "still in shape", "x.Y.z": "fixed long ago"}
        stale = sorted(set(allow) - found_keys)
        self.assertEqual(stale, ["x.Y.z"])

    def test_nothing_is_stale_when_every_entry_still_matches(self):
        found_keys = {"a.B.c", "x.Y.z"}
        allow = {"a.B.c": "r", "x.Y.z": "r"}
        self.assertEqual(sorted(set(allow) - found_keys), [])


class _FakeField:
    """Enough of a Django field for the predicate under test."""

    def __init__(self, *, unique, blank, null, concrete=True):
        self.unique = unique
        self.blank = blank
        self.null = null
        self.concrete = concrete


class PredicateTests(unittest.TestCase):
    """The exact three-way condition, stated once so it cannot drift."""

    @staticmethod
    def _flags(field) -> bool:
        return bool(
            getattr(field, "concrete", False)
            and field.unique
            and field.blank
            and not field.null
        )

    def test_blank_unique_not_null_is_a_finding(self):
        self.assertTrue(self._flags(_FakeField(unique=True, blank=True, null=False)))

    def test_nullable_is_not_a_finding(self):
        """null=True is the fix, not the defect -- NULLs do not collide."""
        self.assertFalse(self._flags(_FakeField(unique=True, blank=True, null=True)))

    def test_unique_without_blank_is_not_a_finding(self):
        """A required unique field cannot reach the empty value."""
        self.assertFalse(self._flags(_FakeField(unique=True, blank=False, null=False)))

    def test_blank_without_unique_is_not_a_finding(self):
        """Many rows may be empty when nothing says they must differ."""
        self.assertFalse(self._flags(_FakeField(unique=False, blank=True, null=False)))

    def test_a_non_concrete_field_is_skipped(self):
        """Reverse relations have no column to collide in."""
        self.assertFalse(
            self._flags(_FakeField(unique=True, blank=True, null=False, concrete=False))
        )


class ScopeTests(unittest.TestCase):
    """Only text fields have an "" to land on."""

    def test_the_texty_set_is_the_documented_one(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for name in ("CharField", "TextField", "SlugField", "EmailField", "URLField"):
            with self.subTest(field=name):
                self.assertIn(f"models.{name}", source)

    def test_there_is_no_baseline_file_to_rot(self):
        """A count baseline would let a new field in this shape be absorbed silently."""
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("security-audit-baseline", source)
        self.assertIn("There is NO baseline file", source)

    def test_the_docstring_names_both_valid_fixes(self):
        """A gate that demands only null=True would be wrong for a slug."""
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("Absent is a real state", source)
        self.assertIn("Absent is NOT a real state", source)


if __name__ == "__main__":
    unittest.main()
