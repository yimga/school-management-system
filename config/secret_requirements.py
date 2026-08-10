"""Fail-closed enforcement for production-critical secrets.

On hosted deployments (Render / production / staging) some secrets MUST be provided
explicitly. Silently deriving or skipping them leaves production in an
insecure-but-running state:

  * ``DJANGO_CRYPTOGRAPHY_KEY`` — if unset, the at-rest encryption key is derived from
    ``SECRET_KEY``. Rotating ``SECRET_KEY`` then irreversibly destroys every encrypted
    column, with no signal at boot.
  * ``MIGRATION_CLOUD_AUDIT_SIGNING_KEY`` — if unset (with the default ``local-env-key``
    backend), Migration Cloud audit rows are written UNSIGNED, so the tamper-evidence
    chain is silently off.

This helper turns that silent degrade into a boot-time ``ImproperlyConfigured`` so the
misconfiguration is impossible to miss. In non-hosted contexts (local dev, CI, the test
suite) it is a no-op passthrough, so the dev/test experience is unchanged.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured


def require_secret_on_hosted(
    name: str,
    value: str | None,
    *,
    is_hosted: bool,
    guidance: str = "",
) -> str | None:
    """Return ``value`` unchanged, or raise ``ImproperlyConfigured`` when a hosted
    deployment is missing it.

    ``is_hosted`` must be the settings-level hosted-deploy signal (``_IS_CLOUD_DEPLOYED``):
    True on Render / production / staging, False in local dev, CI and the test suite — so
    tests and local runs never trip the guard, and only real hosted deploys fail closed.
    """
    if is_hosted and not value:
        message = (
            f"{name} must be set on hosted deployments (Render / production / staging); "
            "refusing to boot in an insecure-but-running state."
        )
        if guidance:
            message = f"{message} {guidance}"
        raise ImproperlyConfigured(message)
    return value
