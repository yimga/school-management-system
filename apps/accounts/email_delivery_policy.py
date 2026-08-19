"""Which emails can actually receive mail.

Migration Cloud often provisions a parent with a name and phone but no mailbox.
Those accounts still need a non-blank ``User.email`` (the field is required), so
we mint a reserved ``@unclaimed.invalid`` address. Invite/reset mail must never
go there — RFC 2606 ``.invalid`` is not a deliverable zone, and treating it as
one would bounce the school's mail relay.
"""

from __future__ import annotations

import hashlib
import re

# RFC 2606 reserved TLD — guaranteed not to resolve. Also skip the billing
# checkout placeholder domain used when a payer only has a phone.
UNDELIVERABLE_EMAIL_DOMAINS = frozenset(
    {
        "unclaimed.invalid",
        "phone.runmycampus.com",
    }
)

SYNTHETIC_EMAIL_DOMAIN = "unclaimed.invalid"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_deliverable_email(email: str) -> bool:
    """True when ``email`` looks like a real mailbox we may send to."""
    value = (email or "").strip()
    if not value or not _EMAIL_RE.match(value):
        return False
    domain = value.rsplit("@", 1)[-1].lower()
    return domain not in UNDELIVERABLE_EMAIL_DOMAINS


def synthetic_unclaimed_email(seed: str) -> str:
    """Stable, undeliverable mailbox derived from identity (idempotent re-apply)."""
    digest = hashlib.sha256((seed or "parent").encode("utf-8")).hexdigest()[:16]
    return f"parent-{digest}@{SYNTHETIC_EMAIL_DOMAIN}"
