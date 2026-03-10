# Security Architecture Rules (Plan H1–H5)

**Due today, non-negotiable.** RunMyCampus security and governor limits.

## H1 — Security architecture rules

- Tenant data isolated by school_id / schema / RLS; no cross-tenant reads in tenant paths.
- Sensitive config (secrets, API keys) in env or secret store; never in versioned config.
- All privileged metadata mutations require audit (ConfigMutationAuditLog or equivalent).
- Authentication: support MFA; session and token lifecycle governed.

## H2 — Sensitive domain review

- Review: authentication, billing, PII, compliance, break-glass, impersonation, webhooks.
- No logging of secrets or full PII in plaintext; mask in audit logs where required.

## H3 — Security review gates

- PR checks: no new direct singleton in tenant code; no unsafe deps (pip-audit in CI).
- High-risk changes (auth, billing, RLS) require explicit review.

## H4 — Misuse detection in CI

- Lint: `lint_tenant_settings.py --check-get-solo-only` (fails on singleton in tenant paths).
- Optional: rate-limit and anomaly checks in runtime (future).

## H5 — Governor limits

- Enforceable limits: workflow runs, API throughput, migration concurrency, bulk export, AI invocations, dynamic field count, pack complexity.
- See `apps/platform_runtime/governor_limits.py` for defaults and `get_limit(key)`.
- Limits must not fail silently; clear operator messages, audit logs, admin visibility.
