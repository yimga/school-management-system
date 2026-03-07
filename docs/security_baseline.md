# Security baseline (C4)

Generated/updated by `scripts/security_ci.sh`. Run that script in CI or before release.

## Checks

| Check | Description |
|-------|-------------|
| pip-audit | Dependency vulnerabilities |
| Bandit | Python static security (apps/, config/) |
| Django check --deploy | Production settings, security middleware |
| Semgrep | Optional; Django/auth rules |

## How to run

From repo root:

```bash
# Install tools (optional)
pip install pip-audit bandit

# Run full security CI (updates this file)
bash scripts/security_ci.sh

# Or run individually
pip-audit
bandit -r apps/ config/ -ll --skip B101
python manage.py check --deploy
```

## Findings and patches

- **pip-audit:** Fix reported vulnerabilities with `pip-audit --fix` or version bumps.
- **Bandit:** Address high/medium issues; B101 (assert_used) is often skipped in tests.
- **Django check --deploy:** Resolve warnings (e.g. DEBUG=0, SECURE_* in production).
- **CSP:** Enable `django-csp` or set Content-Security-Policy headers; use report-only first.

## SAST / DAST (Section 25.5)

- **SAST:** Bandit (Python) and Semgrep (optional) above. Run in CI; fix high/medium findings.
- **DAST:** Optional dynamic scan (e.g. OWASP ZAP, `zap-cli` against a staging URL). Document in CI or runbooks; not required for every commit.

See also: `docs/security-checklist.md`, `SECURITY_IMPLEMENTATION_GUIDE.md`, `docs/architecture/section_25_observability_sre.md`.
