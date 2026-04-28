# Vendor risk policy (integrations)

## In-repo integrations

Examples: payment processors, OAuth/OIDC/SAML IdPs, messaging, OCR, storage. Each integration should have:

1. **Configuration** via `SiteSettings` / runtime defaults (see `scripts/audit_sitesettings_python_surface.py`).
2. **Secrets** outside Git — env / secret manager only.
3. **Failure modes** documented in deployment docs (degraded mode, kill switches where implemented).

## Review cadence

- Re-review vendor when upgrading major Django or SDK versions.
- Track third-party subprocess or network calls via `scripts/audit_subprocess_usage.py` and security surface audit.

No vendor SOC2 report storage is assumed in this repository.
