# Changelog

All notable changes to `@runmycampus/webhook-verifier` (npm) will be
documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0-rc.1] — 2026-05-19

Release candidate for 1.0.0. **No public-API changes vs 0.2.0.** The
package will graduate to 1.0.0 after a 90-day field-test window during
which subscribers may report any verifier bug or wire-format drift.
After the window closes the exported names listed in `STABILITY.md`
are frozen — breaking changes require a 2.0 major bump.

### Added

- `STABILITY.md` — frozen public-API surface, versioning policy,
  deprecation policy, stability tiers.
- `MIGRATION_TO_1_0.md` — 0.x → 1.0 migration guide (no changes
  required for most users).
- `CHANGELOG.md` — this file.

### Changed

- Aligned all internal references to the legacy-header deprecation
  date with `2026-08-18` (was `2026-08-17` in some doc strings —
  cosmetic-only one-day drift; canonical date is the dispatcher
  constant `LEGACY_HEADER_DEPRECATION_DATE`).

### Deprecated

- `verifySignature()` continues to work but is now formally an alias
  for the more ergonomic `verify(headers, body, secret)` API. A
  `@deprecated` JSDoc tag is now present and TypeScript will surface
  a warning at the call site. Removal scheduled for 2.0 (no earlier
  than 90 days after 1.0.0 ships — see deprecation policy in
  `STABILITY.md`).

## [0.2.0] — 2026-05-19

### Added

- `verify(headers, body, secret, { acceptLegacy: true })` — dual-header
  family aware verification (canonical `X-RunMyCampus-*` family
  preferred, legacy `X-Migration-Cloud-*` family accepted during the
  2026-05-18 → 2026-08-18 dual-emit window). Returns a `VerifyResult`
  type carrying a `usedLegacyHeaderFamily` flag so subscribers can
  warn-log without changing their fail-closed posture.
- `LEGACY_SIGNATURE_HEADER`, `LEGACY_TIMESTAMP_HEADER`,
  `LEGACY_EVENT_HEADER`, `LEGACY_VERSION_HEADER` constants exported.
- `VerifyResult`, `HeaderMap`, `HeaderValue`, `VerifyApiOptions`
  types exported.
- Case-insensitive header lookup helpers.

## [0.1.0] — 2026-05-18

### Added

- Initial npm release of `@runmycampus/webhook-verifier`.
- HMAC-SHA256 webhook signature verification (canonical JSON).
- `verifySignature()` lenient boolean API.
- `verifySignatureStrict()` throwing-API surface.
- `computeSignature()` helper for tests and replay tooling.
- Canonical JSON helpers: `canonicalize()`, `canonicalizeToString()`,
  `canonicalSha256Hex()`, `CanonicalJSONError`.
- Typed `VerificationError` + 4 subclasses
  (`ClockSkewError`, `MissingHeaderError`, `BadSignatureError`,
  `UnsupportedAlgorithmError`).
- Clock-skew tolerance honoring `X-RunMyCampus-Timestamp` (default
  300 seconds, matches Stripe / GitHub / Twilio).
- Constant-time compare via Node `crypto.timingSafeEqual` (with a
  manual XOR fold fallback for runtimes lacking it).
- Dual ESM + CJS build via tsup; bundled `.d.ts` for TypeScript.
- Dual-runtime: WebCrypto (browsers / Node 19+ / Edge) with a
  `node:crypto` fallback for Node 16 — 18. Zero runtime
  dependencies.
- Node 16+ supported.
- Shared `test/fixtures/canonical-cases.json` test corpus (16 cases:
  unicode/CJK/escaped/nested) asserted byte-for-byte and SHA-256
  equal across the Python and JS twins. Drift between the twins
  would silently break customer signature verification.
- npm provenance (OIDC) — no npm token in repo secrets.

[1.0.0-rc.1]: https://github.com/runmycampus/runmycampus/releases/tag/webhook-verifier-js-v1.0.0-rc.1
[0.2.0]: https://github.com/runmycampus/runmycampus/releases/tag/webhook-verifier-js-v0.2.0
[0.1.0]: https://github.com/runmycampus/runmycampus/releases/tag/webhook-verifier-js-v0.1.0
