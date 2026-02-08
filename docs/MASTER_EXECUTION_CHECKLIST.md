# Master Execution Checklist

This checklist is the execution gate for phased implementation work.
Every phase must meet all checks before the next phase starts.

## Global Rules

1. One commit per phase.
2. Commit message must include the phase id, for example `phase-0`.
3. Run baseline checks after each phase.
4. Do not mix unrelated file changes into a phase commit.
5. If a phase test fails, fix in the same phase before continuing.

## Phase Gate

For each phase:

1. Implement only files in that phase scope.
2. Run `scripts/run_phase_checks.sh`.
3. Run phase-specific tests.
4. Commit with phase id.
5. Record result summary in PR notes or release notes.

## Baseline Checks

- `python manage.py check`
- `python manage.py test apps.siteconfig.tests.test_admin_ui_smoke apps.api.tests.test_dashboard_api_rbac -v 1`

## Notes

- Use Git Bash for local execution commands.
- Keep changes DRY and modular.
- Keep role and policy logic centralized in shared policy layers.
