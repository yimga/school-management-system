"""Find and repair rows that can never sync because nothing owns them.

Edge sync ships a school's rows with ``model.objects.filter(school=school)``
(``edge_outbox.build_edge_delta_rows``). A row whose ``school_id`` is NULL matches
that filter for NO school, so it is not "failing to sync" -- it is structurally
ineligible, forever, and silently.

That is not hypothetical. On production every academics row was unowned (4/4
departments, 7/7 specialties, all ``school_id=NULL``), so a tenant's entire
curriculum could never reach its box. Worse, a child row that DID ship while its
unowned parent could not produced a dangling FK on the box, and because Postgres
defers FK checks the box lost the WHOLE pull at COMMIT, every cycle.

Ownership is INFERRED, never guessed: an unowned row is claimed only when rows
that reference it (walked via reverse FKs, restricted to referrers that carry
their own ``school``) all point at one school. Anything ambiguous or foreign is
reported and left untouched -- assigning a row to the wrong tenant is a data
leak, which is strictly worse than a row that does not sync.

Tenant-wide by construction: nothing here is school-specific, so the edge
onboarding runbook can run it for whichever school is being brought up.
"""
from __future__ import annotations

from contextlib import contextmanager

from django.conf import settings

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# How a candidate was classified. Only ASSIGNABLE is ever written.
ASSIGNABLE = "assignable"   # referrers all point at THIS school
FOREIGN = "foreign"         # referrers point at a DIFFERENT school -- never touch
AMBIGUOUS = "ambiguous"     # referrers span several schools -- never touch
ORPHAN = "orphan"           # nothing references it; no evidence of an owner


@dataclass
class OwnershipCandidate:
    entity_type: str
    label: str
    pk: object
    verdict: str
    evidence: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        return {
            "entity_type": self.entity_type,
            "model": self.label,
            "pk": self.pk,
            "verdict": self.verdict,
            "evidence": self.evidence,
        }


def _has_school_field(model) -> bool:
    return any(
        getattr(f, "name", None) == "school"
        for f in model._meta.get_fields()
        if getattr(f, "concrete", False)
    )


def _referrer_school_ids(model, pk) -> dict:
    """School ids of rows referencing ``pk``, per referring model.

    Walks reverse FKs and consults only referrers that carry their OWN ``school``
    -- a referrer without one cannot testify to ownership. Read-only.
    """
    found: dict[str, set] = {}
    for rel in model._meta.related_objects:
        related_model = rel.related_model
        if not _has_school_field(related_model):
            continue
        try:
            ids = set(
                related_model._default_manager.filter(**{rel.field.name: pk})
                .exclude(school__isnull=True)
                .values_list("school_id", flat=True)
                .distinct()
            )
        except Exception:  # noqa: BLE001 — a bad reverse relation must not stop the audit
            logger.debug(
                "ownership_repair: reverse lookup failed for %s via %s",
                related_model._meta.label, rel.field.name, exc_info=True,
            )
            continue
        if ids:
            found[related_model._meta.label] = ids
    return found


def _classify(model, pk, school_id) -> OwnershipCandidate:
    referrers = _referrer_school_ids(model, pk)
    owners: set = set()
    for ids in referrers.values():
        owners |= ids
    evidence = {label: sorted(str(i) for i in ids) for label, ids in referrers.items()}
    if not owners:
        verdict = ORPHAN
    elif owners == {school_id}:
        verdict = ASSIGNABLE
    elif school_id in owners:
        verdict = AMBIGUOUS
    else:
        verdict = FOREIGN
    return OwnershipCandidate(
        entity_type="", label=model._meta.label, pk=pk, verdict=verdict, evidence=evidence
    )


@contextmanager
def _school_schema(school):
    """Run the body inside ``school``'s Postgres schema, when there is one.

    THE BUG THIS FIXES. Under ``USE_DJANGO_TENANTS`` (what ``render.yaml`` sets)
    every tenant table lives in ``s_<uuid-hex>``, and ``public`` holds only the shared
    apps. Both entry points below query ``model._default_manager`` with no schema
    switch, so on the cloud they inspected whichever schema the connection happened to
    be on — ``public`` for a management command — where the tenant tables are either
    absent or hold unrelated legacy rows.

    That is not a subtle inaccuracy. Run live against gilead-tech on 2026-08-20 it
    reported **572 unowned rows needing repair** while the tenant's real schema held
    420 correctly-owned students and exactly ONE unowned row. An operator who had
    passed ``--apply`` would have been writing school ownership onto rows in the
    public schema on the strength of an audit that never looked at the school.

    A box (``USE_DJANGO_TENANTS=0``, shared DB + RLS) has one schema and needs no
    switch, so this is a no-op there — which is why the bug was invisible in the
    place the code was written and tested.
    """
    schema = (getattr(school, "schema_name", "") or "").strip()
    if not getattr(settings, "USE_DJANGO_TENANTS", False) or not schema:
        yield
        return
    try:
        from django_tenants.utils import schema_context
    except ImportError:  # pragma: no cover - django_tenants absent on a box
        yield
        return
    with schema_context(schema):
        yield


def plan_ownership_repair(school, *, config=None) -> dict:
    """Read-only audit: which unowned rows could be claimed by ``school``.

    Returns ``{"candidates": [...], "counts": {...}}``. Never writes.
    """
    from apps.api.sync_services import _get_entity_config

    config = config if config is not None else _get_entity_config(include_derived=True)
    school_id = getattr(school, "pk", school)
    candidates: list[OwnershipCandidate] = []
    with _school_schema(school):
        for entity_type, (model, _allowed) in sorted(config.items()):
            if not _has_school_field(model):
                continue
            try:
                unowned = list(
                    model._default_manager.filter(school__isnull=True)
                    .values_list("pk", flat=True)[:500]
                )
            except Exception:  # noqa: BLE001 — never let one model break the whole audit
                logger.debug(
                    "ownership_repair: scan failed for %s", entity_type, exc_info=True
                )
                continue
            for pk in unowned:
                candidate = _classify(model, pk, school_id)
                candidate.entity_type = entity_type
                candidates.append(candidate)

    counts: dict[str, int] = {}
    for c in candidates:
        counts[c.verdict] = counts.get(c.verdict, 0) + 1
    return {"candidates": candidates, "counts": counts, "school_id": str(school_id)}


def apply_ownership_repair(school, *, plan=None, include_orphans: bool = False) -> dict:
    """Assign inferred-owner rows to ``school``. Writes ONLY safe verdicts.

    ``ASSIGNABLE`` rows are claimed. ``ORPHAN`` rows are claimed only with
    ``include_orphans`` -- there is no evidence for them, so that is an operator
    decision, not a default. ``FOREIGN`` / ``AMBIGUOUS`` are NEVER written.
    """
    from django.db import transaction

    from apps.api.sync_services import _get_entity_config

    config = _get_entity_config(include_derived=True)
    plan = plan if plan is not None else plan_ownership_repair(school, config=config)
    allowed = {ASSIGNABLE} | ({ORPHAN} if include_orphans else set())
    school_id = getattr(school, "pk", school)

    by_entity: dict[str, list] = {}
    for c in plan["candidates"]:
        if c.verdict in allowed:
            by_entity.setdefault(c.entity_type, []).append(c.pk)

    updated: dict[str, int] = {}
    with _school_schema(school), transaction.atomic():
        for entity_type, pks in by_entity.items():
            model, _allowed_fields = config[entity_type]
            n = (
                model._default_manager.filter(pk__in=pks, school__isnull=True)
                .update(school_id=school_id)
            )
            if n:
                updated[entity_type] = n
                logger.warning(
                    "ownership_repair: claimed %s unowned %s row(s) for school %s",
                    n, entity_type, school_id,
                )
    return {"updated": updated, "total": sum(updated.values())}
