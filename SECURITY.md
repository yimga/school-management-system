# Security

- **Secrets:** Never commit `.env`, `.env.local`, or any file containing real API keys or passwords. Use `.env.example` with placeholders only. **If any API key or secret was ever committed (e.g. in `.env.local`), rotate it immediately** — revoke and issue new keys in the provider dashboard; update local and CI secrets; document rotation in runbooks. Remove the file from history (e.g. `git rm --cached .env.local`) and ensure it is in `.gitignore`. See [.env.example](.env.example) for expected placeholders.
- **CI guardrail:** The repo must not contain committed `.env` or `.env.local`; CI or pre-commit checks fail if these files are present (see [scripts/check_no_committed_env.sh](scripts/check_no_committed_env.sh)).
- **CSRF:** All `@csrf_exempt` endpoints are audited in [docs/security/CSRF_EXEMPT_AUDIT.md](docs/security/CSRF_EXEMPT_AUDIT.md). Use token or signature verification instead of exemption where possible.
- **Raw SQL and subprocess:** See [docs/security/raw_sql_audit.md](docs/security/raw_sql_audit.md) and [docs/security/subprocess_safety_audit.md](docs/security/subprocess_safety_audit.md).
- **AllowAny APIs:** Public endpoints are audited in [docs/security/ALLOWANY_API_AUDIT.md](docs/security/ALLOWANY_API_AUDIT.md). AllowAny views must be rate-limited and return minimal data.
- **Session timeout:** For shared computers, set `SESSION_INACTIVITY_TIMEOUT_MINUTES=15` or `30` in `.env` so sessions expire after inactivity. Otherwise `SESSION_COOKIE_AGE` (default 4 hours) and role-based timeouts in `ROLE_SESSION_TIMEOUTS` apply. See `config/settings.py` (SESSION_* and ROLE_SESSION_TIMEOUTS).
- **Auth rate limiting:** Login, signup, and password-reset flows use rate limiting (e.g. django-ratelimit) where configured; brute-force protection and optional account lockout after N failures are enforced per security audit. Implementation status: see `config/settings.py` (RATELIMIT_* or equivalent) and [apps/accounts/](apps/accounts/) views; rate limits must be applied to login, signup, and password-reset endpoints. **9.5/10:** All auth endpoints must be rate-limited; document limits in this file or in [docs/security/](docs/security/).
- **Account lockout:** Optional lockout after N failed attempts is documented in security audit; implement in [apps/accounts/](apps/accounts/) (e.g. lockdown path, cooldown, or integration with SecurityAuditLog) and expose in security health UI. **9.5/10:** Lockout or cooldown must be configurable and auditable.
- **Security health UI:** Operators and users can see strength (password, MFA, recovery) and missing tasks via [apps/accounts/views_security.py](apps/accounts/views_security.py) and related templates; export is MFA-gated. **9.5/10:** Security strength and remediation steps must be visible and actionable.
- **Security audit:** Login, logout, and sensitive actions are logged to `SecurityAuditLog`; see [apps/accounts/security_audit.py](apps/accounts/security_audit.py) and [apps/accounts/views_security.py](apps/accounts/views_security.py).

## Reporting a vulnerability

**Do not open a public GitHub issue for security reports.** Public issues can expose active exploitation paths before a fix is ready.

### Private channel

Email **security@runmycampus.com** with a concise report.

> **Maintainer note:** This mailbox must be monitored by the RunMyCampus security
> response team. Confirm routing and on-call coverage before advertising it externally.

### What to include

- Affected component (URL, API route, host surface, or companion artifact version).
- Steps to reproduce and impact (confidentiality, integrity, availability, tenant isolation).
- Proof-of-concept or logs, **redacted** — no real student PII, production secrets, or live tokens.
- Your contact for follow-up and whether you want credit in an advisory.

### Response expectations

- **Acknowledgment:** within **3 business days** of a well-formed report.
- **Updates:** periodic status while we investigate and prepare a fix.
- **Disclosure:** coordinated disclosure — we aim to agree on timing before public announcement.

### Safe harbor (good-faith research)

We support good-faith security research that follows this channel, avoids privacy violations and service disruption, and gives us reasonable time to remediate before public disclosure. Research that exfiltrates tenant data, modifies production systems without authorization, or uses social engineering against staff or students is out of scope.

For general hardening guidance, see the bullets above and [docs/security/](docs/security/).
