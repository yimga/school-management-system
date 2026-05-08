# Identity Provider (SAML / OIDC / SCIM) Connection Guide

The repo already supports SAML 2.0, OIDC, and SCIM 2.0. The work that remains for any enterprise tenant is **customer-side IdP configuration** — exchanging metadata and confirming the user provisioning flow.

Cross-reference: `apps/accounts/`, `apps/interop/`, `docs/compliance/CONTROL_MATRIX.md`.

## What you need from the customer

- Identity Provider type (Okta, Azure AD / Entra, Google Workspace, OneLogin, JumpCloud, Auth0, AD FS, Keycloak)
- Tenant / directory ID
- Authorization to create an enterprise app on their side

## OIDC (recommended for new deployments)

1. **In the customer IdP**, register a new OIDC application:
   - Redirect URI: `https://<tenant-host>/accounts/oidc/callback/`
   - Post-logout redirect: `https://<tenant-host>/accounts/logout/`
   - Required scopes: `openid email profile`
   - Optional: `groups` (for role mapping)
2. **Capture from the IdP**:
   - Issuer URL
   - Client ID
   - Client Secret
3. **In RunMyCampus** (Django admin → Integrations Marketplace → Integration):
   - `provider=identity`, `slug=oidc`, `enabled=True`
   - `config = {"issuer": "...", "client_id": "...", "scopes": ["openid","email","profile"]}`
   - Secret stored in deployment env var `OIDC_CLIENT_SECRET_<TENANT_SLUG>`
4. **Verify**: navigate to `https://<tenant-host>/accounts/login/` → click *Sign in with SSO* → expect successful login + audit-log entry.

## SAML 2.0

1. **In the customer IdP**, register a new SAML application:
   - Entity ID / Audience: `https://<tenant-host>/accounts/saml/metadata/`
   - ACS URL: `https://<tenant-host>/accounts/saml/acs/`
   - Single Logout URL: `https://<tenant-host>/accounts/saml/sls/`
   - NameID format: `emailAddress`
2. **Download the IdP metadata XML** (or note the metadata URL).
3. **In RunMyCampus**:
   - `provider=identity`, `slug=saml`, `enabled=True`
   - `config = {"idp_metadata_url": "..."}` OR upload the XML to `media/saml_metadata/<tenant-slug>.xml` and reference its path.
   - Signing cert stored in deployment env (`SAML_SP_PRIVATE_KEY`, `SAML_SP_CERT`).
4. **Verify**: same login flow as OIDC.

## SCIM 2.0 (auto-provisioning)

For directory sync (create/update/deactivate users automatically when they're added/removed from a directory group):

1. **In RunMyCampus**, create a SCIM bearer token:
   - Django admin → Accounts → SCIM Tokens → Add
   - Scope: `users:read users:write groups:read`
2. **In the customer IdP**, configure SCIM provisioning:
   - SCIM endpoint: `https://<tenant-host>/scim/v2/`
   - Bearer token: the value from step 1 (show once)
   - Map directory groups → RunMyCampus roles (parent / teacher / staff / admin)
3. **Verify**:
   ```bash
   curl -H "Authorization: Bearer <token>" https://<tenant-host>/scim/v2/Users?count=1
   ```
   Expected: HTTP 200 with a SCIM resource list.

## What this guide does NOT cover

- IdP licensing (customer pays their IdP vendor).
- LTI 1.3 — see `apps/interop/lti.py` and `docs/integrations/...` (separate runbook when needed).
