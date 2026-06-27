# Data-residency border-lock — fail-closed cross-region enforcement (SOT)

This is the operator + engineer reference for the **app-layer border-lock**: the
control that, when armed, refuses to read or write a tenant's PII from a store
outside that tenant's regulatory region — and refuses it **fail-closed** (raises
HTTP 403, audited), rather than silently letting the data cross the border.

It complements the two pre-existing residency docs, which it does NOT supersede:

- [`docs/DATA_RESIDENCY_AND_COMPLIANCE.md`](DATA_RESIDENCY_AND_COMPLIANCE.md) — baseline data-handling posture.
- [`docs/compliance/DATA_RESIDENCY_LEGAL_GUIDE.md`](compliance/DATA_RESIDENCY_LEGAL_GUIDE.md) — the per-corridor legal/hosting roadmap.

Those describe the region-agnostic default. This doc describes the *enforcement
code* that was added on top (metric #27) and how to turn it on.

> **TL;DR** — Set `DATA_RESIDENCY_ENFORCE=1`. While off (the default) every gate
> below is a no-op and behaviour is unchanged. While on, any op that would serve a
> region-A tenant from a region-B alias raises `ResidencyViolation` (a
> `PermissionDenied` → 403) and writes a CRITICAL audit record. **This is an
> application-layer control. It does NOT by itself provide physical per-region
> Postgres replicas — that remains an ops/deploy item.** Until those replicas
> exist, the border-lock is the binding guarantee because it fails the op closed.

---

## 1. The flag and how it arms

`residency_enforced()` (`apps/compliance/cross_border_export.py:61`) is true when
**either**:

- the env var `DATA_RESIDENCY_ENFORCE` ∈ {`1`,`true`,`yes`} — an ops flip with no
  redeploy needed (`cross_border_export.py:68`), **or**
- the Django setting `DATA_RESIDENCY_ENFORCE` is truthy — so
  `@override_settings(DATA_RESIDENCY_ENFORCE=True)` works in tests
  (`cross_border_export.py:73`).

The setting itself reads the env var and defaults to **off**:
`DATA_RESIDENCY_ENFORCE = os.getenv("DATA_RESIDENCY_ENFORCE", "0") == "1"`
(`config/settings.py:466`); it is also registered in
`config/settings_registry.py:591`.

A tenant's authoritative region is `effective_region(school)`
(`apps/schools/data_residency.py:116`): explicit `School.data_region` wins,
otherwise it is derived from `country_code`, otherwise `"global"`.

## 2. The three enforcement points (defence in depth)

The same predicate guards three layers, so a cross-border op is blocked no matter
where it originates:

| Layer | Code | What it blocks |
|-------|------|----------------|
| **DB router** (the choke point every ORM read/write flows through) | `_enforce_residency_for_alias` (`apps/siteconfig/db_router.py:63`), called from `db_for_read`/`db_for_write` (`:106`/`:117`) | a region-A tenant whose resolved alias is region-B — calls `enforce_region_match(school, alias, kind="db_route")` (`db_router.py:87`) |
| **Request middleware** | `RegionalDatabaseMiddleware._enforce_inbound_residency` (`apps/platform_runtime/middleware_regional_db.py:60`) | a request that arrived **already pinned** to a foreign alias (a prior-request leak, an operator forcing a foreign region) before routing runs — only active under `ENABLE_MULTI_REGION` (`:43`) |
| **Export path** | `enforce_cross_border_export` (`cross_border_export.py:219`) + the soft UI predicate `cross_border_export_blocked` (`:182`) | an export whose destination region ≠ the school's `data_region` |

The hard gate `enforce_region_match` (`cross_border_export.py:128`) is the shared
core. It is a no-op when: there is no school; enforcement is off; the target
region is empty; the source region is unknown; or the regions match. Only a
genuine mismatch raises.

## 3. Fail-closed behaviour

`ResidencyViolation` (`cross_border_export.py:40`) subclasses
`django.core.exceptions.PermissionDenied`, so a violation surfaces as **HTTP 403**
(not a 500) and is caught by any existing `PermissionDenied` handling, while
remaining a typed marker callers can catch specifically. It carries
`source_region` / `target_region`.

Every block is audited by `_audit_residency_violation`
(`cross_border_export.py:80`):

- A structured **CRITICAL ERROR log line** (`residency.violation kind=… school=…
  source_region=… target_region=…`) is always written — this is the durable
  record, because the whole point of failing closed is that a writable DB in the
  correct region may not be reachable at block time.
- A best-effort `AuditLog` row (`AuditLog.Action.ACCESS_DENIED`, sensitivity
  `CRITICAL`) is *also* attempted (`cross_border_export.py:107`), but its failure
  is swallowed and never masks the block.

Important: the router's helper catches only plumbing errors
(`OPTIONAL_DB_ROUTER_ERRORS`, `db_router.py:9`). `ResidencyViolation` is **not**
in that tuple, so a genuine cross-region violation still propagates rather than
being downgraded to a silent allow (`db_router.py:88` comment).

## 4. How to enable it (operator runbook)

1. Provision (or accept the deferral on) per-region storage. The control works
   *before* replicas exist by failing closed; it does not require them, but you
   should know which case you are in.
2. Set each tenant's regulatory region: populate `School.data_region`, or rely on
   `country_code` derivation. Validate with
   `manage.py verify_data_residency --fix-derive` (referenced at
   `config/settings.py:438` / `:464`).
3. Flip the flag: `DATA_RESIDENCY_ENFORCE=1` in the environment. No redeploy is
   required for the env path (`residency_enforced()` reads it live).
4. Watch the `residency.violation` ERROR log channel and the `AuditLog`
   ACCESS_DENIED rows for blocked attempts.

To roll back, unset the env var (and any Django-setting override). Enforcement
returns to no-op immediately.

## 5. Honest scope / limitations

- **App-layer only.** Three modules (`cross_border_export.py:17`,
  `db_router.py:74`, `middleware_regional_db.py:21`) all carry the same explicit
  HONEST-SCOPE note: this refuses to *serve* an out-of-region request; it does not
  itself create physical per-region replicas. Those `DATABASES` aliases remain an
  ops/deploy item.
- **Read replicas are not residency-checked.** A `DATABASE_READ_REPLICA_ALIAS`
  read-split is treated as an operational replica, not a regional binding
  (`db_router.py:108` comment) — the region-carrying tenant alias is the
  residency choke point.
- **Middleware blocks the pre-pinned case, not the alias it derives.** The alias
  resolved from the school is by construction in-region, so the middleware only
  refuses a foreign region that an upstream layer *already* pinned
  (`middleware_regional_db.py:12`).
- A separate, older soft path exists in `apps/schools/data_residency.py`
  (`assert_aligned_or_log` at `:161`, `CrossRegionWriteError` at `:152`) for
  warn-only logging; the hard 403 path documented here is the
  `cross_border_export` family.

## 6. Test / proof anchors

- `effective_region` derivation: `apps/schools/data_residency.py:116`.
- Flag plumbing: `residency_enforced()` honours both env and setting
  (`cross_border_export.py:61`).
- The router does not downgrade a real violation to an allow: `db_router.py:88`
  (comment) — `ResidencyViolation` is excluded from `OPTIONAL_DB_ROUTER_ERRORS`.
