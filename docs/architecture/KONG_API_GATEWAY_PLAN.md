# Kong (or equivalent) API gateway — rollout plan

**Goal:** Terminate TLS, rate limit, and authenticate external `/api/v1/*` traffic before it hits Django.

1. Deploy Kong (or AWS API Gateway + Lambda authorizer, or Cloudflare Workers) in front of app servers.
2. Routes: `/api/v1/*` → upstream Django; `/healthz` bypass.
3. Plugins: rate-limiting (per API key), request-size-limit, correlation-id header injection.
4. Consumer per tenant or per integration partner; rotate keys via trust center.
5. Django remains source of truth for auth; gateway adds defense in depth.

**Status:** Plan only until infra team provisions gateway. Document in DEPLOY_CHECKLIST when live.
