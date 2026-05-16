"""Public-to-Product Promise Matrix.

Single source of truth tying every public marketing promise to the product
route that delivers it. Used by:
 - the operator-facing matrix surface (`/manager/public-to-product/`)
 - a CI test that asserts every `status="shipped"` row resolves a real route

The point: if marketing says "Trust Center", a product page MUST exist at the
promised URL — otherwise we mislead buyers. Adding a row here is the cheapest
way to keep the two surfaces honest. Adding a row with status=`shipped` but no
resolvable route fails the regression test.

Wave 6 (v2.77).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class PromiseRow:
    """A single promise the public site makes, plus where the product delivers it."""

    promise_slug: str
    """Stable kebab-case key. Stored in dashboards, never re-renamed."""

    promise: str
    """Short human-readable claim (e.g. 'Trust Center')."""

    public_route_name: str
    """Django URL name on the root urlconf that surfaces the promise on marketing."""

    product_route_name: str | None
    """Django URL name (tenant or manager) that delivers the promise. None for static-only promises."""

    product_route_kwargs: dict | None = None
    """Optional kwargs for `reverse(product_route_name, kwargs=...)`."""

    status: str = "shipped"
    """`shipped` | `in-flight` | `planned`. Drives both CI assertion and dashboard color."""

    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


PUBLIC_TO_PRODUCT_PROMISES: tuple[PromiseRow, ...] = (
    PromiseRow(
        promise_slug="trust-center",
        promise="Trust Center",
        public_route_name="marketing_trust_center",
        product_route_name="compliance:dashboard",
        status="shipped",
        notes="Marketing trust page links to the tenant Compliance Dashboard.",
    ),
    PromiseRow(
        promise_slug="release-notes",
        promise="What's new / release notes",
        public_route_name="marketing_landing",
        product_route_name="feedback:release_notes_public",
        status="shipped",
        notes="v2.68: public feed `/release-notes/` backed by `ReleaseNote.is_public`.",
    ),
    PromiseRow(
        promise_slug="help-center",
        promise="In-app Help Center",
        public_route_name="marketing_landing",
        product_route_name="feedback:help_center",
        status="shipped",
        notes="v2.68: tenant Help Center bridging KB + feedback + contact.",
    ),
    PromiseRow(
        promise_slug="data-quality",
        promise="Data Quality Center",
        public_route_name="marketing_landing",
        product_route_name="compliance:data_quality_center",
        status="shipped",
        notes="v2.76: tenant DQ surface with 4 real completeness checks.",
    ),
    PromiseRow(
        promise_slug="onboarding-checklist",
        promise="School activation checklist",
        public_route_name="onboard_wizard",
        product_route_name="siteconfig:onboarding",
        status="shipped",
        notes="Data-driven progress: links each step to its real setup page.",
    ),
    PromiseRow(
        promise_slug="migration-cloud",
        promise="Migration Cloud (universal-first)",
        public_route_name="migrate_marketing_page",
        product_route_name="accounts:migration_wizard",
        status="shipped",
        notes="U1-U9 complete; 7 accelerators (OneRoster, PowerSchool, Blackbaud, Veracross, FACTS, Skyward, Alma).",
    ),
    PromiseRow(
        promise_slug="integrations-hub",
        promise="Integrations marketplace",
        public_route_name="marketing_integrations",
        product_route_name="integrations_marketplace:hub",
        status="shipped",
        notes="v2.72: 23-provider connector registry + per-tenant OAuth + 4-step cascade.",
    ),
    PromiseRow(
        promise_slug="api-center",
        promise="Public APIs / developer center",
        public_route_name="marketing_developers",
        product_route_name="apicenter:dashboard",
        status="shipped",
        notes="DRF schema coverage gate enforces every API view is annotated.",
    ),
    PromiseRow(
        promise_slug="parent-portal",
        promise="Parent portal",
        public_route_name="role_parents",
        product_route_name="accounts:redirect",
        status="shipped",
        notes="Routed via role-aware redirect after parent login.",
    ),
    PromiseRow(
        promise_slug="teacher-portal",
        promise="Teacher portal",
        public_route_name="role_teachers",
        product_route_name="accounts:redirect",
        status="shipped",
    ),
    PromiseRow(
        promise_slug="student-portal",
        promise="Student portal",
        public_route_name="role_students",
        product_route_name="accounts:redirect",
        status="shipped",
    ),
    PromiseRow(
        promise_slug="data-residency",
        promise="EU / regional data residency",
        public_route_name="marketing_security_compliance",
        product_route_name=None,
        status="shipped",
        notes="K4 readiness preflight + DataResidencyRouter; documented at `docs/compliance/DATA_RESIDENCY_LEGAL_GUIDE.md`.",
    ),
    PromiseRow(
        promise_slug="institutional-stamp",
        promise="Verified-tenant institutional stamp on outbound mail",
        public_route_name="marketing_security_compliance",
        product_route_name=None,
        status="shipped",
        notes="v2.64 Pillar 3: DKIM posture + `{% institutional_stamp %}` template tag.",
    ),
)


def all_promises() -> list[dict[str, Any]]:
    """Materialized list — safe to JSON-serialize, used by the template + dashboard."""
    return [p.to_dict() for p in PUBLIC_TO_PRODUCT_PROMISES]


def status_counts() -> dict[str, int]:
    out = {"shipped": 0, "in-flight": 0, "planned": 0}
    for p in PUBLIC_TO_PRODUCT_PROMISES:
        out[p.status] = out.get(p.status, 0) + 1
    out["total"] = sum(out.values())
    return out
