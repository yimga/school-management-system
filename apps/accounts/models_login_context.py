"""Known login fingerprints for suspicious-login alerting (audit residual).

The platform had no signal when an account was accessed from a new device or
network — a credential-stuffing success looked identical to a normal login.
:class:`KnownLoginContext` records a coarse, PRIVACY-PRESERVING fingerprint of
each (user, device/network) pair we have seen succeed. The ``user_logged_in``
receiver in :mod:`apps.accounts.signals` consults it: the first time a user
logs in from a fingerprint we have never recorded — and it is not their very
first login ever — we email the account owner a "new sign-in" alert.

PII contract
------------
We NEVER store the raw IP address or User-Agent string. Only:

  * ``ip_hash``  = sha256(ip)[:12]
  * ``ua_hash``  = sha256(user_agent)[:12]
  * ``context_hash`` = sha256(ip + "|" + user_agent)[:16]  (the dedupe key)

The hashes are one-way; they let us recognise a returning device without ever
holding the network identifiers.
"""
from __future__ import annotations

from django.db import models


class KnownLoginContext(models.Model):
    """A device/network fingerprint we have seen this user log in from."""

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="known_login_contexts",
    )
    context_hash = models.CharField(
        max_length=16,
        db_index=True,
        help_text="sha256(ip + '|' + user_agent)[:16] — the dedupe key.",
    )
    ip_hash = models.CharField(
        max_length=12,
        blank=True,
        default="",
        help_text="sha256(ip)[:12] — never the raw IP.",
    )
    ua_hash = models.CharField(
        max_length=12,
        blank=True,
        default="",
        help_text="sha256(user_agent)[:12] — never the raw UA string.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "accounts"
        db_table = "accounts_known_login_context"
        verbose_name = "Known login context"
        verbose_name_plural = "Known login contexts"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "context_hash"],
                name="accounts_known_login_ctx_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"KnownLoginContext[user={self.user_id} ctx={self.context_hash}]"


__all__ = ["KnownLoginContext"]
