"""Record which IdP minted a user for which tenant (``UserTenantBinding`` upsert).

The per-school OIDC/SAML JIT flows (``views_oidc``/``views_saml``) create the
User + SchoolMembership on first SSO login but historically never recorded a
``UserTenantBinding`` — so the operator binding-audit surface
(``/portal/super/sso/bindings/``) and "which IdP minted this account" trail
were empty for tenant-scoped SSO. ``bind_user_to_tenant`` closes that gap and is
safe to call on EVERY SSO login.
"""

from __future__ import annotations

import logging

from apps.accounts.models_sso import UserTenantBinding

logger = logging.getLogger(__name__)


def bind_user_to_tenant(
    *,
    user,
    school,
    source: str,
    provider: str = "",
    subject: str = "",
    issuer: str = "",
):
    """Idempotently upsert the ``UserTenantBinding`` for an SSO-provisioned login.

    Honors the model's partial-unique "exactly one ``is_primary`` per user"
    constraint: a new binding is marked primary only when the user has no other
    primary binding yet. Repeat logins refresh the audit fields (source / subject
    / issuer / provider) but never flip ``is_primary``. Never raises into the
    login path — a binding write failure is logged and swallowed so SSO login is
    unaffected.
    """
    try:
        # tenant-isolation-allow: sso-primary-binding-invariant-checks-across-all-of-this-users-tenants
        has_other_primary = (
            UserTenantBinding.objects.filter(user=user, is_primary=True)
            .exclude(school=school)
            .exists()
        )
        binding, created = UserTenantBinding.objects.get_or_create(
            user=user,
            school=school,
            defaults={
                "source": source,
                "provider": (provider or "")[:64],
                "subject": (subject or "")[:255],
                "issuer": (issuer or "")[:255],
                "is_primary": not has_other_primary,
            },
        )
        if not created:
            fields = []
            if source and binding.source != source:
                binding.source = source
                fields.append("source")
            if subject and binding.subject != subject[:255]:
                binding.subject = subject[:255]
                fields.append("subject")
            if issuer and binding.issuer != issuer[:255]:
                binding.issuer = issuer[:255]
                fields.append("issuer")
            if provider and binding.provider != provider[:64]:
                binding.provider = provider[:64]
                fields.append("provider")
            if fields:
                binding.save(update_fields=fields)
        return binding
    except Exception:  # noqa: BLE001 — a binding write must never break SSO login
        logger.warning(
            "sso_binding: failed to record UserTenantBinding for school=%s",
            getattr(school, "pk", None),
        )
        return None
