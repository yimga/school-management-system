"""Wave U (v3.99.0 — 2026-05-27) — Empty-state card kernel.

When a list page has zero rows, never render the awkward blank gap.
Instead surface an active card that names the domain, offers a
setup-wizard CTA, and (optionally) a secondary "learn more" link.

This is a pure-Python registry mapping ``(domain, persona) → EmptyStateCard``;
the template tag in ``empty_state_tags.py`` resolves the wizard URL via the
existing wizard registry. Falls back gracefully when the wizard or url
isn't available in the current host context (silently renders the card
without the CTA — never crashes the page).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PERSONA_ANY = "any"
PERSONA_TENANT_ADMIN = "tenant_admin"
PERSONA_TEACHER = "teacher"
PERSONA_PARENT = "parent"
PERSONA_STUDENT = "student"
PERSONA_STAFF = "staff"
PERSONA_OPERATOR = "operator"

ALL_PERSONAS = (
    PERSONA_ANY, PERSONA_TENANT_ADMIN, PERSONA_TEACHER, PERSONA_PARENT,
    PERSONA_STUDENT, PERSONA_STAFF, PERSONA_OPERATOR,
)


@dataclass(frozen=True)
class EmptyStateCard:
    """A typed descriptor rendered when a list has zero rows."""

    headline: str
    body: str
    cta_label: str = ""
    cta_wizard_slug: str = ""
    cta_url_name: str = ""
    cta_kwargs: dict[str, Any] = field(default_factory=dict)
    icon: str = "bi-stars"
    severity: str = "info"  # info | success | warning
    helper_link_label: str = ""
    helper_link_url_name: str = ""

    def __post_init__(self) -> None:
        if not self.headline:
            raise ValueError("EmptyStateCard.headline is required")
        if self.severity not in {"info", "success", "warning"}:
            raise ValueError(f"invalid severity {self.severity!r}")
        # Either wizard_slug OR url_name OR neither — never both
        # (avoids ambiguity about which target the template tag should use).
        if self.cta_wizard_slug and self.cta_url_name:
            raise ValueError(
                "EmptyStateCard: set cta_wizard_slug OR cta_url_name, not both",
            )


# --- Registry -------------------------------------------------------------


_REGISTRY: dict[tuple[str, str], EmptyStateCard] = {
    ("students", PERSONA_TENANT_ADMIN): EmptyStateCard(
        headline="No students yet — let's import the roster.",
        body=(
            "Bulk-import via CSV in under 5 minutes. The wizard validates "
            "required columns and previews changes before applying."
        ),
        cta_label="Open the student import wizard",
        cta_wizard_slug="bulk_csv_student_import",
        icon="bi-mortarboard",
        severity="info",
        helper_link_label="Why CSV first?",
        helper_link_url_name="feedback:help_center",
    ),
    ("students", PERSONA_TEACHER): EmptyStateCard(
        headline="Your classroom roster is empty.",
        body="Ask an admin to import or assign students to this class.",
        icon="bi-people",
        severity="info",
    ),
    ("admissions", PERSONA_TENANT_ADMIN): EmptyStateCard(
        headline="No admissions applications yet.",
        body=(
            "Publish your admissions intake form and we'll list every "
            "application here as it lands."
        ),
        cta_label="Set up admissions",
        cta_wizard_slug="admissions_pipeline_setup",
        icon="bi-inbox",
        severity="info",
    ),
    ("invoices", PERSONA_TENANT_ADMIN): EmptyStateCard(
        headline="No invoices have been issued.",
        body="Configure your fee schedule and let the engine generate the term's invoices.",
        cta_label="Open fee setup",
        cta_wizard_slug="fee_schedule_designer",
        icon="bi-receipt",
        severity="info",
    ),
    ("invoices", PERSONA_PARENT): EmptyStateCard(
        headline="Nothing's due right now.",
        body="When a new invoice arrives, you'll see it here with a one-click pay action.",
        icon="bi-check2-circle",
        severity="success",
    ),
    ("messages", PERSONA_TEACHER): EmptyStateCard(
        headline="No messages today.",
        body="Send a class-wide update or a single-parent thread from the compose pane.",
        cta_label="Compose a message",
        cta_url_name="messaging:compose",
        icon="bi-chat-square-text",
        severity="info",
    ),
    ("messages", PERSONA_PARENT): EmptyStateCard(
        headline="No new messages.",
        body="Updates from teachers and the school will land here.",
        icon="bi-chat-square",
        severity="info",
    ),
    ("attendance", PERSONA_TEACHER): EmptyStateCard(
        headline="Take attendance for today's first class.",
        body="Whole-class shortcut, then individual exceptions. Saved in one tap.",
        cta_label="Open today's roll",
        cta_url_name="teacher:attendance_today",
        icon="bi-clipboard-check",
        severity="info",
    ),
    ("homework", PERSONA_STUDENT): EmptyStateCard(
        headline="No homework due. 🎉",
        body="When a new assignment lands, you'll see it here with a clear due date.",
        icon="bi-journal-check",
        severity="success",
    ),
    ("safeguarding_concerns", PERSONA_TENANT_ADMIN): EmptyStateCard(
        headline="No open safeguarding concerns.",
        body=(
            "When a staff member raises a concern, the DSL gets a 1-click "
            "deep-link here and in the inbox sidebar."
        ),
        icon="bi-shield-check",
        severity="success",
        helper_link_label="KCSIE 2026 reference",
        helper_link_url_name="feedback:help_center",
    ),
    ("records_holds", PERSONA_TENANT_ADMIN): EmptyStateCard(
        headline="No active records holds.",
        body="Hold registry is empty. Transcripts release immediately on request.",
        icon="bi-folder-check",
        severity="success",
    ),
    ("dsl_inbox", PERSONA_TENANT_ADMIN): EmptyStateCard(
        headline="Inbox clear.",
        body="No safeguarding referrals waiting on your action.",
        icon="bi-inbox",
        severity="success",
    ),
}


def get_empty_state(domain: str, persona: str = PERSONA_ANY) -> EmptyStateCard | None:
    """Return the registered card for a (domain, persona) pair — or None."""
    if persona not in ALL_PERSONAS:
        persona = PERSONA_ANY
    card = _REGISTRY.get((domain, persona))
    if card is None and persona != PERSONA_ANY:
        card = _REGISTRY.get((domain, PERSONA_ANY))
    return card


def list_registered_domains() -> list[str]:
    return sorted({domain for (domain, _persona) in _REGISTRY.keys()})


def list_registered_pairs() -> list[tuple[str, str]]:
    return sorted(_REGISTRY.keys())
