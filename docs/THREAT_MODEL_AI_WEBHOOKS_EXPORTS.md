# Threat model sketch: AI, webhooks, uploads, exports

**Purpose:** Lightweight, actionable threat notes for security reviews and control design. Not a formal STRIDE write-up; extend in your org’s template.

## AI (assist + tools)

| Threat | Mitigation direction |
|--------|---------------------|
| Prompt injection leading to tool abuse or data exfil | Versioned prompts/models; canary; no silent promote for tool/data-access changes; constrained tool allowlists; RAG on **canonical docs**, not unconstrained DB. |
| PII in model context | Redact/limit retrieval; eval harness for leakage (CI where feasible). |
| Operator vs tenant confusion | AI features respect same host/school boundaries as the rest of the app. |

## Webhooks

| Threat | Mitigation direction |
|--------|---------------------|
| Forged callbacks | Shared secret / signature verification; idempotency; replay windows. |
| SSRF via callback URLs | Allowlist destinations; block internal ranges in outbound fetches. |

## Uploads

| Threat | Mitigation direction |
|--------|---------------------|
| Malware / polyglots | MIME sniff limits; AV scanning where required; size quotas. |
| Path traversal / storage abuse | Randomized object keys; no user-controlled paths; per-tenant quotas. |

## Exports

| Threat | Mitigation direction |
|--------|---------------------|
| Bulk exfiltration by compromised account | Role checks; rate limits; audit logs; optional approval for large exports. |
| Cross-tenant export | Schema / `school_id` enforcement in queries; tests for tenant isolation on export paths. |

## Cross-cutting

- **Structured alerts** on impersonation start/end, role changes, export jobs, webhook verification failures.
- **CI:** dependency/CVE (e.g. `pip-audit` in `.github/workflows/smoke.yml`), plus targeted security tests for host/school boundaries.

See [PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md](PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md) for operator/tenant routing and impersonation.
