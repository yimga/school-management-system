# apps/social_media

> OAuth-connected social accounts, the proud-campus feed, an outbound cross-post
> outbox, moderation of user-submitted moments, and UTM campaign attribution.

**Tenancy:** SHARED (public schema; every row is scoped by an explicit `school` FK — and a NULL `school` deliberately means "platform", not "unscoped")
**Scale:** 4 models · 3 migrations · 2 test modules · ~2.0k LOC

## What this app owns

Social Media owns the whole two-way path between a campus and its social
accounts: pulling timelines in (`aggregator` → `feed_cache_json`), pushing posts
out (`publisher` → `SocialPostOutbox` → `providers`), letting staff approve
community-submitted photos before they are published (`SocialModerationItem`),
and attributing UTM-tagged inbound traffic to donations (`SocialCampaignAttribution`).

The organising decision is the **dual-scope model**: `school = NULL` is not a
bug, it is the platform (Tier 1) corporate feed; `school = <id>` is a tenant
(Tier 2) campus feed. `scope.resolve_feed_scope(request)` decides which one a
request is in — tenant host with `request.school` → tenant scope; manager or
marketing host → platform scope — and `scope.queryset_for_scope` is the only
correct way to turn that into a queryset, because "platform" means
`school__isnull=True` and not "everything". Partial unique constraints enforce
one active integration per provider on each side of that line.

The second thing to understand: **no live network egress is wired.**
`services/providers.py` is where third-party HTTP would go, but both
`fetch_feed_items` and `publish_post` are env-gated behind
`SOCIAL_LIVE_FETCH_ENABLED` / `SOCIAL_LIVE_PUBLISH_ENABLED`, which are off. With
the flags off, fetch returns an empty delta (the cache stays authoritative) and
publish returns a deterministic `dry-run-<provider>-<ts>` id. With the flags
*on*, the SDK call is still a logged no-op returning `queued-…`. The models,
scoping, throttle, moderation, and outbox around it are real; the wire is not.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `SocialMediaIntegration` | `social_media_socialmediaintegration` | An OAuth-connected account (X / Instagram / LinkedIn / Facebook). Fernet-encrypted token, refresh token and webhook secret at rest; carries `feed_cache_json`, per-tier `allowed_features`, a capped inline `audit_log`, and `needs_reauth`. NULL `school` = platform |
| `SocialPostOutbox` | `social_media_socialpostoutbox` | Outbound cross-post queue with tenant-scoped priority (`EMERGENCY = 0` sorts ahead of `STANDARD = 10`): pending → processing → posted / failed / throttled |
| `SocialModerationItem` | `social_media_socialmoderationitem` | A user-generated proud-campus moment awaiting staff approval (pending / approved / rejected). `school` is required here — moderation is always tenant-scoped |
| `SocialCampaignAttribution` | `social_media_socialcampaignattribution` | Maps UTM-tagged inbound traffic to a finance/donation event: provider, utm triple, `post_id`, `transaction_id`, `amount_cents` |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| URL | `portal:proud_campus_feed` | `/…/proud-campus/` — React island host; ADMIN / IT_ADMIN / LEADERSHIP / TEACHER only (`views.py`) |
| API | `/api/v1/social/feed/` | Scope-aware read (`SocialFeedAPI`) |
| API | `/api/v1/social/publish/` | Enqueue a cross-post |
| API | `/api/v1/social/moderation/`, `…/<uuid>/` | Moderation list + approve/reject action |
| API | `/api/v1/social/analytics/pulse/` | `PulseTimeseriesPoint`-shaped rows for the dashboard chart |
| API | `/api/v1/social/attribution/` | Record a UTM attribution |
| Celery task | `social_media.sync_tenant_feeds` | Aggregates one scope (`school_id=…` or `platform=True`) |
| Celery task | `social_media.process_outbox_batch` | Drains up to 25 pending rows, priority then FIFO |
| Module | `scope` | `resolve_feed_scope`, `queryset_for_scope`, `assert_integration_access`, `integration_scope_key` |
| Services | `aggregator`, `publisher`, `providers`, `throttle`, `emergency`, `analytics`, `asset_processor` | |

Neither Celery task is in `CELERY_BEAT_SCHEDULE` — both are called, not scheduled.

## Before you change this

- **A NULL `school` is a real scope, so `filter(school=None)` and "no filter" are
  not the same query.** Always go through `scope.queryset_for_scope`: it returns
  `school__isnull=True` for platform, a `school=` filter for a tenant, and
  `.none()` for the ambiguous case (no school, not a manager/marketing host). That
  `.none()` fallback is the fail-closed default — do not "fix" it into an
  unfiltered queryset.
- **`resolve_feed_scope` keys platform scope off the hostname** (`manager.` prefix
  or the bare marketing domains). Adding a host means editing that function, and
  getting it wrong silently promotes a tenant request to platform scope.
- **Tokens are encrypted at rest and must never be logged.** `encrypt_charfield`
  covers `encrypted_oauth_token`, `refresh_token`, and `webhook_secret`. The
  provider module's own log calls carry only the provider name and integration
  id, deliberately — keep it that way when you wire real HTTP.
- **The throttle and the emergency heap are per-process in-memory state.**
  `services/throttle.py` holds its leaky buckets in a module-level dict behind a
  `threading.Lock`, and `services/emergency.py` holds its priority heap the same
  way. Under multiple gunicorn workers each process gets its own buckets, so the
  effective rate is roughly `30/min × worker_count` per scope, and the heap is not
  shared with the Celery drainer at all. If you need a real cross-process limit,
  that is a Redis change, not a tuning change.
- **`process_outbox_batch` sweeps every tenant's pending rows in one query** —
  the `tenant-isolation-allow` comment above it marks that as reviewed, not
  overlooked. It orders by `priority, created_at`, which is what makes emergency
  rows jump the queue.
- **`route_emergency_broadcast` bypasses the outbox worker on purpose**: it
  enqueues, stamps priority 0, and drains the rows inline so the broadcast does
  not wait on a Celery round-trip. That means it does provider I/O in the request
  path.
- **Do not describe publishing as live.** Until a real client is wired into
  `providers.publish_post`, an "posted" row means the dry-run path returned an id.
  `external_post_id` values beginning `dry-run-` or `queued-` are the tell.
- The aggregator degrades to `feed_cache_json` on typed provider errors
  (`ProviderNotConfiguredError`, `ProviderTokenExpiredError`,
  `ProviderRateLimitError`). Token expiry is meant to set `needs_reauth` rather
  than blank the feed — a campus feed going empty is worse than a stale one.
- `SocialMediaIntegration.append_audit` saves on every call and caps at the last
  200 entries. It is an inline JSON log, not an audit table; do not treat it as
  tamper-evident.
