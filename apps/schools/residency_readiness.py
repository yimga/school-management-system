"""Wave K4 — preflight check for ``DATA_RESIDENCY_ENFORCE=True``.

Flipping data-residency enforcement from soft-log to hard-raise is a
one-line change in production — but the consequences if it's flipped
prematurely are bad (every misaligned tenant 500s on every request).
This module is the preflight that turns "flip the switch" into a
verifiable readiness check.

Checks performed:

1. **Replica coverage** — every region that's actively in use (by any
   ``is_active=True`` school's ``effective_region``) has a matching
   ``replica_<region>`` alias in ``settings.DATABASES``.
2. **Alignment** — every active school's
   ``regional_cluster == effective_region``. Misalignments would 500
   under enforcement.
3. **Backfill** — no active school has a blank ``data_region`` whose
   country maps to a non-``global`` derived region. (Run
   ``verify_data_residency --fix-derive`` to fix.)

Returns a structured ``ReadinessReport`` rather than raising so the
management command can format it nicely and exit appropriately.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings


@dataclass
class ReadinessReport:
    """Outcome of the preflight check."""

    ready: bool = True
    schools_total: int = 0
    schools_active_regions: set[str] = field(default_factory=set)
    missing_replicas: list[str] = field(default_factory=list)
    misaligned_schools: list[tuple[str, str, str]] = field(default_factory=list)
    """List of ``(school_slug, regulatory, operational)`` triples."""
    unbackfilled_schools: list[tuple[str, str, str]] = field(default_factory=list)
    """List of ``(school_slug, country_code, derived_region)`` triples."""
    registered_replica_aliases: dict[str, str] = field(default_factory=dict)
    """Snapshot of ``settings.DATA_RESIDENCY_REPLICA_ALIASES`` at check time."""

    def issue_count(self) -> int:
        return (
            len(self.missing_replicas)
            + len(self.misaligned_schools)
            + len(self.unbackfilled_schools)
        )


def _replica_aliases() -> dict[str, str]:
    """Region → DB-alias map from settings, with safe fallback to {}."""
    raw = getattr(settings, "DATA_RESIDENCY_REPLICA_ALIASES", None)
    return dict(raw) if isinstance(raw, dict) else {}


def assess_readiness(*, slug_filter: str = "") -> ReadinessReport:
    """Run the full preflight; never raises.

    When ``slug_filter`` is supplied, only that school is examined —
    useful for narrowing down "why does this tenant fail?" investigations.
    """
    from apps.schools.data_residency import (
        derive_default_region,
        effective_region,
    )
    from apps.schools.models import School

    report = ReadinessReport()
    report.registered_replica_aliases = _replica_aliases()

    # tenant-isolation-allow: residency readiness scans every tenant by design
    qs = School.objects.filter(is_active=True).only(
        "slug", "country_code", "data_region", "regional_cluster",
    )
    if slug_filter:
        qs = qs.filter(slug=slug_filter)

    for school in qs.iterator():
        report.schools_total += 1
        regulatory = effective_region(school)
        operational = (school.regional_cluster or "").strip()
        if regulatory != "global":
            report.schools_active_regions.add(regulatory)

        # Misalignment check: only schools with both fields populated and
        # differing trigger an enforcement-time failure.
        if operational and operational != regulatory:
            report.misaligned_schools.append(
                (school.slug, regulatory, operational)
            )

        # Backfill check: a blank data_region whose country maps to a
        # non-global derived region should be filled before enforcement.
        explicit = (school.data_region or "").strip()
        if not explicit:
            derived = derive_default_region(school.country_code or "")
            if derived and derived != "global":
                report.unbackfilled_schools.append(
                    (school.slug, (school.country_code or "--"), derived)
                )

    # Replica coverage: every active region needs a replica alias, except
    # "global" which is served by the default DB by definition.
    aliases = report.registered_replica_aliases
    for region in sorted(report.schools_active_regions):
        if region == "global":
            continue
        if region not in aliases:
            report.missing_replicas.append(region)

    report.ready = report.issue_count() == 0
    return report


__all__ = ["ReadinessReport", "assess_readiness"]
