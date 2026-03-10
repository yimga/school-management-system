# AllowAny and public API audit

**Goal:** Tag every public API view; confirm no cross-tenant or sensitive leakage; rate limiting and minimal response surface for AllowAny endpoints.

## Tagging

- **Public marketing / lead capture** — Unauthenticated, for landing pages, signup, lead forms.
- **Machine integration** — Webhooks, sync, external systems (should use signature/token).
- **Authenticated user** — Requires login; no AllowAny.
- **Staff/admin only** — IsAdminUser or custom staff permission.
- **Internal only** — Not exposed to internet or only via VPN/internal network.

## Inventory

| App | View / endpoint | permission_classes | Tag | Notes |
|-----|-----------------|---------------------|-----|-------|
| apps/schools/api_views.py | SchoolConfigAPI | AllowAny | Public SPA/config | GET /api/config — returns school branding/features by request host. No auth; used by SPA/mobile. Response: schoolName, logoUrl, primaryColor, accentColor, features, offlineEnabled. **Verdict:** Keep; add rate limit (e.g. per-IP). No sensitive data. |

## Other APIs checked

- apps/api/* — IsAuthenticated or IsAdminUser (no AllowAny in sampled files).
- apps/communication/api_views.py — IsAuthenticated / IsAdminUser.
- apps/finance/api_views.py — IsAuthenticated / IsAdminUser.
- apps/academics/api_views.py — IsAuthenticated.

## Next steps

1. Grep all views: `grep -rn "AllowAny\|permission_classes" --include="*.py" apps/`.
2. For each AllowAny: add row above; confirm rate limiting, no sensitive state, minimal response.
3. Replace AllowAny with token/signature auth where appropriate (e.g. webhooks).
