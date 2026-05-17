# Marketing nav revert playbook

This document is the operator runbook for reverting the verb-first marketing nav
(Run / Teach / Pay / Communicate / Grow) back to the legacy noun nav
(Platform / Solutions / …) if a regression is observed after Phase 3 ship.

The plan calls for a **per-verb revert path**: each verb can be reverted
independently if its bounce-rate doubles the prior-noun baseline or qualitative
signal flags confusion. Reverting all verbs at once is the nuclear option;
prefer per-verb scoping.

## Where the switch lives

- Feature flag: `marketing_verb_nav_enabled()` in
  `apps/schools/marketing_v3_surfaces.py`. Backed by Django settings + tenant
  override; defaults to enabled for `runmycampus.com` after 2026-05-16.
- Nav builder: `marketing_navbar_verb_primary()` (same module). Each verb is a
  dict in the returned list with a `bridge_label = "was: Platform"` chip so
  returning users get a visible bridge for the first 60 days.
- URL conf: `config/public_urls.py` declares both the new `/run/`, `/teach/`,
  `/pay/`, `/communicate/`, `/grow/` routes AND legacy `/platform/*` paths.
  Legacy paths use `RedirectView.as_view(permanent=True)` to 301 to the verb
  URL — those redirects are kept even when verbs are disabled, so SEO equity
  survives a revert.

## Full revert (all five verbs)

1. Set `MARKETING_VERB_NAV` env var to `0` (or remove the override) on the
   production app. The flag default falls back to the prior nav within one
   request cycle; no migration, no deploy required.
2. Optionally: temporarily un-permanent the `/platform/*` redirects by editing
   `RedirectView.as_view(permanent=True)` to `permanent=False` in
   `config/public_urls.py` so search-engine recrawl can re-establish the legacy
   URL as canonical. Skip this step if you intend to re-enable verbs within
   the week.
3. Sitemap: the dynamic sitemap (`marketing_sitemap_xml` in
   `apps/schools/marketing_views.py`) emits verb URLs as canonical. After a
   full revert, manually re-add the legacy `/platform/*` paths to
   `_sitemap_entries()` and remove the verb entries — search engines pick up
   the change on their next crawl.
4. Communicate the revert in `docs/CSS_RETIREMENT_DOCKET.md` with a dated note;
   bump the service worker `CACHE_VERSION` so clients refresh the new nav.

## Per-verb revert (preferred)

Per-verb revert only hides the verb from the top-level nav while leaving its
mega-menu links available through their canonical URLs. The legacy
`/platform/{module}/` redirect to the verb path remains in place.

1. In `apps/schools/marketing_v3_surfaces.py::marketing_navbar_verb_primary()`,
   wrap the offending verb entry in a `if VERB_<NAME>_ENABLED:` check, where
   the flag is read from settings (e.g. `MARKETING_VERB_PAY_ENABLED`,
   default True).
2. Set the corresponding env var to `0` in production.
3. Add a fallback link from the nav into the `More` dropdown so the page
   stays reachable from the chrome.
4. Watch analytics for 1 week; restore the verb when the issue is understood.

## Roll-back signals (from the plan)

- **Bounce-rate doubles** the prior noun-nav baseline for the verb
- **Confused-click pattern** (clicks bouncing between the verb and `More` /
  Pricing within 5 seconds) appearing in session replays
- **Direct external feedback** from buyers naming the nav as the friction

Any one of these signals justifies a per-verb revert. Two of them across the
same verb justifies a full revert of that verb without further deliberation.

## What stays put on revert

- `/platform/*` → `/{verb}/{module}/` 301 redirects (preserve SEO).
- Verb hub landing pages at `/run/`, `/teach/`, `/pay/`, `/communicate/`, `/grow/`
  remain reachable directly via URL — only their primary-nav exposure changes.
- Bell-clock platform brand mark and all Phase 4 product-surface usage are
  decoupled from the nav switch; they stay shipped.

## Restore procedure

To re-enable a reverted verb after the underlying issue is fixed:

1. Remove the `MARKETING_VERB_<NAME>_ENABLED=0` override.
2. Confirm via `MARKETING_VERB_NAV=1 python manage.py shell -c "from apps.schools.marketing_v3_surfaces import marketing_navbar_verb_primary; print([v['label'] for v in marketing_navbar_verb_primary()])"`.
3. Refresh the cached `marketing_navbar_primary` context if you have edge
   caching (purge the `/` cache key).
4. Note the restoration date in this file's changelog below so the next
   operator has a paper trail.

## Changelog

- 2026-05-16: Verb nav initially shipped. Bridge chips active on all five
  verbs for 60 days (through 2026-07-15).
