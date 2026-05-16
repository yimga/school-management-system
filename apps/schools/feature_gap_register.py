"""
Feature Gap Register — SOT for "what we say we ship" vs "what's actually
demonstrably wired up." Closes the section N item "end_to_end_feature_gap_register"
that previously had no spec to compare against.

The register is the spec. Each row pins a named feature to a status
(`shipped` | `in_progress` | `planned`) and, when shipped, names the
proof: a route, a model class, a management command, or a CI gate. A
regression test asserts every `shipped` row's proof actually resolves.

Add a row HERE before claiming a feature in marketing. Removing a row
removes the public promise — never do that silently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class FeatureRow:
    """One platform feature with status + proof location."""

    feature_slug: str
    """Stable kebab-case key. Stored in dashboards; never renamed."""

    label: str
    """Human-readable feature name."""

    capability_domain: str
    """Coarse grouping: identity / billing / classroom / reporting / governance / integrations / studio_os / observability / ai."""

    status: str = "shipped"
    """`shipped` | `in_progress` | `planned`."""

    proof_route_name: str | None = None
    """Django URL name that demonstrates the feature is wired up."""

    proof_model: str | None = None
    """`app_label.ModelName` of the canonical model backing the feature."""

    proof_management_command: str | None = None
    """Name of a `python manage.py <cmd>` that exercises the feature."""

    proof_ci_gate: str | None = None
    """Name of the architectural CI gate (scanner) that enforces the feature."""

    public_promise: bool = False
    """True if marketing surfaces this feature. Drives drift assertions."""

    notes: str = ""

    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FEATURE_REGISTER: tuple[FeatureRow, ...] = (
    FeatureRow(
        feature_slug="ai-center",
        label="AI Center (unified governed assistants)",
        capability_domain="ai",
        proof_route_name="siteconfig:ai_center",
        public_promise=True,
        notes="One canonical surface for every governed AI assistant. Replaces per-page broken cards.",
    ),
    FeatureRow(
        feature_slug="ai-governance",
        label="AI governance dashboard",
        capability_domain="ai",
        proof_route_name="siteconfig:ai_governance",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="role-permission-matrix",
        label="Role / permission matrix scanner + CI gate",
        capability_domain="governance",
        proof_ci_gate="audit_role_permission_matrix",
        notes="v2.83 ratchet at --max-candidate-anonymous 66. Per-file alias resolution + auth-mixin propagation.",
    ),
    FeatureRow(
        feature_slug="public-to-product-promise-matrix",
        label="Public-to-Product Promise Matrix",
        capability_domain="governance",
        proof_route_name="manager_public_to_product_matrix",
        public_promise=True,
        notes="Manager-host surface; data SOT in apps/schools/public_product_promise_matrix.py.",
    ),
    FeatureRow(
        feature_slug="feature-gap-register",
        label="Feature gap register (this surface)",
        capability_domain="governance",
        proof_route_name="manager_feature_gap_register",
        public_promise=False,
    ),
    FeatureRow(
        feature_slug="data-quality-center",
        label="Data Quality Center",
        capability_domain="governance",
        proof_route_name="compliance:data_quality_center",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="api-center",
        label="API Center (integrations + keys + webhooks)",
        capability_domain="integrations",
        proof_route_name="apicenter:dashboard",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="integrations-marketplace",
        label="Integrations Marketplace (Zoom/Meet/Teams/Outlook/Gmail/Slack)",
        capability_domain="integrations",
        proof_route_name="integrations_marketplace:hub",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="studio-os-shell",
        label="Studio OS shell",
        capability_domain="studio_os",
        proof_route_name="studio_os:shell",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="studio-os-control",
        label="Studio OS — Control mode",
        capability_domain="studio_os",
        proof_route_name="studio_os:control",
    ),
    FeatureRow(
        feature_slug="studio-os-experience",
        label="Studio OS — Experience mode",
        capability_domain="studio_os",
        proof_route_name="studio_os:experience",
    ),
    FeatureRow(
        feature_slug="studio-os-automation",
        label="Studio OS — Automation mode",
        capability_domain="studio_os",
        proof_route_name="studio_os:automation",
    ),
    FeatureRow(
        feature_slug="studio-os-output",
        label="Studio OS — Output mode",
        capability_domain="studio_os",
        proof_route_name="studio_os:output",
    ),
    FeatureRow(
        feature_slug="studio-os-launch",
        label="Studio OS — Launch mode",
        capability_domain="studio_os",
        proof_route_name="studio_os:launch",
    ),
    FeatureRow(
        feature_slug="help-center",
        label="Help Center landing",
        capability_domain="governance",
        proof_route_name="feedback:help_center",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="release-notes",
        label="Public release notes feed",
        capability_domain="governance",
        proof_route_name="feedback:release_notes_public",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="notification-preferences",
        label="User notification preferences (per-channel)",
        capability_domain="identity",
        proof_route_name="accounts:notification_preferences",
        notes="v2.84. Channels: email / sms / push / in_app + weekly_summary toggle.",
    ),
    FeatureRow(
        feature_slug="first-school-readiness-preflight",
        label="First-school readiness preflight",
        capability_domain="governance",
        proof_management_command="verify_platform_readiness",
        notes="6 criteria per tenant: academic_year, term, classroom, active_teacher, active_student, brand_name.",
    ),
    FeatureRow(
        feature_slug="first-school-operating-proof",
        label="First-school operating proof (Playwright)",
        capability_domain="governance",
        proof_ci_gate="first-school-operating-proof.yml",
        notes="8-stage lifecycle; needs 3 staging secrets to activate.",
    ),
    FeatureRow(
        feature_slug="render-parity-probe",
        label="Render-parity probe (deployed vs local routes)",
        capability_domain="observability",
        proof_ci_gate="render-parity.yml",
    ),
    FeatureRow(
        feature_slug="api-center-browser-proof",
        label="API Center browser proof (Playwright)",
        capability_domain="integrations",
        proof_ci_gate="first-school-operating-proof.yml",
        notes="API Center spec lives alongside the first-school proof workflow.",
    ),
    FeatureRow(
        feature_slug="tenant-isolation-scanner",
        label="Tenant isolation scanner (RLS-style enforcement)",
        capability_domain="governance",
        proof_ci_gate="scan_tenant_queryset_safety",
        notes="Baseline 730. Annotate cross-tenant queries with `# tenant-isolation-allow:`.",
    ),
    FeatureRow(
        feature_slug="bank-account-dual-auth",
        label="Bank account four-eyes dual auth",
        capability_domain="billing",
        proof_model="finance.BankAccountChangeRequest",
        notes="v2.60. State machine PENDING→APPROVED/REJECTED/EXPIRED.",
    ),
    FeatureRow(
        feature_slug="impersonation-dual-control",
        label="School impersonation dual-control",
        capability_domain="identity",
        proof_model="schools.School",
        notes="Pattern shared with BankAccount dual-auth (v2.60).",
    ),
    FeatureRow(
        feature_slug="csp-enforce-mode",
        label="CSP enforce mode (style-src self only)",
        capability_domain="governance",
        proof_ci_gate="scan_inline_style_off_token",
        notes="v2.60 flip. Zero-tolerance gate; baseline 0.",
    ),
    FeatureRow(
        feature_slug="emotional-ux-confidence",
        label="Emotional UX confidence audit",
        capability_domain="governance",
        status="planned",
        notes="Subjective; needs user testing or design review, not a scanner.",
    ),
    FeatureRow(
        feature_slug="feedback-loop-live-usage",
        label="Feedback loop live usage telemetry",
        capability_domain="governance",
        status="planned",
        notes="Needs real-user data; harness is wired but consumption not yet metered.",
    ),
)


def iter_features() -> tuple[FeatureRow, ...]:
    return FEATURE_REGISTER


def feature_slugs() -> frozenset[str]:
    return frozenset(f.feature_slug for f in FEATURE_REGISTER)


def get_feature(slug: str) -> FeatureRow | None:
    for f in FEATURE_REGISTER:
        if f.feature_slug == slug:
            return f
    return None


def features_by_domain() -> dict[str, list[FeatureRow]]:
    out: dict[str, list[FeatureRow]] = {}
    for f in FEATURE_REGISTER:
        out.setdefault(f.capability_domain, []).append(f)
    return out
