# SOT wave validation stanza (shell + siteconfig + marketplace)

Canonical **`manage.py test`** modules for PATH II shell / CCC / tenant mutating-policy waves. **Order matters:** `test_wave_stanza_contract` and `verify_doc_plan_density_discipline.py` require this bash block to match `scripts/wave_shell_test_modules.WAVE_SHELL_TEST_MODULES` exactly. Keep aligned with `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` forward-queue rows.

```bash
DJANGO_TEST_DB_FILE=.django_test_dbs/wave1005.sqlite3 python manage.py test \
apps.platform_runtime.tests.test_shell_contract \
apps.platform_runtime.tests.test_marketing_shell \
apps.platform_runtime.tests.test_wave_stanza_contract \
apps.siteconfig.tests.test_ccc_control_center_contract \
apps.siteconfig.tests.test_sync_center_mutating_policy \
apps.siteconfig.tests.test_tag_manager_mutating_policy \
apps.siteconfig.tests.test_impersonation_consent_mutating_policy \
apps.siteconfig.tests.test_clear_preview_mutating_policy \
apps.siteconfig.tests.test_mutating_routes_expansion \
apps.accounts.tests.test_backend_dashboard_shell_render \
apps.marketplace.tests.test_permissions \
apps.marketplace.tests.test_tenant_marketplace_post_security \
apps.schools.tests.test_control_plane_shell_render \
--noinput --keepdb
```

Follow with:

`python scripts/verify_shell_surface_inventory.py`  
`python scripts/verify_phase2_authenticated_shell_conformance.py`  
`python scripts/verify_design_system_phase2.py`  
`python scripts/verify_doc_plan_density_discipline.py`  
`python scripts/verify_sot_pillar_evidence.py`
