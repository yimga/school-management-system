# Setup Studio — Wedge 44 interop checklist

Use with **Backend → District & LMS interoperability**.

1. [ ] Generate OneRoster Bearer token; store in district secret manager.
2. [ ] Call `GET .../manifest?school_slug=` with Bearer → 200.
3. [ ] Validate `users` or `students`+`teachers` counts vs SIS.
4. [ ] Configure optional **IP allowlist** and **scopes** for least privilege.
5. [ ] Register **roster webhook URL** + secret; verify `X-RunMyCampus-Signature` on POST.
6. [ ] Enable **synthetic demo roster** only for sandbox tenants (partner certification).
7. [ ] Complete **Partner certification** page items in the hub.
8. [ ] Export **District packet** (PDF/print) for RFP / security questionnaire.

LTI 1.3: use hub **LTI wizard** block (JWKS, launch URL template). SSO: SAML/OIDC in Integrations; check clock skew and cert expiry if login fails.

9. [ ] Review **SSO / IdP login health** on the hub after go-live (last OK vs last fail; fix IdP config if failures climb).
10. [ ] Read **[INTEGRATION_PARTNER_TRUST_SIGNALS.md](../INTEGRATION_PARTNER_TRUST_SIGNALS.md)** for RFP / security questionnaire alignment.
