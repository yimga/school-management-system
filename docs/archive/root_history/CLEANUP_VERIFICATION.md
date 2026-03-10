# Cleanup and Verification Summary

## Completed (no breaking changes)

### 1. Root cleanup
- **Moved to `scripts/dev/`:** `remove_people_auto_nullable_migration.py`, `reverse_admin_home.py`, `search_home_venv.py`, `search_reverse_home_venv.py` (with path fixes so they run from project root).
- **Removed from root:** Those four scripts (originals deleted).
- **Already in scripts:** `clean_people_migrations.py`, `clean_people_migration_artifacts.py`, and dev test/validate scripts were already under `scripts/` or `scripts/dev/`.
- **Updated:** `scripts/dev/README.md` documents the moved scripts.

### 2. Bug fixes (gaps closed)
- **apps/compliance/admin_audit.py:** Added missing `import csv` and `from django.http import HttpResponse` (used in `export_to_csv`).
- **apps/compliance/management_commands.py:** Fixed `generate_audit_trail` to use `Count` from `django.db.models` instead of undefined `models`; removed redundant `models` import from `generate_access_control`.
- **apps/evals/models.py:** Added `from django.utils import timezone` (used in `mark_reviewed` / `mark_bypassed`).
- **apps/finance/admin.py:** Added `from datetime import timedelta` (used in `resend_selected_reminders`).
- **apps/finance/services.py:** Added `from datetime import date` and `FeeInstallment` to `.models` imports (`get_month_name`, `copy_fee_plan_to_year`).
- **apps/finance/signals.py:** Implemented `_deactivate_reminders_for_student` (was called but undefined).
- **apps/finance/tasks.py:** Set `dry_run = False` in `process_payment_receipt_upload_task` where `dry_run` was used but not defined.
- **apps/portal/services.py:** Added `TYPE_CHECKING` import of `PendingGuardianInvite` for type hint in `link_guardian_via_invite`.

### 3. Unused-import / light sanitization
- **apps/academics/services_certification.py:** Removed unused `List` from typing import.
- **apps/accounts/activity_helper.py:** Removed unused `ContentType` import.
- **apps/accounts/context_processors.py:** Removed unused `datetime` import.
- **apps/api/consumers.py:** Removed unused `database_sync_to_async` import (channels).

### 4. App-by-app verification
- **Django check:** `python manage.py check` — no issues.
- **URL resolution:** All namespaces resolve at least one named URL:
  - accounts, portal, finance, evals, academics, reports, analytics, siteconfig, payroll, compliance, communication, requests, api, kb, super.
- **Imports:** `apps.accounts.views`, `apps.portal.views`, `apps.finance.views` import successfully (Django shell).
- **Tests:** Ran `apps.accounts.tests.test_smoke_urls`, `apps.compliance.tests.test_compliance`, `apps.finance.tests.test_split_allocation`, `apps.portal.tests.test_url_aliases` (35 tests) and `apps.evals.tests.test_grading_scale_map`, `apps.reports.tests.test_localization`, `apps.people.test_people_management` (42 tests) — all passed.

## What was not changed (per plan)

- **apps/*/apps.py** signal imports (e.g. `apps.academics.signals`) — kept for side-effect registration.
- **balance_amount** (Invoice) — still in use; not removed.
- **Student** alias in `apps.people.models` — kept for backwards compatibility.
- **BI/reports models**, **Channels/ASGI fallback**, **NotImplementedError** stubs — unchanged.

## Remaining (optional next pass)

- **pyflakes** still reports many unused imports and some unused variables across the codebase. These can be cleaned in a follow-up, file-by-file, to avoid touching Django entrypoints (views, URLconfs, management commands, signals).
- **Vulture** (or similar) can be run for unused functions/classes after manual review of false positives.
