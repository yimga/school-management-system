"""Wave T (v3.97.0 — 2026-05-26) — Smart-links kernel.

Single source of truth for "next-best-action" links across dead-end pages.

The platform was leaking value at state pages (frozen-account, photo-expired,
403, 404) that told users *what was wrong* but never linked to the action
that fixes it. This registry maps (state, persona) -> ordered list of
``SmartLink`` descriptors; a template tag resolves each entry against the
URL reverser and renders a button.

Design:
- Pure-Python; no Django imports here so the registry is unit-testable
  as ``SimpleTestCase`` without bringing up the URL resolver.
- Entries carry either ``url_name`` (preferred — reversed via ``{% url %}``)
  OR ``href`` (absolute path fallback when url_name unresolvable in the
  current host context). This keeps tenant / control-plane / marketing
  host splits working without a per-host registry.
- ``mailto`` entries skip URL reversal entirely (operator escalation).

Add new entries by appending to ``_REGISTRY`` — never branch in templates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# --- Persona + state constants --------------------------------------------

# Personas (keep aligned with role_registry; "any" matches every persona).
PERSONA_ANY = "any"
PERSONA_OPERATOR = "operator"
PERSONA_TENANT_ADMIN = "tenant_admin"
PERSONA_TEACHER = "teacher"
PERSONA_PARENT = "parent"
PERSONA_STUDENT = "student"
PERSONA_STAFF = "staff"

ALL_PERSONAS = (
    PERSONA_ANY,
    PERSONA_OPERATOR,
    PERSONA_TENANT_ADMIN,
    PERSONA_TEACHER,
    PERSONA_PARENT,
    PERSONA_STUDENT,
    PERSONA_STAFF,
)

# States (free-form keys — used as registry lookup tokens).
STATE_FROZEN_BILLING = "frozen.billing"
STATE_FROZEN_STORAGE = "frozen.storage"
STATE_FROZEN_OTHER = "frozen.other"
STATE_PHOTO_LINK_EXPIRED = "photo.link_expired"
STATE_PHOTO_FEATURE_DISABLED = "photo.feature_disabled"
STATE_ERROR_404 = "error.404"
STATE_ERROR_403 = "error.403"
STATE_ERROR_403_STAFF = "error.403_staff"
STATE_ERROR_403_CONTROL_PLANE = "error.403_control_plane"
STATE_ERROR_500 = "error.500"
STATE_ERROR_503 = "error.503"
STATE_OFFLINE = "error.offline"
STATE_RECORDS_HOLD_ACTIVE = "records.hold_active"
STATE_INVOICE_OVERDUE = "invoice.overdue"
STATE_ADMISSION_PENDING = "admission.pending_review"
STATE_DSL_CONCERN_OPEN = "safeguarding.concern_open"


# --- SmartLink descriptor -------------------------------------------------


@dataclass(frozen=True)
class SmartLink:
    """A next-best-action descriptor.

    Exactly one of ``url_name`` / ``href`` / ``mailto`` resolves to the link
    target; the template tag picks the first non-empty in that order.
    """

    label: str
    url_name: str = ""
    href: str = ""
    mailto: str = ""
    kwargs: dict[str, Any] = field(default_factory=dict)
    icon: str = "bi-arrow-right"
    severity: str = "primary"  # primary | secondary | danger | success
    # Optional copy shown under the button (one-liner explaining what the
    # action does, when label alone is ambiguous).
    helper_text: str = ""

    def __post_init__(self) -> None:
        sources = [bool(self.url_name), bool(self.href), bool(self.mailto)]
        if sum(sources) == 0:
            raise ValueError(
                f"SmartLink {self.label!r} must set one of url_name/href/mailto",
            )
        if self.severity not in {"primary", "secondary", "danger", "success"}:
            raise ValueError(
                f"SmartLink {self.label!r} severity {self.severity!r} invalid",
            )


# --- Registry -------------------------------------------------------------


# Tuple-of-tuples so callers can't mutate the table at runtime.
_REGISTRY: dict[tuple[str, str], tuple[SmartLink, ...]] = {
    # ---- Frozen account (BILLING) -------------------------------------
    (STATE_FROZEN_BILLING, PERSONA_ANY): (
        SmartLink(
            label="Update payment method",
            url_name="finance:dashboard",
            icon="bi-credit-card",
            severity="primary",
            helper_text="Resolve the declined card or switch payment rail.",
        ),
        SmartLink(
            label="Contact billing support",
            mailto="support@runmycampus.com?subject=Account+frozen+%E2%80%94+billing",
            icon="bi-life-preserver",
            severity="secondary",
        ),
        SmartLink(
            label="Sign out",
            url_name="accounts:logout",
            icon="bi-box-arrow-right",
            severity="secondary",
        ),
    ),
    # ---- Frozen account (STORAGE) -------------------------------------
    (STATE_FROZEN_STORAGE, PERSONA_ANY): (
        SmartLink(
            label="View storage usage",
            url_name="finance:dashboard",
            icon="bi-hdd",
            severity="primary",
            helper_text="See which records / uploads are using space.",
        ),
        SmartLink(
            label="Contact support",
            mailto="support@runmycampus.com?subject=Account+frozen+%E2%80%94+storage",
            icon="bi-life-preserver",
            severity="secondary",
        ),
        SmartLink(
            label="Sign out",
            url_name="accounts:logout",
            icon="bi-box-arrow-right",
            severity="secondary",
        ),
    ),
    # ---- Frozen account (other / fallback) ----------------------------
    (STATE_FROZEN_OTHER, PERSONA_ANY): (
        SmartLink(
            label="Contact support",
            mailto="support@runmycampus.com?subject=Account+on+hold",
            icon="bi-life-preserver",
            severity="primary",
        ),
        SmartLink(
            label="Sign out",
            url_name="accounts:logout",
            icon="bi-box-arrow-right",
            severity="secondary",
        ),
    ),
    # ---- Photo upload link expired ------------------------------------
    (STATE_PHOTO_LINK_EXPIRED, PERSONA_ANY): (
        SmartLink(
            label="Request a new link",
            mailto="?subject=Photo+upload+link+expired",
            icon="bi-envelope-arrow-up",
            severity="primary",
            helper_text="Email your school admin to resend the secure link.",
        ),
        SmartLink(
            label="Back to portal",
            url_name="accounts:redirect",
            icon="bi-house",
            severity="secondary",
        ),
    ),
    # ---- Photo feature disabled by school ------------------------------
    (STATE_PHOTO_FEATURE_DISABLED, PERSONA_ANY): (
        SmartLink(
            label="Upload on this device",
            url_name="accounts:redirect",
            icon="bi-camera",
            severity="primary",
            helper_text="Open the portal here and upload from the profile page.",
        ),
        SmartLink(
            label="Ask school to enable",
            mailto="?subject=Please+enable+remote+photo+upload",
            icon="bi-envelope",
            severity="secondary",
        ),
    ),
    # ---- 404 ----------------------------------------------------------
    (STATE_ERROR_404, PERSONA_ANY): (
        SmartLink(
            label="Search the help center",
            url_name="feedback:help_center",
            icon="bi-search",
            severity="primary",
            helper_text="Find the right page by keyword.",
        ),
        SmartLink(
            label="Go to dashboard",
            url_name="accounts:redirect",
            icon="bi-house",
            severity="secondary",
        ),
        SmartLink(
            label="Report a broken link",
            mailto="support@runmycampus.com?subject=Broken+link+(404)",
            icon="bi-bug",
            severity="secondary",
        ),
    ),
    # ---- 403 (tenant portal) ------------------------------------------
    (STATE_ERROR_403, PERSONA_ANY): (
        SmartLink(
            label="Go to dashboard",
            url_name="accounts:redirect",
            icon="bi-house",
            severity="primary",
        ),
        SmartLink(
            label="Request access",
            url_name="accounts:request_waiver",
            icon="bi-key",
            severity="secondary",
            helper_text="Ask an administrator to grant the missing permission.",
        ),
        SmartLink(
            label="Help center",
            url_name="feedback:help_center",
            icon="bi-search",
            severity="secondary",
        ),
    ),
    # ---- 403 (staff tried control-plane-only route) ---------------------
    (STATE_ERROR_403_STAFF, PERSONA_ANY): (
        SmartLink(
            label="Open backend dashboard",
            url_name="accounts:backend_dashboard",
            icon="bi-speedometer2",
            severity="primary",
        ),
        SmartLink(
            label="Review access status",
            url_name="accounts:security_trust_hub",
            icon="bi-shield-check",
            severity="secondary",
        ),
    ),
    # ---- 403 (control plane) ------------------------------------------
    (STATE_ERROR_403_CONTROL_PLANE, PERSONA_ANY): (
        SmartLink(
            label="Request operator access",
            mailto="security@runmycampus.com?subject=Operator+access+request",
            icon="bi-shield-check",
            severity="primary",
            helper_text="Ask a platform operator to grant the missing permission.",
        ),
        SmartLink(
            label="Back to Manager",
            url_name="super:dashboard",
            icon="bi-house",
            severity="secondary",
        ),
    ),
    # ---- 500 ----------------------------------------------------------
    (STATE_ERROR_500, PERSONA_ANY): (
        SmartLink(
            label="Retry this page",
            href=".",
            icon="bi-arrow-clockwise",
            severity="primary",
        ),
        SmartLink(
            label="Report this error",
            mailto="support@runmycampus.com?subject=Server+error+(500)",
            icon="bi-bug",
            severity="secondary",
            helper_text="Include what you were doing — we'll chase it down.",
        ),
        SmartLink(
            label="Go to dashboard",
            url_name="accounts:redirect",
            icon="bi-house",
            severity="secondary",
        ),
    ),
    # ---- 503 ----------------------------------------------------------
    (STATE_ERROR_503, PERSONA_ANY): (
        SmartLink(
            label="Try again",
            href=".",
            icon="bi-arrow-clockwise",
            severity="primary",
            helper_text="Maintenance windows are usually brief.",
        ),
        SmartLink(
            label="System status",
            url_name="public_status",
            icon="bi-activity",
            severity="secondary",
        ),
        SmartLink(
            label="Go to dashboard",
            url_name="accounts:redirect",
            icon="bi-house",
            severity="secondary",
        ),
    ),
    # ---- Offline (standalone page) ------------------------------------
    (STATE_OFFLINE, PERSONA_ANY): (
        SmartLink(
            label="Retry connection",
            href=".",
            icon="bi-arrow-clockwise",
            severity="primary",
        ),
        SmartLink(
            label="Go to dashboard",
            url_name="accounts:redirect",
            icon="bi-house",
            severity="secondary",
            helper_text="Cached pages may still open while you reconnect.",
        ),
    ),
    # ---- Records hold active (Wave S-D) -------------------------------
    (STATE_RECORDS_HOLD_ACTIVE, PERSONA_PARENT): (
        SmartLink(
            label="Resolve outstanding balance",
            url_name="portal:parent_finance",
            icon="bi-credit-card",
            severity="primary",
            helper_text="Most transcript holds clear automatically once the balance is paid.",
        ),
        SmartLink(
            label="Contact the registrar",
            mailto="?subject=Transcript+hold+question",
            icon="bi-envelope",
            severity="secondary",
        ),
    ),
    # ---- Invoice overdue ----------------------------------------------
    (STATE_INVOICE_OVERDUE, PERSONA_PARENT): (
        SmartLink(
            label="Pay family balance",
            url_name="portal:parent_finance_pay_all",
            icon="bi-credit-card",
            severity="primary",
            helper_text="One checkout for every linked learner.",
        ),
        SmartLink(
            label="View invoices",
            url_name="portal:parent_finance",
            icon="bi-receipt",
            severity="secondary",
        ),
        SmartLink(
            label="Set up a payment plan",
            mailto="?subject=Payment+plan+request",
            icon="bi-calendar-check",
            severity="secondary",
        ),
    ),
    # ---- Admission pending review (tenant admin / staff) --------------
    (STATE_ADMISSION_PENDING, PERSONA_TENANT_ADMIN): (
        SmartLink(
            label="Open admissions queue",
            url_name="accounts:backend_applicant_list",
            icon="bi-inbox",
            severity="primary",
            helper_text="Review and approve pending applications.",
        ),
    ),
    # ---- Safeguarding concern open (DSL) ------------------------------
    (STATE_DSL_CONCERN_OPEN, PERSONA_TENANT_ADMIN): (
        SmartLink(
            label="Open safeguarding concern",
            url_name="accounts:safeguarding_inbox",
            icon="bi-shield-exclamation",
            severity="danger",
            helper_text="DSL action required within KCSIE 2026 SLA.",
        ),
    ),
}


# --- Public API -----------------------------------------------------------


def get_smart_links(state: str, persona: str = PERSONA_ANY) -> list[SmartLink]:
    """Return the ordered list of smart links for a (state, persona) pair.

    Falls back to ``persona=any`` when no persona-specific entry is set.
    Returns ``[]`` when nothing is registered (template renders nothing
    extra — no exception, this is a UX enhancement, not a load-bearing API).
    """
    if persona not in ALL_PERSONAS:
        # Unknown persona — fall through to ANY rather than 500-ing.
        persona = PERSONA_ANY
    entry = _REGISTRY.get((state, persona))
    if entry is None and persona != PERSONA_ANY:
        entry = _REGISTRY.get((state, PERSONA_ANY))
    return list(entry) if entry else []


def list_registered_states() -> list[str]:
    """Diagnostic helper — used by tests to assert the registry is non-empty."""
    return sorted({state for (state, _persona) in _REGISTRY.keys()})


def list_registered_pairs() -> list[tuple[str, str]]:
    """Diagnostic helper — every (state, persona) pair currently registered."""
    return sorted(_REGISTRY.keys())
