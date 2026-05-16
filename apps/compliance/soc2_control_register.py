"""
SOC2 Type II control register.

Lane-2 scaffolding: SOC2 attestation is external (auditor work), but mapping
each Trust Services Criteria (TSC) common-control to its in-platform evidence
source is internal and tractable. This register is the SOT.

When SOC2 fieldwork begins, this is what the auditor sees first. Each row
has: control_id (AICPA TSC numbering), description, owner, and
`evidence_source` pointing to the in-platform artifact (a route, a model, a
scanner, or an audit-log query).

The regression test asserts every `status="implemented"` row has at least one
evidence source that resolves.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SOC2Control:
    """One SOC2 TSC common-control mapped to in-platform evidence."""

    control_id: str
    """AICPA control reference (e.g., 'CC6.1', 'CC7.2', 'PI1.4')."""

    label: str
    """Short description of what the control demands."""

    category: str
    """`security` | `availability` | `processing_integrity` | `confidentiality` | `privacy`."""

    status: str = "implemented"
    """`implemented` | `partial` | `planned`."""

    evidence_route_name: str | None = None
    """Operator-facing surface that demonstrates the control."""

    evidence_model: str | None = None
    """`app_label.ModelName` where audit rows live."""

    evidence_scanner: str | None = None
    """Name of the architectural CI scanner that enforces it."""

    owner_role: str = "platform-engineering"
    """Team that owns ongoing operation."""

    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SOC2_REGISTER: tuple[SOC2Control, ...] = (
    SOC2Control(
        control_id="CC6.1",
        label="Logical access — only authorized users access systems.",
        category="security",
        evidence_route_name="siteconfig:ai_governance",
        evidence_scanner="audit_role_permission_matrix",
        notes="RBAC matrix scanner enforces zero candidate-anonymous; ai-governance surfaces principal access.",
    ),
    SOC2Control(
        control_id="CC6.2",
        label="Authentication includes MFA / SSO where required.",
        category="security",
        evidence_route_name="super:ai_gateway_console",
        notes="Passkey-only enforcement guard in login_view (v2.64 Pillar 1).",
    ),
    SOC2Control(
        control_id="CC6.6",
        label="Session integrity — sessions tied to known device/IP envelope.",
        category="security",
        evidence_model="compliance.AuditLog",
        notes="SessionPinningMiddleware (v2.64 Pillar 1) flushes session on IP/UA mismatch and writes a CRITICAL audit row.",
    ),
    SOC2Control(
        control_id="CC6.7",
        label="Data-in-transit protections — TLS to all platform endpoints.",
        category="security",
        evidence_scanner="check_real_migration_drift",
        notes="HSTS, CSP enforce mode (v2.60), inline-style-off-token gate at 0.",
    ),
    SOC2Control(
        control_id="CC6.8",
        label="Privileged-access change requires four-eyes / dual auth.",
        category="security",
        evidence_model="finance.BankAccountChangeRequest",
        notes="BankAccount dual-auth (v2.60) + School impersonation dual-control share the M-of-N pattern.",
    ),
    SOC2Control(
        control_id="CC7.1",
        label="System monitoring — anomalies surface to operators.",
        category="availability",
        evidence_route_name="manager_feedback_loop",
        notes="Feedback loop + friction telemetry + AuditLog feed.",
    ),
    SOC2Control(
        control_id="CC7.2",
        label="Security event log retained and searchable.",
        category="security",
        evidence_model="compliance.AuditLog",
        notes="AuditLog is the canonical row-level audit. Per-tenant scoped.",
    ),
    SOC2Control(
        control_id="CC7.3",
        label="Incident response — declared, triaged, communicated.",
        category="availability",
        evidence_route_name="feedback:help_center",
        status="partial",
        notes="Help Center landing exists; formal incident timeline + post-mortem template pending.",
    ),
    SOC2Control(
        control_id="CC8.1",
        label="Change management — code changes reviewed before merge.",
        category="processing_integrity",
        evidence_scanner="check_documented_baselines",
        notes="11 architectural CI gates enforce contracts; PR merge requires them green.",
    ),
    SOC2Control(
        control_id="PI1.4",
        label="Data quality — inputs validated, errors surfaced.",
        category="processing_integrity",
        evidence_route_name="compliance:data_quality_center",
        notes="Data Quality Center (v2.76) ships 4 real tenant-scoped checks.",
    ),
    SOC2Control(
        control_id="C1.1",
        label="Confidential information classified and protected.",
        category="confidentiality",
        evidence_scanner="scan_tenant_queryset_safety",
        notes="Tenant-isolation scanner at baseline 730; new cross-tenant queries require `# tenant-isolation-allow:` markers.",
    ),
    SOC2Control(
        control_id="C1.2",
        label="Confidential information disposed of per policy.",
        category="confidentiality",
        status="partial",
        notes="Per-tenant data residency module shipped; formal retention-policy enforcement pending.",
    ),
    SOC2Control(
        control_id="P3.2",
        label="Personal data collection has documented purpose + consent.",
        category="privacy",
        evidence_route_name="compliance:dashboard",
        notes="Trust Center + scope-consent UI (v2.64 Pillar 4) for marketplace installs.",
    ),
    SOC2Control(
        control_id="P5.1",
        label="Data subject access requests handled within policy SLA.",
        category="privacy",
        status="planned",
        notes="GDPR/FERPA SAR workflow needs dedicated build.",
    ),
)


def iter_controls() -> tuple[SOC2Control, ...]:
    return SOC2_REGISTER


def control_ids() -> frozenset[str]:
    return frozenset(c.control_id for c in SOC2_REGISTER)


def get_control(control_id: str) -> SOC2Control | None:
    for c in SOC2_REGISTER:
        if c.control_id == control_id:
            return c
    return None


def status_counts() -> dict[str, int]:
    out: dict[str, int] = {"implemented": 0, "partial": 0, "planned": 0}
    for c in SOC2_REGISTER:
        out[c.status] = out.get(c.status, 0) + 1
    return out
