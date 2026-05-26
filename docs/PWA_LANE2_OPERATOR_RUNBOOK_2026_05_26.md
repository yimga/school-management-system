# PWA Lane 2 Cross-Browser Certification — Operator Runbook

This runbook is the missing link between the in-tree Playwright spec at
[tests/e2e/pwa-offline.spec.js](tests/e2e/pwa-offline.spec.js) and the
external "browser-recorded PWA install + offline + tenant cache isolation"
proof that lives on the audit's external-blocker list.

The spec is the WHAT. This runbook is the HOW — what an operator must do to
turn the spec into actual evidence the audit can verify.

## What "Lane 2" means

| Lane | Scope | Owner |
| --- | --- | --- |
| Lane 1 | In-repo headless Playwright run against `http://localhost:8000` | CI / engineering |
| **Lane 2** | **Headed cross-browser run against a staging tenant with a real subdomain, a real TLS cert, and a real device profile** | **Operator** |

Lane 1 proves the spec is syntactically and semantically correct.
Lane 2 proves the PWA actually installs, the cache actually isolates, and
the offline shell actually renders on iOS Safari and Android Chrome.

## Preconditions

1. **Staging tenant provisioned** at a real subdomain (e.g. `staging-cert.runmycampus.com`).
2. **TLS certificate** that browsers trust without an override (Let's Encrypt is fine; self-signed will FAIL the install criteria).
3. **Render or Fly deploy of `sms-v3.91.X-*`** running with `DEBUG=False` so the service worker scope behaves as in production.
4. **Manifest icons published at 192px and 512px** — the spec's `platform manifest loads` check enforces this.
5. **A second tenant** at a separate subdomain (e.g. `staging-other.runmycampus.com`) for the cross-tenant isolation check.
6. **Two physical or virtual devices**: one iOS (Safari 17+), one Android (Chrome 120+). Emulators are acceptable for the install criteria but NOT for the install prompt UX.
7. **`npx playwright install --with-deps`** ran on the operator workstation that will execute the run.

## Execution

### Step 1 — Lane 1 sanity sweep (5 min)

```bash
npx playwright test tests/e2e/pwa-offline.spec.js
```

All 10 tests must pass against `http://localhost:8000`. If any fail, fix
locally before touching Lane 2.

### Step 2 — Lane 2 cross-browser run (30 min)

```bash
RMC_PLAYWRIGHT_HOST=https://staging-cert.runmycampus.com \
  npx playwright test tests/e2e/pwa-offline.spec.js \
  --project=chromium --project=webkit
```

Save the HTML report:

```bash
npx playwright show-report > /dev/null &
cp -r playwright-report \
  var/evidence/lane2/pwa-cert-$(date -u +%Y-%m-%dT%H-%M-%SZ)/
```

### Step 3 — Headed install proof (15 min)

Open `https://staging-cert.runmycampus.com` on the iOS device.

- Safari → Share → "Add to Home Screen" → confirm the manifest icon and name match the registry.
- Open the home-screen icon. Confirm a top-bar-less standalone window.
- Toggle airplane mode. Reload. Confirm the offline shell appears (NOT the browser's neterror page).

Repeat on Android Chrome via the "Install app" omnibox prompt.

Screenshot each step with the OS-native screenshot tool and save under
`var/evidence/lane2/pwa-cert-<date>/install/<device>/`.

### Step 4 — Tenant cache isolation proof (10 min)

1. Log in to `staging-cert.runmycampus.com` as `tenant-A admin`.
2. Visit `/portal/`. Wait for SW to register.
3. In devtools → Application → Cache Storage, confirm cache keys are
   `sms-static-sms-vX.Y.Z-...` and `sms-dynamic-sms-vX.Y.Z-...`. No keys
   should mention tenant slugs in plaintext.
4. Open a second window to `staging-other.runmycampus.com`.
5. Confirm a SEPARATE set of cache storage exists, NOT shared with `staging-cert`.
6. Screenshot both Application panels.

### Step 5 — Logout purge proof (5 min)

1. While logged in at `staging-cert.runmycampus.com`, populate the cache by
   navigating to 3-4 portal routes.
2. Click logout.
3. Refresh the cache storage panel — cache count must equal the post-logout
   baseline (typically 0 or just the static shell).
4. Screenshot the before/after.

### Step 6 — Sensitive-path no-cache proof (5 min)

1. Visit `/admin/`, `/super/`, `/api/v1/health/` while logged in.
2. Open cache storage. NONE of these paths may appear as cache entries.
3. Screenshot the cache key list.

## What evidence to keep

Place under `var/evidence/lane2/pwa-cert-<YYYY-MM-DD>/`:

```text
playwright-report/                   ← from Step 2
install/ios/safari-install-prompt.png
install/ios/standalone-mode.png
install/ios/offline-fallback.png
install/android/chrome-install-prompt.png
install/android/standalone-mode.png
install/android/offline-fallback.png
tenant-isolation/tenant-a-cache.png
tenant-isolation/tenant-b-cache.png
logout-purge/before.png
logout-purge/after.png
sensitive-paths/cache-keys-after-admin-visit.png
manifest.json                        ← curl of the served manifest
service-worker.js                    ← curl of the served SW
```

## What to file in the SOT after the run

Once evidence is collected and reviewed:

1. Update `docs/generated/pwa_runtime_proof_hardening.json` — set
   `browser_backed: true` and add `evidence_bundle_path` pointing at the
   `var/evidence/lane2/pwa-cert-<date>/` directory.
2. Append a new `§11.4 forward queue` entry to the SOT documenting the
   Lane 2 cert with the evidence bundle path.
3. Flip the GEOS matrix `pwa_pct` honest score from 60 to 100 (or to the
   appropriate fraction if any device class failed).
4. Re-run `python scripts/verify_greatest_education_os_matrix.py --write`.

## What this runbook deliberately does NOT do

* Does not run Lane 2 itself — that's the operator's job on real devices.
* Does not modify the spec at run time — the spec is the contract.
* Does not promise live cross-tenant Playwright until Step 4 evidence
  lands in the bundle.

## Related artifacts

| Artifact | Role |
| --- | --- |
| [tests/e2e/pwa-offline.spec.js](tests/e2e/pwa-offline.spec.js) | The spec being certified |
| [docs/generated/pwa_runtime_proof_hardening.md](docs/generated/pwa_runtime_proof_hardening.md) | Pre-Lane-2 repo-scope proof |
| [docs/generated/pwa_first_mobile_launch_strategy.md](docs/generated/pwa_first_mobile_launch_strategy.md) | Why PWA before native |
| [docs/generated/pwa_native_wrapper_deferment_plan.md](docs/generated/pwa_native_wrapper_deferment_plan.md) | When native wrappers unlock |
