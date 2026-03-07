# Release checklist (skeleton)

Use this for each release (tag or deploy to production). Expand steps as needed per wave.

## Pre-release

- [ ] Branch / version: confirm release branch or tag (e.g. `main` or `v1.2.0`).
- [ ] Changelog: update CHANGELOG or release notes with user-visible changes.
- [ ] Baseline: if Wave 0 applies, confirm [baseline_report.md](baseline_report.md) and gates are current.

## Build

- [ ] Migrate: `python manage.py migrate` (or let predeploy run it).
- [ ] Static: `python manage.py collectstatic --noinput` (or equivalent).
- [ ] Tests: run full test suite or at least `scripts/pre_deploy_gate.sh`.

## Deploy

- [ ] Env: confirm DATABASE_URL, SECRET_KEY, REDIS_URL, CELERY_BROKER_URL and optional EMAIL_* in target env.
- [ ] Predeploy: `./scripts/release/render_predeploy.sh` (or platform equivalent) runs and succeeds.
- [ ] Health: after deploy, GET `/health/` returns 200.

## Post-release

- [ ] Smoke: open login, backend dashboard, one critical flow; confirm no 500s.
- [ ] Monitoring: check error rate and logs.
- [ ] Rollback plan: if critical failure, revert to previous deploy and restore DB backup only if needed (see [execution/RELEASE_HARDENING_CHECKLIST.md](execution/RELEASE_HARDENING_CHECKLIST.md)).

---

**Date:** _______________  
**Release / tag:** _______________  
**Checked by:** _______________
