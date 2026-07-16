# apps/security

> Cross-cutting HTTP-layer defenses: Content-Security-Policy, the SSRF guard,
> the cache-backed rate limiter, and iframe-embed framing rules.

**Tenancy:** SHARED (public schema; these are request-layer defenses, not tenant data)
**Scale:** 0 models · 0 migrations · 21 test modules · ~2.8k LOC

## What this app owns

Security is a library of request-layer guards plus the test harness that proves
them. It owns four independent defenses: the CSP middleware and its violation
report endpoint, `ssrf.py` (the gate every outbound fetch of a tenant-supplied
URL must pass), `rate_limit.py` (a decorator for sensitive endpoints), and the
embed-framing override that lets Studio iframes work without weakening
`X-Frame-Options` globally.

What makes this app unusual is the ratio: ~2.8k LOC and **21 test modules** for
eight source modules. That is the point. Most of the app is adversarial tests —
tenant breach scenarios, boundary penetration, route leakage, GraphQL tenant
safety, impersonation approval — that assert platform-wide invariants owned by
*other* apps. If you are looking for where the platform proves it does not leak
across tenants, a large part of the answer is `apps/security/tests/`.

CSP is the one place with real operational history worth knowing. It has run in
**enforce mode by default since v2.57**: once the inline-style backlog hit zero,
`style-src` no longer needed `'unsafe-inline'` and `CSP_ENFORCE` flipped to
`True`. The policy is deliberately conservative — `'self'`-only for scripts,
styles, and connect — and operators can roll back to Report-Only with
`CSP_ENFORCE=0` if a regression surfaces.

## Key models

**None — this app declares no Django models and ships no migrations.** Nothing
here is stateful by design. The CSP violation counters live in the **cache**
(hourly buckets, `csp_violations:bucket:<hour_epoch>`) explicitly so that
readiness assessment needed no persistence model; they are runtime telemetry, not
an audit log, and they survive only as long as the cache TTL. For long-term
retention, log aggregation (Sentry / ELK) is the canonical surface. Rate-limit
counters are likewise cache-backed fixed-window keys.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Middleware | `ContentSecurityPolicyMiddleware` | `csp_middleware`; also exports the `csp_nonce` context processor |
| Middleware | `EmbedSameOriginFrameMiddleware` | Relaxes framing to `SAMEORIGIN` only for explicit `?embed=1` |
| View | `csp_violation_report` | Routed in `config/urls.py` at `/security/csp-report/` (name `csp_violation_report`) |
| Module | `ssrf` | `is_safe_public_url(url)` → `(ok, reason)` |
| Module | `rate_limit` | `@rate_limit(scope=..., limit=..., window_seconds=...)` → HTTP 429 + `Retry-After` |
| Module | `csp_readiness` | `assess_csp_readiness()` — config/wiring preflight |
| Module | `csp_violation_counter` | Reads the hourly cache buckets |
| Mgmt command | `verify_csp_readiness` | Run until exit 0 before flipping enforcement |

No `urls.py` of its own — the report endpoint is wired directly in
`config/urls.py`.

**Scope limit worth stating:** `csp_readiness` asserts *config and wiring*
preconditions only. It does **not** read violation counts to decide readiness,
because reports are persisted log-only. Runtime readiness is a human runbook:
run the command until clean, watch `csp_violation` warnings for a window
proportional to traffic (7+ days), then set `CSP_ENFORCE=1`.

## Before you change this

- **The app label is `rmc_security`, not `security`.** `SecurityConfig` sets it
  explicitly. Anything that resolves this app by label — `get_app_config`,
  migrations, `app_label` Meta — needs `rmc_security`. The directory is still
  `apps/security`, which is why this README is titled `apps/security`.
- **`ssrf.py` is a resolve-then-check guard, and it says so.** It resolves the
  hostname and checks **every** resolved IP against private / loopback /
  link-local (including the `169.254.169.254` cloud-metadata endpoint) / reserved
  / multicast / unspecified. It is *not* a complete DNS-rebinding defense on its
  own — a name can resolve differently between the check and the connect. The
  practical hole is closed by checking at **both** registration time and delivery
  time. If you add a new outbound-fetch path, you owe it both calls; a caller
  needing more should pin and connect to a validated IP.
- **Unparseable IP means blocked, not allowed.** `_ip_blocked` returns `True` on
  `ValueError`. Fail-closed is the contract here — do not "helpfully" pass through
  what you could not parse.
- **The CSP report endpoint's exemptions are each deliberate.** It is CSRF-exempt
  because browsers do not send our CSRF cookie on a report POST; rate-limited
  because one tab refresh can generate many reports; body-size-capped at 64 KiB to
  avoid log spam; and PII-free in the log line (directive + blocked-uri +
  document-uri only). Do not log the report body.
- **`'unsafe-inline'` / `'unsafe-eval'` in `script-src` are enforcement-time
  killers** and `csp_readiness` blocks on them. Adding an inline `<script>`,
  reach for the per-request nonce (`csp_nonce` context processor,
  `<script nonce="{{ csp_nonce }}">`) — not a policy relaxation. Extra origins
  belong in the `CSP_EXTRA_*` settings, not hardcoded in `_DEFAULT_DIRECTIVES`.
- **`/admin/` and `/static/` bypass CSP** to avoid breaking the Django admin and
  static delivery. That is a known, scoped exemption — widening it is not the fix
  for a policy violation on a tenant page.
- **Embed framing keys off `?embed=1` only**, and honors views that set
  `xframe_options_exempt`. Global `X_FRAME_OPTIONS` stays `DENY`; without this
  narrow override Launch Studio and Automation Studio iframes show "refused to
  connect". Do not solve an iframe problem by relaxing the global default.
- Note a stale comment: `csp_readiness`'s docstring still describes `style-src
  'unsafe-inline'` as surfaced known-debt, but `_DEFAULT_DIRECTIVES` has had
  `style-src` at `('self',)` since v2.57. The code is right; that line of the
  docstring predates the flip.
