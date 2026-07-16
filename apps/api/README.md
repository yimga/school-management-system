# apps/api

> The platform's DRF surface: `/api/v1/` and `/api/v2/`, OneRoster, SCIM, SAML,
> OIDC, Ed-Fi, CEDS, the mobile API, offline sync, and the webhook catalog.

**Tenancy:** SHARED (public schema; it is listed in `SHARED_APPS` at `settings.py:3893`)
**Scale:** 4 models · 2 migrations · 76 test modules · ~43k LOC across 164 files

## What this app owns

This is the largest app in the repo and the platform's entire machine-facing
edge. 84 modules sit directly under `apps/api/` (164 `.py` files in total),
grouped into a few families: the versioned REST surface (`urls_v1`, `urls_v2`, `views_v1*`,
`views_v2`, `api_v1_manifest`), the interop standards (`oneroster*` — 12 modules
including its own OAuth2 token/introspection/discovery trio — plus `scim`,
`saml`, `oidc_rp`, `edfi_views`, `ceds_views`, `ministry_connectors`), the
mobile/offline rail (`mobile_api`, `offline_device_api`, `offline_encryption`,
`offline_replay_views`, `sync_bundle_api`, `sync_delta_api`, `sync_services`),
and the cross-cutting request machinery (`throttling`, `rate_limit`,
`permissions`, `deprecation`, `exception_handler`, `middleware_idempotency`,
`middleware_tenant_cors`, `middleware_edge_fallback`).

Two structural facts about this app surprise almost everyone who opens it:

**It has no `__init__.py`.** `apps/api/` is a PEP 420 implicit namespace package
and it *is* in `INSTALLED_APPS` (`config/settings.py:302`). Django is perfectly
happy with this — `apps.py` declares `ApiConfig` with an explicit
`label = "api"` — but tooling is not always so relaxed. The repo's own
`scan_import_reference_integrity.py` gate documents `apps/api/` by name as the
canonical namespace-package case it must treat as opaque, because it cannot
statically resolve symbols through one. Do not "fix" the missing `__init__.py`
without understanding what depends on the namespace-package behaviour.

**Its models do not live in `models.py` — there is no `models.py`.** The four
models below are declared in `mobile_api.py`, which is why an automated scan of
the app reports zero models while `migrations/0001_initial.py` cheerfully creates
four tables.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `MobileDevice` | `api_mobiledevice` | Registered mobile/web device per user: `device_id` UUID, platform (IOS/ANDROID/WEB), push token, app + OS version |
| `PushNotification` | `api_pushnotification` | Outbound push queued against a `MobileDevice`, with a PENDING → SENT/DELIVERED/FAILED status field |
| `OfflineSyncQueue` | `api_offlinesyncqueue` | Client-originated offline mutations awaiting replay: `entity_type` / `entity_id` / `action` / `data` plus a CONFLICT state and `retry_count` |
| `APIAccessLog` | `api_apiaccesslog` | Per-request API access record for monitoring and rate limiting |

All four are declared in `apps/api/mobile_api.py`, not a `models.py`. **None of
them carries a `school` foreign key** — they are keyed on `user` (and on
`MobileDevice` from there). They are not tenant-scoped rows; they live in the
public schema and are scoped by user identity alone.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| URLs | `urls`, `urls_v1`, `urls_v2` | Hundreds of route names (`ai-*`, `admin-dashboard`, `academic-dashboard`, `admissions-*`, …) |
| Module | `throttling` | The scoped throttle classes + the two global backstops (see below) |
| Module | `deprecation` | RFC 8594 `Deprecation:` / `Sunset:` / `Link: rel="successor-version"` headers; `DEPRECATED_ENDPOINTS` is the SOT and is mirrored into the v1 manifest |
| Module | `middleware_idempotency` | `Idempotency-Key` support on `/api/v1/` writes; 24h cache TTL; 2xx-only |
| Module | `middleware_tenant_cors` | Per-tenant CORS allowlist from the `cors_allowed_origins` school setting, union-merged with the static list |
| Module | `api_contract` | The stable `/api/v2/` JSON envelope (`CONTRACT_VERSION = "2026.04"`) |
| Module | `permissions` | DRF permission classes over the shared RBAC in `apps.accounts.permissions` |
| Celery tasks | none | This app declares no tasks |
| Management commands | none | This app declares no commands |

## Before you change this

- **DRF *replaces* `DEFAULT_THROTTLE_CLASSES` — it does not merge them.** This is
  the single most important thing to know before touching throttling here. The
  moment a view declares its own `throttle_classes`, the settings defaults are
  gone for that view, backstops included. That is by design (the scoped budgets
  in `throttling.py` are tighter than the backstops, so they must not be
  loosened) — but it means a view that declares a throttle owns its whole
  throttling story.
- **The backstops exist because the default block was default-*open*.**
  `DEFAULT_THROTTLE_CLASSES` (`config/settings.py` ~2963) once held only
  `MigrationCloudGlobalThrottle`, which is **path-scoped**: its `allow_request()`
  returns `True` for anything outside `/migration/api/v1/`. The settings block
  *looked* like a blanket throttle while every DRF view that forgot to declare
  `throttle_classes` was entirely unthrottled. `DefaultBackstopUserThrottle`
  (1200/min, authenticated) and `DefaultBackstopAnonThrottle` (120/min, anonymous)
  now close that gap. They are deliberately generous — high enough that no
  legitimate caller notices, low enough to blunt a runaway loop. Do not remove
  them, and do not mistake them for the real budget.
- **Throttle scopes are tenant-aware by cache key, not by queryset.** Keys are
  composed `<scope>:<tenant>:<ident>` where tenant is `request.school.pk` (or a
  shared `global` bucket pre-tenant), so one school's burst cannot exhaust
  another's. If you add a throttle, subclass `_ApiScopedThrottleBase` rather than
  DRF's `SimpleRateThrottle` directly, or you lose that isolation.
- **`anon_only` / `auth_only` prevent double-counting.** A public endpoint pairs a
  per-IP anon throttle with a per-user auth throttle; the flags are what keep a
  single request from being charged to both. Setting neither on a paired throttle
  silently halves the effective budget.
- **The scoped rates are owned in `throttling.py`, not in settings.** Each class
  sets `rate` directly and `get_rate()` is overridden so DRF never falls through
  to `DEFAULT_THROTTLE_RATES`. This is deliberate: operators do not override the
  public API's abuse budget through generic settings. A misconfigured subclass
  returns `None` (allow) rather than raising `ImproperlyConfigured` at request
  time — fail-open on *configuration*, never on traffic.
- **Every DRF view class here must carry `@extend_schema`.** `scan_drf_schema_coverage.py`
  is a zero-tolerance CI gate scoped to `apps/api/`. Intentional exclusions need
  `# drf-spectacular-allow: <reason>`.
- **Deprecating a route means adding it to `DEPRECATED_ENDPOINTS`, not just a
  changelog line.** That table is the producer for both the response headers and
  the manifest's `deprecations` block. The module docstring is explicit that the
  advertised 90-day policy had "no runtime teeth" before it existed — a client
  that gets no `Sunset` header discovers the break at 410-time.
- **Idempotency is opt-in and narrow.** `middleware_idempotency` only acts on
  `/api/v1/` writes that supply the header, and only caches JSON 2xx responses —
  errors deliberately fall through so a client can retry after a fix. Widening
  the scope would start deduplicating internal Django view writes.
- **`offline_encryption` keys are session-scoped and must never be logged.** The
  key is HMAC-derived from `SECRET_KEY` + user id + session key. Rotating
  `SECRET_KEY` invalidates every outstanding offline queue payload.
