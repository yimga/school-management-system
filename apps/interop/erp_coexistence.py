"""
ERP / finance coexistence — canonical patterns for customer SIS+ERP deployments.

End-to-end in code: event names, webhook shape, and API Center handoff. Live ERP endpoints
still require customer credentials; this module is the product contract operators sell against.
"""

from __future__ import annotations

from typing import Any, Final

# Customer systems we document + test webhooks against (tenant configures URL in API Center).
ERP_COEXISTENCE_PATTERNS: Final[tuple[dict[str, str], ...]] = (
    {
        "code": "sap_s4hana",
        "label": "SAP S/4HANA Finance",
        "motion": "Outbound: student fee sync, vendor invoice status. Inbound: cost center mapping.",
        "webhook_events": "student.updated, finance.gl_posting.ack",
    },
    {
        "code": "workday_financial",
        "label": "Workday Financial",
        "motion": "Staff cost allocation + procurement requisitions mirrored from HR roster.",
        "webhook_events": "hr.position.updated, finance.requisition.status",
    },
    {
        "code": "oracle_fusion",
        "label": "Oracle Fusion / NetSuite (education)",
        "motion": "Subsidiary per campus; intercompany eliminations for district roll-ups.",
        "webhook_events": "finance.invoice.posted, student.enrollment.delta",
    },
    {
        "code": "powerschool_erp",
        "label": "PowerSchool ERP / eFinancePlus class",
        "motion": "US K-12 district: meal eligibility + ADA-driven revenue recognition hooks.",
        "webhook_events": "attendance.daily.summary, finance.revenue.recognition",
    },
    {
        "code": "microsoft_dynamics",
        "label": "Microsoft Dynamics 365 Finance",
        "motion": "Entra SSO alignment; OData export profiles from API Center.",
        "webhook_events": "identity.user.provisioned, finance.payment.settled",
    },
    {
        "code": "generic_rest_erp",
        "label": "Generic REST / iPaaS (MuleSoft, Boomi, Workato)",
        "motion": "Signed webhooks + idempotency keys; customer maps to their ERP canonical model.",
        "webhook_events": "* (scoped subscription)",
    },
)


def list_patterns() -> tuple[dict[str, str], ...]:
    return ERP_COEXISTENCE_PATTERNS


def sample_webhook_envelope(*, event: str, school_id: str) -> dict[str, Any]:
    """JSON-safe envelope for docs and dry-run tests (no PII)."""
    return {
        "schema_version": "1.0",
        "event": event,
        "school_id": str(school_id),
        "idempotency_key": "erp-demo-key",
        "payload_ref": "https://api.runmycampus.com/docs/erp-webhook-payloads",
    }
