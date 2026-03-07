# Scanner traffic and hardening

## What the logs show

Your logs (e.g. 2026-03-02 15:34–16:05) show two kinds of traffic:

### 1. Automated scanner/probes (10.x.x.x and 185.177.72.60)

- **Paths probed:** `/.git/config`, `/.git/HEAD`, `/terraform/*`, `/terraform.tfstate`, `/main.yml`, `/wp-config.php*`, `/cloudformation.yml`, `/config.js`, `/env.js`, `/stripe.js`, `/sw.js`, `/update/index.php`, `/setup/`, `/_internal/api/setup.php`, etc.
- **Interpretation:** Common internet scanning for misconfigured apps (Terraform state, .git, WordPress, env files, payment scripts). Many requests returned **301** (e.g. `/.git/config`, `/terraform/terraform.tfstate`); others **404**.
- **Risk:** 301 on `/.git` can leak that something exists; ideally these paths should never be served or redirected. Your app does not serve these files; the 301 may come from the platform (e.g. Render) or a catch-all. Blocking these paths in Django with an early **404** avoids any redirect and reduces noise.

### 2. Legitimate traffic

- **Render/1.0** → `GET /health/` (200) every ~5s (platform health checks).
- **73.99.214.1, 103.4.250.x, 152.53.195.17** → real users (Chrome/Edge), `/`, `/school-not-found/`, `/pricing/`, `/api/weather/context/`, static assets.
- **195.221.56.3** → POST to `/update/index.php`, `/setup/` (404): likely a misconfigured client or scanner; now covered by the blocklist.

## What was implemented

1. **`config.middleware.BlockScannerPathsMiddleware`**  
   Runs early (after `SecurityMiddleware`). For request paths that match known scanner targets (e.g. `/.git`, `/.terraform`, `/terraform*`, `/wp-config*`, `/main.yml`, `/config.js`, `/env.js`, `/stripe.js`, `/update/`, `/setup/`, `/_internal/`, etc.), it returns **404** immediately. Normal paths are unchanged.

2. **Middleware registration**  
   - Default stack: `config.settings` → `MIDDLEWARE`.  
   - Tenant stack: same middleware added in the tenant `MIDDLEWARE` block in `config.settings`.

Result: scanner requests for those paths get a fast 404 from Django; no redirect, no further processing, and less log noise.

## Optional next steps

- **Platform (e.g. Render):** If 301 for `/.git` or similar is from the reverse proxy, consider a rule there to return 404/403 for `/.git`, `/.env`, `/terraform*`, etc.
- **Rate limiting:** For IPs that hammer many 404s (e.g. 185.177.72.60), consider per-IP rate limiting or blocklist at proxy/firewall level.
- **Logging:** You can log blocked paths (e.g. in the middleware) to a separate channel to monitor scanner patterns without cluttering main request logs.
