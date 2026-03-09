# Marketing site performance

**Scope:** Code-level and deploy/infra guidance so the public marketing surface stays fast. CDN, WebP/AVIF, and static rendering are deploy/infra; this doc covers what’s in app code and what to do at the edge.

## In-app (done or optional)

- **Lazy loading:** Hero video uses `preload="metadata"`; images below the fold use `loading="lazy"` and `decoding="async"` where applicable.
- **Hero image:** A single `hero_dashboard_image_url` (or placeholder) is used. For multiple resolutions, add `hero_dashboard_image_srcset` and `hero_dashboard_image_sizes` to context and in the template use `<img src="..." srcset="{{ hero_dashboard_image_srcset }}" sizes="{{ hero_dashboard_image_sizes }}">` so the browser can pick the right asset.
- **Critical CSS:** Marketing landing uses `marketing-home.css` with design tokens; above-the-fold styles are in the same file. For further gains, consider inlining a small critical subset and deferring the rest (build-step or CMS).
- **No render-blocking scripts:** Analytics script is loaded with `async` when `marketing_analytics_script_url` is set.

## Deploy / infra (operational)

- **CDN:** Serve static assets and, if possible, public marketing pages from a CDN. Point `STATIC_URL` (and static domain) to the CDN origin so all `{% static %}` assets are cached at the edge.
- **WebP/AVIF:** Prefer generating and serving WebP/AVIF for photos (hero, module screenshots, product viz) at build or upload time. Use `<picture>` with `source type="image/webp"` and fallback `<img>`; or serve WebP/AVIF from the same URL via content negotiation at the CDN/proxy.
- **Static rendering / cache:** For fully static marketing pages, consider exporting to HTML at build time or caching full-page responses at the reverse proxy (e.g. cache key by path + locale). Dynamic bits (e.g. A/B variant) can be injected client-side or via edge logic if needed.
- **Preconnect:** When using a third-party analytics script, `marketing_analytics_preconnect_origin` is output in `extrahead` so the browser can preconnect early.

## Checklist

- [x] Lazy loading and async decode on non-hero images.
- [x] Hero video `preload="metadata"`.
- [ ] Optional: hero `srcset`/`sizes` when multiple resolutions exist.
- [ ] CDN and WebP/AVIF at edge (operational).
- [ ] Full-page or route-level cache for marketing (operational).
