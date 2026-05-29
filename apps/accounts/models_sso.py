"""v4.00.50 — SSO-provisioned User → School tenant binding.

When a user first lands via OIDC or SAML SSO, we know the verified
identity but not (yet) which RunMyCampus tenant the user belongs to.
The bind is recorded here at provisioning time so:

  * subsequent SSO logins pick up the same tenant automatically
  * operator tools can audit "which IdP minted this account, for which
    tenant, when"
  * future role assignment + StudentProfile/TeacherProfile/etc. flow
    keys off this row when the tenant is otherwise ambiguous

One row per user (1:1). The ``source`` field tracks oidc vs. saml so
the audit trail survives.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class UserTenantBinding(models.Model):
    class Source(models.TextChoices):
        OIDC = "oidc", "OIDC"
        SAML = "saml", "SAML"
        MANUAL = "manual", "Manual"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tenant_binding",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="user_tenant_bindings",
    )
    source = models.CharField(max_length=16, choices=Source.choices)
    provider = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Slug of the upstream IdP (e.g. 'azure', 'google', 'okta').",
    )
    subject = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Verified subject claim (OIDC `sub`, SAML NameID).",
    )
    issuer = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "accounts"
        verbose_name = "User tenant binding"
        verbose_name_plural = "User tenant bindings"
        indexes = [
            models.Index(fields=["school", "source"]),
            models.Index(fields=["provider", "subject"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} → {self.school_id} ({self.source})"
