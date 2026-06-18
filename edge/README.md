# Edge deployment (optional)

## Canonical path (recommended — OSS)

Tenant custom domains and platform TLS use:

1. **DNS TXT verification** — `apps/schools/dns_verification.py` + dnspython
2. **Reverse proxy** — **Caddy** or **nginx**
3. **Certificates** — **Let's Encrypt** (ACME HTTP-01 or DNS-01)

After verification, `sync_verified_schooldomain` provisions the tenant hostname on the origin. No paid CDN or edge vendor is required.

See also: `apps/siteconfig/services_custom_domain.py`.

## Optional: Cloudflare Workers (`edge/`)

The `edge/` folder contains an **optional** Cloudflare Worker for SWR caching of runtime payloads and LiteLLM passthrough. It is **not** required for:

- Custom domain onboarding
- Tenant wizard DNS steps
- Production TLS for school subdomains

Deploy only if your ops team already uses Cloudflare and wants edge caching:

```bash
cd edge && npx wrangler deploy
```

**Honest scope:** Worker code is ready; binding routes/KV/secrets is operator-side. The platform functions fully without it when Caddy + Let's Encrypt terminate TLS at the origin.
