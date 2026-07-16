# apps/apicenter

> The API Center: integration governance with an audit trail, tenant API keys,
> API quotas, and the OAuth2 developer platform.

**Tenancy:** SHARED (public schema; `APIKey`, `APIQuota`, and `DeveloperApplication` carry a **nullable** `school` FK, where NULL means platform-wide)
**Scale:** 7 models · 11 migrations · 19 test modules · ~3.7k LOC

## What this app owns

API Center is the front door for everything outside the platform that wants in,
and the governance surface for everything inside it that talks out. It owns three
related things: the **one page where an operator toggles every Integration on or
off with a recorded reason**, the **credentials** that authenticate external
callers (API keys, and an OAuth2 authorization-code + refresh-token flow for
third-party apps), and the **quota rows** that cap how hard a tenant may hit the
API.

The governance decision is a deliberate single kill switch. `gating.py` states it:
when the API Center feature is enabled, `Integration.enabled` is *the* single
source of truth for whether an integration may be used — there is no second flag,
no per-caller override. And when the feature flag is off, gating is a no-op that
returns `True` rather than a default-deny, so turning API Center off cannot black
out a school's live integrations.

The credential decision is that **no secret is ever stored in recoverable form**.
An `APIKey` keeps only a `key_prefix` and a SHA-256 hash — the secret is shown once
at creation and is unrecoverable thereafter. OAuth access and refresh tokens are
likewise stored as hashes (`access_token_hash` / `refresh_token_hash`, both unique).
A leak of this app's tables leaks no usable credential.

## Key models

All 7 models:

| Model | Table | Purpose |
| --- | --- | --- |
| `APIKey` | `apicenter_apikey` | Tenant-scoped key for external API auth. Prefix `sk_live_`; only `key_prefix` + hash stored, secret shown once |
| `APIQuota` | `apicenter_apiquota` | Per-tenant or platform-wide quota. Types: `requests_per_minute`, `requests_per_day`, `webhooks_count` |
| `APIAuditLog` | `apicenter_apiauditlog` | Audit trail for Integration enable/disable and other governance changes |
| `DeveloperApplication` | `apicenter_developerapplication` | Third-party / integration app registration — the OAuth2 client |
| `OAuthAuthorizationCode` | `apicenter_oauthauthorizationcode` | Short-lived code for the `authorization_code` grant (10-minute lifetime) |
| `OAuthTokenPair` | `apicenter_oauthtokenpair` | Issued access + refresh tokens, hashed at rest. Access 1 hour, refresh 30 days; `revoked_at` for revocation |
| `MarketplaceExtensionSubmission` | `apicenter_marketplaceextensionsubmission` | Publishing pipeline for marketplace-listed extensions: draft → submitted → review → approved / rejected → published → deprecated |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `gating` | `is_integration_allowed()` — the single kill switch |
| Module | `oauth_service` | Token issuance, refresh exchange, code consumption, client credential verification |
| Module | `app_access` | Tenant-safe queryset narrowing for marketplace-linked apps |
| Module | `developer_platform` | `DEVELOPER_PLATFORM_LINKS` — a static link map to schema/docs/OAuth endpoints |
| URL (`apicenter:`) | `dashboard`, `toggle`, `api_keys`, `api_key_create`, `api_key_revoke` | Integration governance + key management |
| URL (`apicenter:`) | `api_portal_docs`, `sdk_docs`, `webhook_docs`, `partner_sandbox`, `app_certification` | Developer-facing docs surfaces |
| URL (`apicenter:`) | `webhook_subscription_create` / `_edit` / `_delete` | Webhook subscription management |
| URL (`oauth:`) | `oauth_urls` | Mounted separately at `/api/v1/oauth/` (see below) |

This app declares **no Celery tasks** and **no management commands**.

**Three URLconfs, mounted by other configs — this app mounts nothing itself:**
`urls.py` is included under the `apicenter` namespace by `config/urls.py`,
`config/tenant_urls.py`, `config/manager_urls.py`, and `config/public_urls.py`;
`oauth_urls.py` is mounted at `/api/v1/oauth/` under the `oauth` namespace; and
`ai_center_urls.py` is a separate super-operator URLconf mounted under
`/super/ai-center/`. Reversing an apicenter URL from the wrong host needs the right
`urlconf=`.

## Before you change this

- **`Integration.enabled` is the single kill switch — do not add a second.**
  `gating.py` says it in its module docstring. Note the flag semantics carefully:
  if the `enable_api_center` flag is **off**, `is_integration_allowed` returns
  `True` (no gating at all), and it only consults `integration.enabled` when the
  feature is on. A `None` integration is the sole unconditional `False`. Inverting
  the flag-off branch to default-deny would black out live integrations the moment
  someone toggled the feature.
- **Secrets are hash-only and unrecoverable by design.** `_hash_secret` is a plain
  SHA-256 and its docstring instructs callers to use a **constant-time compare** for
  verification — a naive `==` reintroduces a timing side channel. The `APIKey`
  docstring says the secret is shown only once at creation; there is deliberately no
  "reveal key" path, and adding one means storing the secret recoverably. Don't.
- **`APIQuota` rows are inert unless a view opts in.** Enforcement is not a global
  DRF throttle: it lives in `apps/api/rate_limit.py`, where
  `throttle_tenant_request()` calls `_get_apicenter_quota_for_school()` and prefers
  the `APIQuota` limit over the settings default. A view that never calls
  `throttle_tenant_request` is not quota-limited no matter what rows exist. Creating
  a quota row is not the same as enforcing it.
- **Quota resolution is school-then-platform, first row wins.**
  `_get_apicenter_quota_for_school` tries `school_id=<pk>` and falls back to
  `school__isnull=True` (the platform-wide row), taking `.first()` — there is no
  uniqueness constraint making that deterministic, so **duplicate rows for the same
  `(school, quota_type)` make the effective limit arbitrary**. Treat one row per
  pair as an invariant the schema does not enforce for you. The lookup also swallows
  every error and returns `(None, None)`, meaning **a broken quota lookup fails
  open**, falling back to the settings default rather than blocking traffic.
- **`webhooks_count` is a declared quota type with no reader.** It appears in
  `APIQuota.QUOTA_TYPES` and an operator can create the row, but nothing anywhere
  enforces it — `_get_apicenter_quota_for_school` is only ever called with
  `requests_per_minute` / `requests_per_day`, and its `else` branch is unreachable in
  practice. Do not present it to users as an enforced cap; either wire a consumer or
  leave it alone knowingly.
- **A nullable `school` means platform-wide, not "unscoped".** `APIKey`, `APIQuota`,
  and `DeveloperApplication` all allow `school=NULL` deliberately: a NULL row is the
  platform default that applies to every tenant. When you write a query here, decide
  explicitly whether NULL rows should be included — the views use
  `Q(school__isnull=True) | Q(school=school)` for exactly this reason. Getting it
  wrong either hides the platform default or leaks a tenant's row.
- **`verify_client_credentials` looks up `DeveloperApplication` by `client_id`
  across all tenants** and carries a `tenant-isolation-allow` marker justifying it:
  an OAuth client id is globally unique by protocol, and the token endpoint has no
  tenant context to scope by. That exemption is specific to credential verification —
  do not copy the marker onto queries that *do* have a school in hand.
- **Most of this app's 19 test modules do not test this app.** The `test_ai_center_*`
  suites exercise `services/ai_center/*` (indexing, friction analysis, KB generation,
  the Ollama client) through the super-operator URLconf that lives here. The AI logic
  is not in `apps/apicenter` — only its operator surface is. Expect to edit
  `services/ai_center/` when an `ai_center` test fails.
- `developer_platform.DEVELOPER_PLATFORM_LINKS` is a **static dict of paths**, not a
  reverse-based route map. If a route moves, this dict does not follow it and no test
  of a wrong path will fail — update it by hand.
