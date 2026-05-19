# Migrating from 0.x to 1.0

**TL;DR: for most users, zero changes are required.** The 0.x → 1.0
transition publishes a stability contract over the existing surface;
no exported name has been removed, no type has been tightened beyond
its 0.2.0 contract, and no default has been flipped between 0.2.0 and
1.0.0.

If you were already using `import { verify, VerificationError, ... }
from "@runmycampus/webhook-verifier"` in 0.2.0, your code continues to
work unchanged in 1.0.0.

## What changed semantically (nothing for callers)

- The names listed in `STABILITY.md` are now **frozen** under semver.
  Breaking changes require a 2.0 bump.
- `verifySignature()` is now formally a deprecated alias for
  `verify()`. It still works; it now carries a `@deprecated` JSDoc
  tag so your editor and TypeScript will flag it at the call site.
- The legacy-header deprecation date in package documentation now
  matches the dispatcher constant `LEGACY_HEADER_DEPRECATION_DATE`
  (`2026-08-18`). A cosmetic one-day drift in some doc strings was
  resolved.

## What will change in 2.0 (not 1.0)

Plan ahead — these are the only known breaking changes scheduled for
the next major bump. None ships in 1.0.

- `verify(headers, body, secret, { acceptLegacy: true })` — the default
  flips from `true` to `false`. After the 2026-05-18 → 2026-08-18
  dual-emit window closes and the dispatcher stops emitting the legacy
  `X-Migration-Cloud-*` family entirely, the SDK default-on for legacy
  acceptance becomes a silent failure-attractor. The flip is gated
  behind at least 90 days of field test after 1.0.0 ships and at
  least 90 days after the dispatcher cutover, whichever is later.

  **Forward-compatible idiom (works in 0.2.0+ AND in 2.0+):**

  ```ts
  import { verify } from "@runmycampus/webhook-verifier";

  const result = await verify(req.headers, bodyBytes, secret, {
    acceptLegacy: false,
  });
  ```

  Subscribers who have NOT yet migrated to the new header family
  should keep the default until the dispatcher cuts over, then flip
  explicitly. See `STABILITY.md` § "Legacy-header dual-emit window"
  for the full timeline.

- `verifySignature()` (the deprecated alias) is removed. Replace with
  `verify(...)` returning a `VerifyResult`, or with
  `verifySignatureStrict(...)` if you want exception-based control
  flow over the boolean lenient form.

## Recommended pre-2.0 cleanup

If you'd like to be ready for 2.0 today:

1. Replace `verifySignature(body, sigHeader, secret, opts)` with
   `(await verify(req.headers, body, secret)).valid` — note that
   `verify` takes the entire header map, not just the signature
   value, so it can transparently fall back across header families.
2. Pass `acceptLegacy: false` explicitly once your stack has migrated
   to reading the canonical `X-RunMyCampus-*` family.
3. Inspect `result.usedLegacyHeaderFamily` and emit a one-line
   warn-log when it flips true. This is the early-warning signal
   that one of your delivery sources is still on the legacy family.

## Where to ask for help

- Issues: <https://github.com/runmycampus/runmycampus/issues>
- Header-migration runbook: `docs/WEBHOOK_HEADER_MIGRATION_2026.md`
  in the platform repository.
- Verification doc: `apps/migration_cloud/api/static/WEBHOOK_VERIFICATION.md`
  in the platform repository.
