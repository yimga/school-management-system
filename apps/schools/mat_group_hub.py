"""Wave J (v3.95.0 — 2026-05-26) — MAT (Multi-Academy Trust) Group Hub.

A *MAT* (or district, or network) groups several independent tenants under
one operational umbrella. The hub lets a group operator see rolled-up KPIs
across all member schools: admissions pipeline, fee collection rate,
attendance, results, staff headcount.

**Tenant isolation is preserved.** This module never executes a cross-tenant
queryset. Instead:

1. The MAT registry is built from ``Organization`` + group-member ``School`` rows
   when schools opt into group mode (Phase 6). Legacy operator
   ``cockpit_payload["mat_groups"]`` JSON still fills gaps for groups not yet
   backed by Organization rows.
2. The aggregator iterates the member tenant slugs and runs the metric
   provider *once per tenant scope* (each query is naturally tenant-scoped
   via Django's tenant routing), then sums in Python.
3. The metric provider is a pluggable callable; tests inject mocks so
   `tenant_scope_runner` is exercised without spinning up real schools.

Boundary: NO direct ORM queries across the `school_id` boundary. The
``tenant_scope_runner`` callback is the seam that enforces scope.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MATMember:
    """A single tenant within a MAT group."""

    tenant_slug: str
    display_name: str
    region: str = ""  # e.g. "UK-North", "NG-Lagos"


@dataclass(frozen=True)
class MATGroup:
    """A group of tenants operated under one trust / district."""

    group_id: str
    display_name: str
    members: tuple[MATMember, ...]
    operator_email: str = ""
    region: str = ""


@dataclass
class MATGroupKPISnapshot:
    """A rolled-up snapshot of group-wide metrics at a point in time."""

    group_id: str
    member_count: int
    total_students: int = 0
    total_staff: int = 0
    admissions_pipeline_count: int = 0
    fees_collected_minor: int = 0
    fees_outstanding_minor: int = 0
    attendance_rate_pct: float = 0.0
    pass_rate_pct: float = 0.0
    per_member: list[dict[str, Any]] = field(default_factory=list)
    failed_members: list[str] = field(default_factory=list)


# Default metric keys the aggregator expects each member provider to return.
_METRIC_KEYS: tuple[str, ...] = (
    "students",
    "staff",
    "admissions_pipeline",
    "fees_collected_minor",
    "fees_outstanding_minor",
    "attendance_rate_pct",
    "pass_rate_pct",
)


# ---------------------------------------------------------------------------
# Registry parsing
# ---------------------------------------------------------------------------

def parse_mat_registry(raw: Any) -> tuple[MATGroup, ...]:
    """Parse the operator-controlled MAT registry payload.

    Expected shape::

        {
          "trust-greenwich": {
            "display_name": "Greenwich Academy Trust",
            "operator_email": "ops@greenwich.example",
            "region": "UK-London",
            "members": [
              {"tenant_slug": "greenwich-park", "display_name": "Greenwich Park School", "region": "UK-London"},
              {"tenant_slug": "greenwich-meridian", "display_name": "Meridian Primary", "region": "UK-London"},
            ],
          }
        }

    Returns the parsed registry; silently drops malformed entries.
    """
    if not isinstance(raw, dict):
        return ()
    out: list[MATGroup] = []
    for group_id, payload in raw.items():
        if not isinstance(group_id, str) or not isinstance(payload, dict):
            continue
        members_raw = payload.get("members") or []
        if not isinstance(members_raw, list):
            continue
        members: list[MATMember] = []
        for m in members_raw:
            if not isinstance(m, dict):
                continue
            slug = (m.get("tenant_slug") or "").strip()
            if not slug:
                continue
            members.append(MATMember(
                tenant_slug=slug,
                display_name=(m.get("display_name") or slug).strip(),
                region=(m.get("region") or "").strip(),
            ))
        if not members:
            continue
        out.append(MATGroup(
            group_id=group_id,
            display_name=(payload.get("display_name") or group_id).strip(),
            members=tuple(members),
            operator_email=(payload.get("operator_email") or "").strip(),
            region=(payload.get("region") or "").strip(),
        ))
    return tuple(out)


def load_registry_from_operator_settings() -> tuple[MATGroup, ...]:
    """Pull the effective MAT registry (Organization-derived + legacy JSON).

    Organization-backed groups take precedence over ``cockpit_payload`` entries
    with the same ``group_id``. Returns () when unavailable or unconfigured.
    Fail-open."""
    try:
        from apps.governance.mat_groups_sync import resolve_mat_groups_payload

        raw = resolve_mat_groups_payload()
        return parse_mat_registry(raw)
    except Exception:  # noqa: BLE001
        pass
    try:
        from apps.platform_runtime.helpers import get_platform_site_settings_record

        ss = get_platform_site_settings_record(create=False)
    except Exception:  # noqa: BLE001
        return ()
    if ss is None:
        return ()
    payload = getattr(ss, "cockpit_payload", None) or {}
    if not isinstance(payload, dict):
        return ()
    raw = payload.get("mat_groups")
    return parse_mat_registry(raw)


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

def _empty_member_record(member: MATMember) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "tenant_slug": member.tenant_slug,
        "display_name": member.display_name,
        "region": member.region,
    }
    for k in _METRIC_KEYS:
        rec[k] = 0
    rec["error"] = ""
    return rec


def aggregate_group_kpis(
    group: MATGroup,
    *,
    tenant_scope_runner: Callable[[str, MATMember], dict[str, Any]],
) -> MATGroupKPISnapshot:
    """Roll up KPIs across all member tenants.

    ``tenant_scope_runner`` is the per-member metric provider. It MUST run
    its queries in the member tenant's scope (this is what preserves
    isolation). The aggregator only sums the returned dicts. Expected return
    keys: ``students``, ``staff``, ``admissions_pipeline``,
    ``fees_collected_minor``, ``fees_outstanding_minor``,
    ``attendance_rate_pct``, ``pass_rate_pct``.

    Failed members are recorded in ``failed_members`` but do NOT abort the
    rollup — the operator sees partial data rather than no data.
    """
    snap = MATGroupKPISnapshot(
        group_id=group.group_id,
        member_count=len(group.members),
    )
    students = staff = pipeline = 0
    collected = outstanding = 0
    attendance_acc: list[float] = []
    pass_acc: list[float] = []

    for member in group.members:
        rec = _empty_member_record(member)
        try:
            metrics = tenant_scope_runner(member.tenant_slug, member) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "mat_group_hub member metric runner failed group=%s tenant=%s err=%s",
                group.group_id, member.tenant_slug, exc,
            )
            rec["error"] = str(exc) or "metric runner raised"
            snap.failed_members.append(member.tenant_slug)
            snap.per_member.append(rec)
            continue

        for k in _METRIC_KEYS:
            v = metrics.get(k, 0)
            try:
                rec[k] = float(v) if "pct" in k else int(v)
            except (TypeError, ValueError):
                rec[k] = 0

        students += int(rec["students"])
        staff += int(rec["staff"])
        pipeline += int(rec["admissions_pipeline"])
        collected += int(rec["fees_collected_minor"])
        outstanding += int(rec["fees_outstanding_minor"])
        if rec["attendance_rate_pct"] > 0:
            attendance_acc.append(float(rec["attendance_rate_pct"]))
        if rec["pass_rate_pct"] > 0:
            pass_acc.append(float(rec["pass_rate_pct"]))

        snap.per_member.append(rec)

    snap.total_students = students
    snap.total_staff = staff
    snap.admissions_pipeline_count = pipeline
    snap.fees_collected_minor = collected
    snap.fees_outstanding_minor = outstanding
    snap.attendance_rate_pct = (
        round(sum(attendance_acc) / len(attendance_acc), 2)
        if attendance_acc else 0.0
    )
    snap.pass_rate_pct = (
        round(sum(pass_acc) / len(pass_acc), 2)
        if pass_acc else 0.0
    )
    return snap


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def find_group_by_id(groups: Iterable[MATGroup], group_id: str) -> MATGroup | None:
    for g in groups:
        if g.group_id == group_id:
            return g
    return None


def member_count(group: MATGroup) -> int:
    return len(group.members)


def all_member_tenant_slugs(groups: Iterable[MATGroup]) -> tuple[str, ...]:
    """All distinct tenant slugs participating in any MAT — useful for
    operator-side cron filters."""
    seen: set[str] = set()
    out: list[str] = []
    for g in groups:
        for m in g.members:
            if m.tenant_slug not in seen:
                seen.add(m.tenant_slug)
                out.append(m.tenant_slug)
    return tuple(out)
