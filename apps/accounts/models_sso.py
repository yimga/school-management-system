"""v4.00.50 — SSO-provisioned User → School tenant binding.

When a user first lands via OIDC or SAML SSO, we know the verified
identity but not (yet) which RunMyCampus tenant the user belongs to.
The bind is recorded here at provisioning time so:

  * subsequent SSO logins pick up the same tenant automatically
  * operator tools can audit "which IdP minted this account, for which
    tenant, when"
  * future role assignment + StudentProfile/TeacherProfile/etc. flow
    keys off this row when the tenant is otherwise ambiguous

Multi-binding (2026-07-02, 9.8 SSO wave): the original 1:1 ``OneToOneField``
contradicted ``SchoolMembership``'s first-class multi-school support — a
user could hold N memberships but only ever 1 binding. A user may now hold
one binding per school (unique ``(user, school)``), with exactly one row
marked ``is_primary`` (partial unique constraint) so login/tenant selection
stays deterministic. The ``source`` field tracks oidc vs. saml so the audit
trail survives.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class UserTenantBinding(models.Model):
    class Source(models.TextChoices):
        OIDC = "oidc", "OIDC"
        SAML = "saml", "SAML"
        MANUAL = "manual", "Manual"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tenant_bindings",
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
    is_primary = models.BooleanField(
        default=True,
        help_text=(
            "When a user is bound to multiple schools, which binding wins "
            "for automatic tenant selection at login. Exactly one per user "
            "(partial unique constraint)."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "accounts"
        verbose_name = "User tenant binding"
        verbose_name_plural = "User tenant bindings"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "school"],
                name="uniq_tenant_binding_user_school",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_primary=True),
                name="uniq_primary_tenant_binding_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "source"]),
            models.Index(fields=["provider", "subject"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} → {self.school_id} ({self.source})"
