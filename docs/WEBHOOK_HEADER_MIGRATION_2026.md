# Webhook Header Family Migration — 2026

## TL;DR

RunMyCampus is renaming the outbound webhook HTTP header family from
`X-Migration-Cloud-*` to `X-RunMyCampus-*`. The platform now emits **both
families** on every outbound delivery during a 90-day dual-emit window.

* **Announce:** 2026-05-18 (RunMyCampus v3.35.0)
* **Dual-emit window:** 2026-05-18 → 2026-08-18 (90 days)
* **Legacy removal:** RunMyCampus v3.40.0 (the earliest release on or
  after 2026-08-18). Customers who have not migrated by then will see
  signature-verification failures.

The HMAC signature bytes are **byte-identical** in both header families.
Only the header *names* change. Your verifier code already works — it
just needs to read the new name.

---

## Why we're doing this

The `Migration Cloud` brand was an internal-only label for the SIS
migration product line. As RunMyCampus has grown its public surface
area (marketplace, orchestration, schoolops, identity broker), customer
integrations now span products well beyond migration. The header family
should reflect the platform, not one product line.

Renaming sooner protects customers from a more painful rename later
(when the legacy name has compounded years of integration debt). The
dual-emit window gives every customer enough time to switch without
breaking signature verification for any in-flight integration.

---

## Header changes

| Legacy (deprecated 2026-08-18)  | New canonical name              |
|---------------------------------|---------------------------------|
| `X-Migration-Cloud-Signature`   | `X-RunMyCampus-Signature`       |
| `X-Migration-Cloud-Timestamp`   | `X-RunMyCampus-Timestamp`       |
| `X-Migration-Cloud-Version`     | `X-RunMyCampus-Version`         |
| `X-Migration-Cloud-Event`       | `X-RunMyCampus-Event`           |
| `X-Migration-Cloud-Delivery`    | `X-RunMyCampus-Delivery`        |

A new header is also present on every delivery during the window:

```
X-RunMyCampus-Header-Deprecation: legacy-x-migration-cloud-headers-will-be-removed-after-2026-08-18
```

Use it to confirm at receive time that you're inside the migration
window. After the window closes, the header is no longer emitted.

### Signature bytes are unchanged

The HMAC-SHA256 digest is computed over the canonical JSON body
(`json.dumps(payload, sort_keys=True, separators=(",", ":"))` —
UTF-8, sorted keys, no whitespace). The dispatcher emits the same
digest in both `X-Migration-Cloud-Signature` and
`X-RunMyCampus-Signature`. You can swap header names atomically; you
do not need to recompute or re-verify anything.

---

## Customer action items

### Step 1 — Install the official SDK (recommended)

The packaged SDKs already use the new header family:

```bash
# Python
pip install runmycampus-webhook-verifier

# JavaScript / TypeScript
npm install @runmycampus/webhook-verifier
```

Source:
* [`packages/runmycampus-webhook-verifier-py/`](../packages/runmycampus-webhook-verifier-py/)
* [`packages/runmycampus-webhook-verifier-js/`](../packages/runmycampus-webhook-verifier-js/)

Both packages ship zero runtime dependencies, constant-time HMAC
compare, optional clock-skew enforcement (`X-RunMyCampus-Timestamp`,
default 300s window), and typed-error strict mode. They are
byte-for-byte interoperable.

If you migrate to the packaged SDK, you are done — the SDK reads
`X-RunMyCampus-Signature` natively, and the dispatcher is already
emitting that header.

### Step 2 — Or update your existing verifier code

If you maintain your own verifier (Flask middleware, Express
middleware, a Cloudflare Worker, etc.), update **only the header
name**. The body, the HMAC algorithm, and the secret material are
unchanged.

#### Flask (Python) — before / after

```python
# BEFORE (legacy header, still works during window)
header = request.headers.get("X-Migration-Cloud-Signature", "")

# AFTER (new canonical header)
header = request.headers.get("X-RunMyCampus-Signature", "")
```

#### Express (Node) — before / after

```js
// BEFORE
const header = req.get("X-Migration-Cloud-Signature");

// AFTER
const header = req.get("X-RunMyCampus-Signature");
```

#### Belt-and-suspenders (recommended during window)

If you want to migrate without a flag day, fall back gracefully:

```python
header = (
    request.headers.get("X-RunMyCampus-Signature")
    or request.headers.get("X-Migration-Cloud-Signature")
    or ""
)
```

This pattern is forward-compatible — it keeps working after the legacy
header is removed and is robust against header-name typos during
deploys.

### Step 3 — Test against the dual-emit window

While the window is open (2026-05-18 → 2026-08-18), every outbound
delivery carries both header families and the deprecation pointer.
Confirm in your receiver logs that:

1. Your verifier reads `X-RunMyCampus-Signature`.
2. The signature matches against the raw body bytes (not re-serialized
   JSON — re-serializing reorders keys and breaks the digest).
3. Your handler is idempotent on `X-RunMyCampus-Delivery` (the same
   delivery may arrive more than once after transient failure).

### Step 4 — Confirm before the cutover

Before 2026-08-18, RunMyCampus operators will email each partner with
an active webhook subscription. If your team has migrated, reply with
confirmation; we'll de-prioritize the cutover-warning escalation path.

If you cannot migrate by 2026-08-18, contact RunMyCampus support **before
the date** — we can extend the dual-emit window for individual partners
on a case-by-case basis. We will not extend it silently or by default.

---

## Backward compatibility notes

* **Legacy headers retain identical signature bytes.** If your verifier
  reads `X-Migration-Cloud-Signature` today and confirms the HMAC
  matches the body, it will continue to read the same digest from the
  same header through 2026-08-18. No change is required to your secret,
  your hash algorithm, or your canonical-body assumptions.

* **The deprecation header is informational only.** Receivers should
  not gate request acceptance on its presence or absence. The
  dispatcher omits it after the window closes.

* **`MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=False` is an operator escape
  hatch.** Some self-hosted RunMyCampus operators will flip this
  setting early once they confirm their downstream receivers have
  migrated. If you operate inside such an environment, your traffic
  will see only the new family — confirm with your operator before
  relying on dual-emit being present.

* **The vendored standalone verifier files at
  `apps/migration_cloud/api/static/runmycampus_webhook_verifier.js` and
  `apps/migration_cloud/api/webhook_verifier_sdk.py` already use the
  new header.** They are marked DEPRECATED in favor of the packaged
  SDKs but remain available through v4.0.0 for air-gapped customers.

---

## Operator-side reference

For RunMyCampus operators running the platform:

* Setting: `MIGRATION_CLOUD_EMIT_LEGACY_HEADERS`
  (env `RMC_EMIT_LEGACY_WEBHOOK_HEADERS`).
* Default: `"1"` (legacy emission ON).
* Set to `"0"` only after auditing every active webhook subscription
  for the partner-confirmed migration state.
* No data migration is required to flip the flag — both header
  families compute the same digest from the same `secret_ciphertext`
  source.

The dispatcher source of truth lives in
[`apps/migration_cloud/api/webhook_dispatch.py`](../apps/migration_cloud/api/webhook_dispatch.py)
under `_build_outbound_headers()`. The deprecation date constant
(`LEGACY_HEADER_DEPRECATION_DATE`) is the single source of truth for
the timeline — updating it requires a coordinated PR plus customer
notification.

---

## Timeline summary

| Date          | RMC release | Event                                                   |
|---------------|-------------|---------------------------------------------------------|
| 2026-05-18    | v3.35.0     | Dual-emit begins; deprecation header added; announce.   |
| 2026-08-18    | (TBD)       | Customer migration deadline.                            |
| ≥ 2026-08-18  | v3.40.0+    | Legacy `X-Migration-Cloud-*` family removed.            |

For questions: open an issue on the RunMyCampus support channel or
email your account team.
