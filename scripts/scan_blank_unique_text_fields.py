"""A text field that is blank=True AND unique=True is optional EXACTLY ONCE.

WHY THIS EXISTS. ``blank=True`` reads as "this may be left empty". ``unique=True`` reads
as "no two rows may share a value". Together, on a text field with no ``null=True``, they
mean something nobody intends: blank stores ``""`` rather than NULL, and Postgres and
SQLite both treat ``""`` as an ordinary value under a unique index while treating NULLs as
distinct from one another. So the FIRST row may be left empty and the SECOND raises
IntegrityError. The field is not optional; it is optional once.

Two live defects came from exactly this shape, found on 2026-08-23:

  * ``School.subdomain`` -- the second school created without a subdomain died. Reachable
    from the OneRoster importer, the schools API, CSV imports, and any bare
    ``School.objects.create()``. Through the admin it surfaced as "School with this
    Subdomain already exists" on a field the user had left EMPTY, which sends somebody
    hunting for a duplicate that does not exist. Fixed by schools/0087.
  * ``portal.FAQCategory/KBCategory/KBArticle.slug`` -- ``slugify`` drops every character
    it cannot transliterate, so ``slugify("教育")`` and ``slugify("التعليم")`` are both
    "". The models assigned that unguarded, so a school's FIRST help article in Arabic
    saved and the SECOND raised IntegrityError. This platform ships 17 locales including
    Arabic, so that is the ordinary case for a school writing its own help centre.

WHY THE LIVE REGISTRY, NOT THE SOURCE. A source scan would have to guess field classes,
and it misses fields inherited from an abstract base or a mixin -- which is where a shared
``slug`` most often lives. ``_meta.get_fields()`` knows exactly what shipped. The cost is
that this gate needs Django, so it runs in ci.yml and in pre_push_boundary_check's
DJANGO_GATES phase rather than the deps-free boundary job.

WHAT IT DOES NOT FLAG. ``null=True`` alongside them is the fix, not the defect -- NULLs do
not collide. A field that is unique WITHOUT blank is a required field and cannot reach the
empty value. A non-text field has no "" to land on.

FIXING ONE. There are exactly two honest answers, and which one is right depends on
whether an ABSENT value is meaningful for that field:

  1. Absent is a real state -- make it NULL. ``null=True``, plus normalise ``""`` to None
     in ``save()`` (a ModelForm hands back "" for an untouched CharField even when the
     field is nullable, and importers construct the model directly), plus a migration
     converting existing "" rows with the AlterField ordered FIRST, since the column must
     accept NULL before one can be written. ``School.subdomain`` took this route
     (schools/0087) because a school without a subdomain is reached at /t/<slug>/ and
     every consumer already read ``subdomain or slug``.
  2. Absent is NOT a real state -- guarantee a value. Derive one in ``save()`` that is
     non-empty AND not already taken. The KB slugs took this route: a slug should never
     be NULL, it should always be derived, and ``derive_unique_slug`` closes empty and
     colliding in that order. Note that a bare fallback is not enough on its own -- if
     every non-Latin title falls back to "article", the second one collides on THAT.

Either way you write the decision down here, which is the point: the shape itself is a
trap, and the gate exists to make somebody say which of the two they applied.

There is NO baseline file. A field in this state is a defect or a documented decision, and
the ALLOWLIST below is where a decision goes so it is reviewable. A stale allowlist entry
-- one naming a field that no longer has this shape -- is itself reported, so an entry
cannot outlive its field and quietly re-open the hole.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# "app_label.Model.field" -> why this one is deliberate.
ALLOWLIST: dict[str, str] = {
    # Route 2 (see FIXING ONE): save() derives a guaranteed non-empty, non-colliding slug
    # via portal.models_kb.derive_unique_slug, so "" can no longer reach the column. NULL
    # would be wrong here -- a slug is what the URL is built from, and every one of these
    # rows has a name or title to derive from.
    # Enforced by apps/portal/tests/test_kb_slug_non_latin_2026_08_23.py, which is
    # mutation-proven: revert the derivation and 8 of its 14 tests fail.
    "portal.FAQCategory.slug": "derive_unique_slug in save() -- never empty, never taken",
    "portal.KBCategory.slug": "derive_unique_slug in save() -- never empty, never taken",
    "portal.KBArticle.slug": "derive_unique_slug in save() -- never empty, never taken",
    "finance.Invoice.payment_code": (
        "Not the same defect. Invoice.save() writes '' on INSERT and immediately UPDATEs "
        "to INV-<id>-<short>, so the '' slot is vacated before the next invoice needs it, "
        "and no code path bulk_creates Invoices. Reviewed 2026-08-23 and left alone: it "
        "is fragile rather than broken, and money code is not somewhere to make a "
        "speculative change. If a bulk_create of Invoice ever lands, this stops being "
        "true and the field needs the schools/0087 treatment."
    ),
}


def _texty(field) -> bool:
    from django.db import models

    return isinstance(
        field,
        (
            models.CharField,
            models.TextField,
            models.SlugField,
            models.EmailField,
            models.URLField,
        ),
    )


def find_optional_once_fields() -> list[tuple[str, str, str]]:
    """Every concrete text field that is blank + unique and cannot hold NULL."""
    from django.apps import apps as django_apps

    hits: list[tuple[str, str, str]] = []
    for model in django_apps.get_models():
        for field in model._meta.get_fields():
            if not getattr(field, "concrete", False) or not _texty(field):
                continue
            if field.unique and field.blank and not field.null:
                hits.append(
                    (f"{model._meta.label}.{field.name}", type(field).__name__, model._meta.app_label)
                )
    return sorted(hits)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = parser.parse_args()

    import django

    django.setup()

    found = find_optional_once_fields()
    found_keys = {key for key, _cls, _app in found}
    findings = [(k, c, a) for k, c, a in found if k not in ALLOWLIST]
    stale = sorted(set(ALLOWLIST) - found_keys)

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "finding_count": len(findings),
                    "findings": [{"field": k, "class": c, "app": a} for k, c, a in findings],
                    "allowed": sorted(ALLOWLIST),
                    "stale_allowlist_entries": stale,
                },
                indent=2,
            )
        )
        return 1 if findings or stale else 0

    for key, cls, _app in findings:
        print(f"  {key}  ({cls})")
        print("      blank=True + unique=True + not nullable: only ONE row may be empty.")
    for key in stale:
        print(f"  STALE ALLOWLIST: {key} no longer has this shape -- remove the entry.")

    checked = len(found)
    if findings or stale:
        print(
            f"\nblank+unique text fields: {len(findings)} unreviewed, "
            f"{len(stale)} stale allowlist entry(ies)."
        )
        print("Fix: null=True + normalise '' to None in save() + migrate '' rows to NULL")
        print("     (AlterField first). See apps/schools/migrations/0087 for the shape.")
        print("     A deliberate exception goes in this script's ALLOWLIST with a reason.")
        return 1

    print(
        f"blank+unique text fields: {checked} in this shape, "
        f"{len(ALLOWLIST)} reviewed and allowed, 0 unreviewed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
