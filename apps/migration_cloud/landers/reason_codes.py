"""Why a row was held — as a value, not as English prose to be re-read later.

Step 2 of ``docs/MIGRATION_CLOUD_ZERO_TOUCH_IMPORT_SPEC.md``.

The single most consequential routing decision in the import pipeline — does this
row need a human? — was made by substring-matching the error message::

    if "invalid" in e or "not found" in e or "unresolved" in e: return "invalid_ref"

That is not a classifier, it is a coincidence. Measured across all 108 per-row
failure sites in ``apps/migration_cloud/landers/`` on 2026-08-21, **68 fell
through to** ``lander_error`` — the bucket that means "a person must look at
this" — and many of them plainly should not have:

* ``no team named X (catalog not landed yet)`` is a wave-ordering ``invalid_ref``.
  It matched neither ``"not found"`` nor ``"no such"``, so it read as a crash.
* ``no recipient resolved for parent P`` is ``invalid_ref``.
* ``no score or letter for S / Maths / T1`` is ``missing_required``.
* ``this row does not say which staff member it belongs to`` is
  ``missing_required`` — the phrasing was deliberately made human-readable, which
  is exactly what stopped the matcher recognising it.

So a lander now DECLARES the reason. ``classify_message`` survives only as the
fallback for a site that has not declared one yet, and every use of it is
recorded as a fallback (``reason_source="fallback"``) so the remaining backlog is
countable rather than invisible.

The vocabulary is deliberately the five classes the review surface already
speaks (``apps/migration_cloud/views.py::QUARANTINE_ISSUE_LABELS``). Inventing a
sixth here would change what a tenant is shown without anyone deciding it should
change; the win in this pass is routing rows to the RIGHT existing bucket, not
adding buckets.
"""

from __future__ import annotations

from typing import Final

#: The source system marked this row deleted, so it was deliberately not
#: imported. A correct outcome. Needs nobody.
SOURCE_DELETION: Final = "source_deletion"

#: The record already exists here and the write was skipped. Needs nobody.
DUPLICATE: Final = "duplicate"

#: The row points at something that could not be resolved — a class, a student, a
#: team. Often a wave-ordering artefact rather than bad data, which is why step 3
#: of the spec can replay these rather than ask a person.
INVALID_REF: Final = "invalid_ref"

#: A value the domain requires was absent or empty in the source file.
MISSING_REQUIRED: Final = "missing_required"

#: Anything else — including a genuine exception from the write. This is the
#: "we do not know" bucket, and a row landing here is a request for a human, so
#: it should be the LAST resort and never the default for a known condition.
LANDER_ERROR: Final = "lander_error"

ALL_REASON_CODES: Final = frozenset({
    SOURCE_DELETION,
    DUPLICATE,
    INVALID_REF,
    MISSING_REQUIRED,
    LANDER_ERROR,
})

#: Classes that are a correct outcome, not a problem for anyone to fix. Mirrors
#: ``views.QUARANTINE_NO_ACTION_CLASSES``; kept here too so a lander can reason
#: about it without importing the view layer.
NO_ACTION_REASON_CODES: Final = frozenset({SOURCE_DELETION, DUPLICATE})


def classify_message(message: str) -> str:
    """Guess a reason code from an error string. The legacy path.

    Preserved byte-for-byte from ``orchestrator._classify_quarantine_issue`` so
    adopting the structured contract cannot silently reclassify a site that has
    not been reviewed. Call sites that pass an explicit ``reason_code`` never
    reach this.
    """
    e = (message or "").lower()
    # A source-deletion HOLD is not a failure — it is a tobedeleted structural row
    # deliberately not imported as active.
    if "held for review" in e or ("marked this" in e and "deleted" in e):
        return SOURCE_DELETION
    if "duplicate" in e or "unique" in e or "already exists" in e:
        return DUPLICATE
    if "invalid" in e or "not found" in e or "unresolved" in e or "no such" in e:
        return INVALID_REF
    if "missing" in e or "required" in e or "not provided" in e:
        return MISSING_REQUIRED
    return LANDER_ERROR


def normalize_reason_code(value: object) -> str | None:
    """Return ``value`` if it names a known class, else ``None``.

    Unknown codes are dropped rather than stored: an ``issue_class`` the review
    surface has no label for renders as a title-cased slug to a school
    administrator, which is worse than falling back to a class we can explain.
    """
    code = str(value or "").strip().lower()
    return code if code in ALL_REASON_CODES else None
