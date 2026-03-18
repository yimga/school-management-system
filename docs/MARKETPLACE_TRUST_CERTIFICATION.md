# Marketplace trust & certification (ecosystem §0.3)

## Checklist per listing

1. **Scopes** — App declares `AppScope`; installation grants visible before Install.
2. **Security** — No secrets in client assets; `lint_secret_exposure` in CI.
3. **Impact** — Package engine preview/rollback; dependency graph in UI.
4. **Review** — Publisher attestation + optional operator sign-off before production install.

## Developer sandbox

- Create **trial school** + **API Center** token with `sandbox_only` flag (recommended).
- OpenAPI: `/api/schema/` (staff) + `docs/apicenter_integration_governance.md`.

## Links

- `INTEGRATION_PARTNER_TRUST_SIGNALS.md`
- `MASTER_PLATFORM_CHECKLIST.md` marketplace section
