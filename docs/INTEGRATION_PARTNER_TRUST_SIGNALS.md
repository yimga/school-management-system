# Integration patterns, certification, scopes, and audit (partner trust)

**Authority:** RUNMYCAMPUS §0.3 pillar 2 (Ecosystem) + pillar 4 (Integration / trust / API).  
**Audience:** Marketplace publishers, district IT, LMS admins, security reviewers.

## 1. Trust signals we expose

| Signal | Where | What partners see |
|--------|--------|-------------------|
| **OneRoster readiness** | `GET /api/interop/oneroster/`, tenant hub | Manifest, academicSessions, Bearer pattern, IP allowlist, scopes, export profile. |
| **LTI 1.3** | Hub + `/api/interop/lti13/` | Issuer, JWKS, OIDC launch template. |
| **SCIM** | Readiness + `public_endpoint_audit.md` | Inbound provisioning; optional timestamp replay. |
| **SSO** | SAML metadata URL, OIDC discovery via integration config | Standard federation. |
| **SSO health** | Backend → District & LMS interop → **SSO / IdP login health** | Last success, last failure, error summary (no PII). |
| **Webhooks** | Hub advanced settings | HMAC signature (`X-RunMyCampus-Signature`); secret rotation. |
| **Audit** | OneRoster requests logged (no PII); SAML ACS / OIDC structured logs | Compliance narrative. |

## 2. Certification checklist

Use **[docs/setup_studio/WEDGE_INTEROP_CHECKLIST.md](../setup_studio/WEDGE_INTEROP_CHECKLIST.md)** with the tenant hub **Partner certification** flow.

## 3. Scopes and least privilege

- OneRoster: `oneroster_scopes` on district integration — `*` or enumerated roster.* scopes.  
- Marketplace apps: **AppScope** / installation grants (see marketplace governance docs).

## 4. Audit and export

- Security review: `docs/SECURITY_REVIEW_LOG.md`.  
- Public surface: `docs/public_endpoint_audit.md`.  
- District printable packet: hub **District packet (print)**.

## 5. Clever / ClassLink native APIs

Proprietary vendor APIs require **partnership**; equivalent motion today: **Bearer + OneRoster 1.1** + SSO spine — see `docs/interop/WORLD_CLASS_TRIPLE_WEDGE.md` §44.
