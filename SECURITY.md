# Security

- **Secrets:** Never commit `.env`, `.env.local`, or any file containing real API keys or passwords. Use `.env.example` with placeholders only. If a secret was ever committed, rotate it immediately and remove the file from history (e.g. `git rm --cached .env.local` and ensure it is in `.gitignore`).
- **CSRF:** All `@csrf_exempt` endpoints are audited in [docs/security/CSRF_EXEMPT_AUDIT.md](docs/security/CSRF_EXEMPT_AUDIT.md). Use token or signature verification instead of exemption where possible.
- **Raw SQL and subprocess:** See [docs/security/raw_sql_audit.md](docs/security/raw_sql_audit.md) and [docs/security/subprocess_safety_audit.md](docs/security/subprocess_safety_audit.md).
