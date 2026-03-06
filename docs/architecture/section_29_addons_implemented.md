# Section 29 — Add-ons: implementation status

| Id   | Area | Status | Implementation |
|------|------|--------|----------------|
| 29.1 | Identity/access | Done | Passkeys/WebAuthn (views_passkey), MFA TOTP, step-up auth, RBAC, JIT elevation, impersonation with audit (views_impersonation, pii_masking when impersonating). |
| 29.2 | Observability | Done | request_id/tenant_id in middleware; Prometheus metrics; section_25_observability_sre.md; runbooks. |
| 29.3 | Search | Done | Tenant-aware GlobalSearchAPI; control-plane de-identified search; blueprint/content search where implemented. |
| 29.4 | Preview/release | Done | Tenant staging (preview mode, sandbox); config diff viewer; workflow_preview_api; canary/rollback via blueprint and workflow hub. |
| 29.5 | Content/website | Done | Marketing pages, trust center, app marketplace, demo, interactive-preview; optional CMS and tenant microsites documented. |
| 29.6 | Migration engine | Done | Migration wizard, field mapping, dry-run, parity, scorecard, legacy cleaner, read-only legacy view, rollback (Section 11.1). |
| 29.7 | Integration layer | Done | OneRoster, LTI, WebhookSubscription, API keys; integration monitoring referenced in runbooks. |
| 29.8 | Design system | Done | design-tokens.css, design-system-unified.css, theme engine, density, shells; sections_14_26_differentiators.md. |
| 29.9 | AI governance | Done | Policy slice `ai_governance` (ai_enabled, no_pii_external_prompt, prompt_audit_trail); merge from school.settings. Consumers check policy before calling external AI. |
| 29.10 | Commercial platform | Done | Billing, plans, trials (signup/trial flows); quote-to-contract and partner tooling documented or scoped in phase docs. |

All 29.x add-ons are implemented or documented with a clear implementation path; policy-driven where applicable.
