# Aggressive deploy-cache audit prompt

Use this prompt in Agent mode when post-deploy changes are invisible, or proactively before a major release.

---

## Mission

You are a **zero-tolerance deploy-cache surgeon** for RunMyCampus. The owner cannot see commits from the last N days after deploy. Your job is to **audit every cache layer**, **remove harmful caching**, **fix invalidation**, and **prove** deploy freshness with named verifiers — not narrative.

## Phase 1 — Audit (read-only, exhaustive)

Trace the full path from `git push` → Render deploy → browser paint:

| Layer | Inspect |
| --- | --- |
| **Service worker** | `static/js/service-worker.js` — `CACHE_VERSION`, fetch strategy (network-first vs SWR vs cache-first), activate purge, scope |
| **SW registration** | `static/js/rmc-service-worker-registration.js` — `updateViaCache: 'none'`, `scope: '/'`, `controllerchange` reload |
| **SW URL** | Must be `/sw.js` with `Service-Worker-Allowed: /` — NOT `/static/js/` (scope trap) |
| **Static hashing** | `ForgivingCompressedManifestStaticFilesStorage` — `{% static %}` resolves hashed URLs in prod |
| **HTML caching** | `HtmlNoCacheMiddleware`, view `@never_cache` on hot shells |
| **Server cache** | Redis `effective_site_settings` TTL, fragment caches, `EdgeSWRFallbackMiddleware` |
| **Deploy parity** | `/-/version/` commit_sha vs `RENDER_GIT_COMMIT` on hosted Render |
| **Middleware allowlists** | `/sw.js`, `/sw-asset-manifest.json`, `/-/version/` reachable on tenant hosts |
| **Scanner trap** | `BlockScannerPathsMiddleware` must **NOT** include `/sw.js` (returns 404 before routing) |

Run:

```bash
python scripts/verify_deploy_cache_posture.py
python scripts/verify_service_worker_version.py --check-monotonic
python scripts/verify_manager_render_parity.py   # when RENDER_PARITY_BASE_URL set
curl -sI https://<tenant>/sw.js | grep -i cache-control
curl -s https://<tenant>/-/version/
```

## Phase 2 — Diagnose (rank by likelihood)

1. **SW stale-while-revalidate on CSS/JS** — serves week-old bundles until hard refresh  
2. **SW scope capped at `/static/js/`** — fetch handler never runs for pages or `/static/css/`  
3. **CACHE_VERSION not bumped** on waves that touch static/templates  
4. **HTML cached** by browser/CDN — user keeps old `{% static %}` hashes  
5. **Deploy never reached Render** — hosted `commit_sha` ≠ local HEAD  
6. **Dirty-form update toast** — user dismisses SW update prompt  
7. **Redis fragment cache** — rare for UI; check 60s TTL surfaces only  

## Phase 3 — Fix (smallest aggressive diff)

Required fixes when audit fails:

- Serve SW from `/sw.js` with `no-store` + `Service-Worker-Allowed: /`
- **Network-first** static with **timeout → cache fallback** (not SWR-first)
- **Purge all `sms-*` caches** on SW activate + `PURGE_ALL_CACHES` message
- Inject `rmc-deploy-sha` meta + `rmc-deploy-freshness.js` — auto-reload when `/-/version/` diverges
- `HtmlNoCacheMiddleware` on all `text/html` responses
- Bump `CACHE_VERSION` + baseline JSON in same commit
- Wire `/sw.js` into middleware allowlists

## Phase 4 — Remove harm

Delete or disable:

- Stale-while-revalidate as **primary** strategy for CSS/JS (keep only for optional API reads)
- Duplicate hardcoded `SW_MANIFEST_VERSION` env strings — read from SW source SOT
- `/static/js/service-worker.js` as registration URL in templates

Do **not** remove: offline IndexedDB write queue, tenant cache key prefixing, Redis session store.

## Phase 5 — Prove

```bash
python scripts/verify_deploy_cache_posture.py          # DEPLOY_CACHE_POSTURE_PASS
python scripts/verify_service_worker_version.py --check-monotonic
python manage.py check
```

Manual smoke after deploy:

1. Open tenant dashboard → note `meta[name=rmc-deploy-sha]`
2. Deploy new commit
3. Normal refresh (not hard) → page must reload or show update toast within 2s
4. DevTools → Application → Service Workers → `/sw.js` controlling `/`

## Operator emergency (production stuck now)

Tell affected users:

1. Hard refresh once: `Ctrl+Shift+R` / `Cmd+Shift+R`
2. Or: DevTools → Application → Service Workers → Unregister → reload
3. Verify deploy landed: `curl https://<host>/-/version/` vs Render dashboard commit

Platform-side after this patch ships: normal navigation self-heals.

---

**Definition of done:** `DEPLOY_CACHE_POSTURE_PASS` green, SW bumped, hosted `/-/version/` matches git HEAD, owner confirms visible UI change without manual cache clear.
