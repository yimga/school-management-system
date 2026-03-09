# Security Baseline and CI (Wave 7.4)

**Purpose:** Document security and SAST checks to run in CI and how to run them.

## Checks

| Check | Command / tool | When |
|-------|----------------|------|
| Django deploy checks | `python manage.py check --deploy` | CI (or pre-deploy) |
| Dependency vulnerabilities | `pip-audit` or `pip install pip-audit && pip-audit` | CI / weekly |
| Python SAST | `bandit -r apps config -ll` (or exclude tests) | CI / PR |
| Secrets | CI secret scanning (e.g. GitHub secret scanning, gitleaks) | CI |

## Django `check --deploy`

Validates settings for production (e.g. DEBUG, ALLOWED_HOSTS, SECRET_KEY, CSRF, session). Run in CI:

```bash
python manage.py check --deploy
```

## pip-audit

Checks installed packages for known vulnerabilities:

```bash
pip install pip-audit
pip-audit
```

Integrate in CI after `pip install -r requirements*.txt`.

## Bandit

Static analysis for common Python security issues:

```bash
pip install bandit
bandit -r apps config -ll --skip B101,B104
```

- `-ll`: report low and medium severity.
- `--skip B101`: assert_used (tests use assert); B104: hardcoded bind (dev servers). Adjust as needed.

## Recommendation (non-negotiable)

- **Required for CI:** `check --deploy` and `pip-audit`.
- **Required where tooling exists:** Bandit and secret scanning; add to CI.

## References

- [Django deployment checklist](https://docs.djangoproject.com/en/stable/howto/deployment/checklist/)
- RunMyCampus audit plan: Wave 7.4 (docs/RUNMYCAMPUS_AUDIT_PLAN_COMPLETE_NO_BACKLOG.md)
