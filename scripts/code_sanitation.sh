#!/usr/bin/env bash
# Code sanitation gate: non-negotiable before merge/deploy.
# Enforces: no print() in app code, allowlisted CSRF/raw SQL/broad except,
# repo hygiene, tenant settings discipline. Exit 0 only if all pass.
set -euo pipefail

echo "[code_sanitation] Repo hygiene (no conflict markers, backup files)"
python scripts/check_repo_hygiene.py

echo "[code_sanitation] No print() in application code"
python scripts/lint_no_print_in_apps.py

echo "[code_sanitation] Root clutter"
python scripts/check_root_clutter.py

echo "[code_sanitation] Provider secret exposure"
python scripts/lint_secret_exposure.py

echo "[code_sanitation] Bounded context / legacy siteconfig imports"
python scripts/lint_bounded_context_imports.py --strict
python scripts/lint_siteconfig_legacy_imports.py

echo "[code_sanitation] Tenant settings (no new get_solo in tenant-facing)"
python scripts/lint_tenant_settings.py --check-get-solo-only

echo "[code_sanitation] CSRF exempt allowlist"
python scripts/lint_csrf_exempt_usage.py

echo "[code_sanitation] Raw SQL allowlist"
python scripts/lint_raw_sql_usage.py

echo "[code_sanitation] Broad exception baseline"
python scripts/lint_broad_except.py --allowlist scripts/allowlists/broad_except_allowlist.json --strict

echo "[code_sanitation] PASSED"
exit 0
