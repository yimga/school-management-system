# Render / Custom Domain Parity Certification Report

- Generated: 2026-05-07T22:14:13.102Z
- Expected repo SHA: `0b4ee86e7e7c24dfb1fa8ce3014702656098ea92`
- Verdict: RENDER PARITY PARTIAL

## Deployed SHA
- Not verified. `/-/version/` did not return JSON containing the expected commit SHA.
- Direct Render and `runmycampus.com` version endpoints returned marketing HTML.

## Direct Render Public Smoke
- Public routes: 6/6 returned 200.
- Routes: `/`, `/product-tour/`, `/pricing/`, `/trust/`, `/resources/`, `/demo/`.
- No major console/page errors or bad responses were captured in the browser smoke.

## Custom Domain Public Smoke
- Browser smoke for `https://runmycampus.com` public routes: 6/6 returned 200.
- Custom-domain SHA/version metadata remains unavailable, so custom-domain parity is not certified.

## Manager / Platform
- Unauthenticated manager routes safely rendered login pages/redirects for 15/15 checked routes.
- Authenticated platform operator QA was not certified because live credentials were unavailable.

## Tenant
- Tenant live QA was not certified.
- `xp-tenant.runmycampus.com` did not resolve.
- `gilead-school.runmycampus.com/school/settings/` returned a 500 service-interrupted page without live tenant authentication.

## Render Shell
- Not certified. No Render shell/dashboard credentials or CLI context were available.

## Remaining Blockers
- Deployed SHA not verified from JSON version endpoint.
- Authenticated manager/platform live QA pending.
- Authenticated tenant live QA pending.
- Render shell command parity pending.

## Final Verdict

RENDER PARITY PARTIAL
