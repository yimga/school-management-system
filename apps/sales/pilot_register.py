"""
Pilot tracker register.

Lane-2 scaffolding: actual pilot deals are external (sales work), but tracking
which pilots are pending / in-flight / completed and their go/no-go gates is
internal. This is the operator-facing SOT.

When a pilot moves forward, update its row HERE FIRST so the operator
dashboard and downstream comms templates stay aligned. Removing a row =
removing the pilot from the platform record; don't do it silently.

For real prospect data (names, contracts, dates), use the CRM/finance side.
This register is the *internal preparedness checklist*: what stage is each
pilot in, what's the next gate, which platform features are blocking it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PilotRow:
    """One pilot tenant or prospect tracked at the platform level."""

    pilot_slug: str
    """Stable kebab-case key. Map to tenant subdomain when live."""

    label: str
    """Short display name (e.g., 'Gilead Tech High', 'Mountain Bay Academy')."""

    stage: str = "prospect"
    """`prospect` | `mou` | `provisioning` | `live` | `paid` | `paused` | `lost`."""

    region: str = "global"
    """`global` | `africa` | `emea` | `apac` | `americas`."""

    institution_type: str = "k12"
    """`k12` | `university` | `district` | `vocational` | `multi_campus`."""

    blocking_features: tuple[str, ...] = ()
    """Slugs from feature_gap_register that block this pilot moving to `live`."""

    blocking_psps: tuple[str, ...] = ()
    """PSP slugs the pilot needs but we haven't certified."""

    next_gate: str = ""
    """One-line description of the next decision/milestone."""

    target_go_live_quarter: str = ""
    """e.g., '2026-Q3'. Free text; not a hard date."""

    operator_notes: str = ""

    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PILOT_REGISTER: tuple[PilotRow, ...] = (
    PilotRow(
        pilot_slug="gilead-tech-high",
        label="Gilead Tech High (first-school staging)",
        stage="live",
        region="africa",
        institution_type="k12",
        next_gate="Convert from 'live (staging)' to 'paid' once first-school operating proof flips to green on every PR.",
        target_go_live_quarter="2026-Q2",
        operator_notes="Used as the platform's first-school operating proof target. Playwright spec scaffolded; needs RMC_STAGING_* secrets.",
    ),
    PilotRow(
        pilot_slug="reference-multi-campus",
        label="Reference multi-campus deployment",
        stage="prospect",
        region="africa",
        institution_type="multi_campus",
        blocking_features=("integrations-marketplace",),
        blocking_psps=("paystack", "flutterwave"),
        next_gate="Confirm per-campus integrations work end-to-end with at least one payments rail certified.",
        target_go_live_quarter="2026-Q3",
        operator_notes="Per-campus connector cascade is built; needs a real prospect to exercise it under load.",
    ),
    PilotRow(
        pilot_slug="reference-district",
        label="Reference district deployment",
        stage="prospect",
        region="americas",
        institution_type="district",
        blocking_features=("api-center",),
        next_gate="Validate the district aggregates API with at least one district customer's data volume.",
        target_go_live_quarter="2026-Q4",
    ),
    PilotRow(
        pilot_slug="diaspora-tuition-remittance",
        label="Diaspora tuition remittance pilot",
        stage="prospect",
        region="global",
        institution_type="k12",
        blocking_psps=("paypal", "stripe"),
        next_gate="Certify Stripe + PayPal adapter and document FX disclosure.",
        target_go_live_quarter="2026-Q4",
        operator_notes="Use case: parent abroad pays in USD/EUR/GBP; school settles in local currency.",
    ),
)


def iter_pilots() -> tuple[PilotRow, ...]:
    return PILOT_REGISTER


def pilot_slugs() -> frozenset[str]:
    return frozenset(p.pilot_slug for p in PILOT_REGISTER)


def get_pilot(slug: str) -> PilotRow | None:
    for p in PILOT_REGISTER:
        if p.pilot_slug == slug:
            return p
    return None


def stage_counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for p in PILOT_REGISTER:
        out[p.stage] = out.get(p.stage, 0) + 1
    return out
