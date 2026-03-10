# Security

- **Secrets:** Never commit `.env`, `.env.local`, or any file containing real API keys or passwords. Use `.env.example` with placeholders only. **If any API key or secret was ever committed (e.g. in `.env.local`), rotate it immediately** — revoke and issue new keys in the provider dashboard; update local and CI secrets; document rotation in runbooks. Remove the file from history (e.g. `git rm --cached .env.local`) and ensure it is in `.gitignore`. See [.env.example](.env.example) for expected placeholders.
- **CI guardrail:** The repo must not contain committed `.env` or `.env.local`; CI or pre-commit checks fail if these files are present (see [scripts/check_no_committed_env.sh](scripts/check_no_committed_env.sh)).
- **CSRF:** All `@csrf_exempt` endpoints are audited in [docs/security/CSRF_EXEMPT_AUDIT.md](docs/security/CSRF_EXEMPT_AUDIT.md). Use token or signature verification instead of exemption where possible.
- **Raw SQL and subprocess:** See [docs/security/raw_sql_audit.md](docs/security/raw_sql_audit.md) and [docs/security/subprocess_safety_audit.md](docs/security/subprocess_safety_audit.md).
- **AllowAny APIs:** Public endpoints are audited in [docs/security/ALLOWANY_API_AUDIT.md](docs/security/ALLOWANY_API_AUDIT.md). AllowAny views must be rate-limited and return minimal data.
