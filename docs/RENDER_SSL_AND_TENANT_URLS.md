# Fixing ERR_SSL_VERSION_OR_CIPHER_MISMATCH on Render Tenant URLs

If you see **"This site can't provide a secure connection"** for a URL like:

`gilead-school.school-management-system-2kzk.onrender.com`

the browser is failing the TLS handshake with that host. Render does **not** provide wildcard SSL for tenant subdomains (e.g. `*.school-management-system-2kzk.onrender.com`), so those URLs will always be unreliable or broken.

## Fix (recommended)

**Use your canonical domain for all tenant and manager URLs, not the Render host.**

1. **Set the base domain on Render**
   - In the Render dashboard for this service, add an environment variable:
   - **`MULTI_TENANT_BASE_DOMAIN`** = **`runmycampus.com`** (or your real production domain).
   - This makes the app build all tenant links as `https://slug.runmycampus.com` instead of `https://slug.school-management-system-2kzk.onrender.com`.

2. **Point your domain at Render**
   - In your DNS (e.g. Cloudflare, Namecheap), add a CNAME (or A record) so that:
     - `runmycampus.com` (and optionally `*.runmycampus.com`) resolve to your Render service.
   - In Render, add the custom domain `runmycampus.com` (and optionally `*.runmycampus.com`) to the service so Render issues SSL for it.

3. **Result**
   - Tenant portal links (e.g. from Find school, school-not-found, emails) will be `https://gilead-school.runmycampus.com` (or your domain). SSL works because it’s issued for your domain, not for `*.onrender.com`.

## Code change (already applied)

`domain_sync.get_base_domain()` now uses the same logic as `host_routing.get_canonical_base_domain()`: when `MULTI_TENANT_BASE_DOMAIN` is unset, it defaults to **`runmycampus.com`** instead of `RENDER_EXTERNAL_HOSTNAME`. So even without the env var, the app no longer builds tenant URLs on the Render host, avoiding the SSL error for new links.

For production you should still set **`MULTI_TENANT_BASE_DOMAIN=runmycampus.com`** (or your domain) on Render so behavior is explicit and correct for your branding.
