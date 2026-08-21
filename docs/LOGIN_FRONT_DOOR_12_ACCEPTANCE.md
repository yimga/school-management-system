# Local Front Door — 12-point acceptance contract

All twelve capabilities are release requirements. `Cockpit health` verifies the
shipped wiring from source markers and must report 12/12; the regression suite
fails if any capability disappears.

| # | Capability | Load-bearing implementation | Acceptance evidence |
|---|---|---|---|
| 1 | Passkeys and trusted devices | Anonymous WebAuthn options/verification, resident-key enrollment, host-bound membership validation, rate limits | Real WebAuthn option generation plus unavailable-library and route tests |
| 2 | Returning-user entrance | Tenant-host-scoped role memory; no name, email, or account identifier stored | Login DOM/JS contract tests |
| 3 | Role-aware sign-in | Staff, parent and student role gateway drives method rails (passkey/SSO/password; magic link/invite; school ID/email/passkey) while server authorization remains authoritative | Login interaction/context tests |
| 4 | Offline continuity | Authenticated capability mint, AES-GCM/PBKDF2 device-PIN enrollment, host/expiry validation and read-only local unlock | Offline token, mint, vault wiring and expiry/host regression tests |
| 5 | School-day information | Tenant-configured public-safe dashboard feed, announcements and cached anonymous metadata | Immersive context and no-clipping tests |
| 6 | Tenant publisher | Announcement create/update, draft/approval, scheduling, expiry and immutable audit log | Announcement model/form contracts and health wiring |
| 7 | Local partners | Tenant-controlled sponsor configuration, safe URLs, maximum placement, offline suppression and dismiss control | Cockpit form/context tests |
| 8 | Guided recovery | Magic link, password reset, invite/guardian linking and public support shortcuts | Magic-link and recovery tests |
| 9 | Verified-school protection | RP host/origin validation, tenant membership binding and generic anti-enumeration errors | Passkey route/options tests and server-side tenant guard |
| 10 | Accessible authentication | Labels, live regions, keyboard role navigation, focus movement, reduced-motion support and responsive layouts | Template, CSS and login canvas regression tests |
| 11 | Public-data assistant | Deterministic access help limited to recovery, invite and offline guidance; no account lookup endpoint | Login assistant contract tests |
| 12 | Health and diagnostics | Twelve independent source-wiring checks with computed score and direct remediation links | `test_all_twelve_health_checks_use_real_shipped_markers` |

## Non-negotiable offline boundaries

- Local mode requires a capability issued during an authenticated online session.
- The capability is encrypted locally with a user-created device PIN.
- Unlock rejects a different tenant host and expired capability.
- Local mode is read-only by default; finance, payroll, configuration, exports
  and other sensitive operations require verified online authentication.
- Sponsored content is hidden whenever freshness cannot be verified offline.

## Honest leftovers vs the approval HTML mock

- The HTML mock is an **implementation contract**, not a pixel canvas. Live login uses
  design tokens and `.rmc-*` — not mock hex (`#070b18`, `#ef4f64`).
- Returning-user memory stores **role / school host / prefs only**. Name and email
  are never written to `localStorage`.
- Student sign-in is school ID or email plus passkey. **QR-badge login is not
  implemented** and must not be advertised on the live doorway.

