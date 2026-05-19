# `@runmycampus/webhook-verifier` — Stability contract

This document describes the **frozen public-API surface** of the
`@runmycampus/webhook-verifier` npm package, the versioning policy
under which it evolves, and the deprecation policy that governs
removals.

The contract takes effect at 1.0.0. The current 1.0.0-rc.1 release
candidate publishes the contract for a 90-day field-test window
before 1.0.0 graduates. See `CHANGELOG.md` for the release timeline.

## Public API surface

The following names are exported from the top-level
`@runmycampus/webhook-verifier` package and are considered **stable**
under the versioning policy below.

**Values / functions:**

- `verify`
- `verifySignature`
- `verifySignatureStrict`
- `computeSignature`
- `canonicalize`
- `canonicalizeToString`
- `canonicalSha256Hex`
- `CanonicalJSONError`
- `VerificationError`
- `ClockSkewError`
- `MissingHeaderError`
- `BadSignatureError`
- `UnsupportedAlgorithmError`
- `SIGNATURE_HEADER`
- `TIMESTAMP_HEADER`
- `EVENT_HEADER`
- `VERSION_HEADER`
- `LEGACY_SIGNATURE_HEADER`
- `LEGACY_TIMESTAMP_HEADER`
- `LEGACY_EVENT_HEADER`
- `LEGACY_VERSION_HEADER`
- `SUPPORTED_PREFIX`
- `DEFAULT_TOLERANCE_SECONDS`
- `VERSION`

**Types (`export type`):**

- `BytesLike`
- `VerifyOptions`
- `VerifyApiOptions`
- `VerifyResult`
- `HeaderMap`
- `HeaderValue`

Anything not listed above is **internal** — its name, signature, and
existence may change in any release.

## Versioning policy

The package follows [Semantic Versioning 2.0](https://semver.org/spec/v2.0.0.html)
with the customary mapping:

| Change shape                                    | Bump   |
|-------------------------------------------------|--------|
| Removing an exported name; renaming a parameter; tightening a parameter type beyond what the prior contract accepted; flipping a default that alters behavior; removing or renaming a class | **major** |
| Adding a new exported name; adding a new optional field to an options-bag interface with a default that preserves prior behavior; adding a new class | **minor** |
| Fixing a bug; tightening internal validation; documentation; performance | **patch** |

Pre-1.0 (`0.x`) versions did NOT carry these guarantees. The 0.x → 1.0
transition is intentionally non-breaking — see `MIGRATION_TO_1_0.md`.

## Deprecation policy

When a name is to be removed or its behavior is to change in a way
that would otherwise require a major bump, it is first **deprecated**
under the following rules:

1. The deprecation is announced in `CHANGELOG.md` with the target
   removal version and the planned removal date.
2. The name continues to function for at least **90 days** after the
   announcement, AND for at least one full minor-version cycle.
3. The deprecated name carries a TypeScript `@deprecated` JSDoc tag
   so editors and linters surface it at the call site.
4. Removal lands in the major version named in step 1, never sooner.

The 90-day floor exists so customer integrations have a fair runway
to migrate even when the upstream cadence is faster than their
maintenance windows.

## Stability tiers

Different parts of the surface carry different stability commitments:

| Tier        | Members | Guarantee |
|-------------|---------|-----------|
| **Stable**  | `verify`, `verifySignatureStrict`, `computeSignature`, `canonicalize`, `canonicalizeToString`, `canonicalSha256Hex`, `CanonicalJSONError`, all `*Error` classes, all `*_HEADER` and `*_PREFIX` and `*_SECONDS` constants, `VERSION`, all exported types listed above | Frozen per the versioning policy above. |
| **Deprecated alias** | `verifySignature` | Continues to work; carries a `@deprecated` JSDoc tag. New code should use `verify(...)` which returns a `VerifyResult` carrying the legacy-header-family flag. Removal scheduled for 2.0 (no earlier than 90 days after 1.0.0 ships). |
| **Unstable** | Any name prefixed with `_` (e.g. `_toUint8`, `_coerceHeader`, `_getHeader`); any module path under the package internals not re-exported from `index.ts`. | May change in any release, including patches. Do not import. |

## Legacy-header dual-emit window

The `verify(...)` function accepts an options-bag field `acceptLegacy`
whose default is **`true`** in the 1.x line. This preserves
compatibility for subscribers still reading the original
`X-Migration-Cloud-*` header family during the platform's 2026-05-18
→ 2026-08-18 dual-emit window. The default will flip to **`false`**
in 2.0 (no earlier than 90 days after the dual-emit window closes).
Subscribers who have migrated should pass `acceptLegacy: false`
explicitly to fail-closed on legacy-only deliveries today.

The dispatcher-side constant `LEGACY_HEADER_DEPRECATION_DATE` lives
in `apps/migration_cloud/api/webhook_dispatch.py` in the RunMyCampus
platform repo and is the **single source of truth** for the cutover
date. This SDK reflects it; if the two ever disagree the dispatcher
wins.
