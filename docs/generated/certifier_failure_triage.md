# Certifier failure triage (from `.django_test_dbs/certifier_continue_suite.log`)

Summary: **3 failures**, **7 errors**, **5 skipped** — full suite exit code 1.

## FAIL

### `Phase8RegistryFullCoverageTests.test_registry_matches_phase7_list`

- **Traceback:** `AssertionError: Phase 8 registry mismatch missing=['schools/super_security_hub.html'] extra=[]`
- **Root cause:** `PHASE8_DECLARATIONS` in `apps/dashboard/phase8_declarations.py` did not include `schools/super_security_hub.html` while `PHASE7_DASHBOARD_TEMPLATES` did.
- **Category:** registry drift

### `Phase8RegistryFullCoverageTests.test_no_default_fallback_for_canonical_paths` (`schools/super_security_hub.html`)

- **Traceback:** `AssertionError: True is not false : schools/super_security_hub.html` (`dec["is_default"]`)
- **Root cause:** Missing Phase 8 entry forced default fallback in the Phase 8 templatetag path.
- **Category:** registry drift

### `PlatformAdminBridgeCompletenessTests.test_every_platform_admin_model_has_admin_bridge`

- **Traceback:** Missing `['admin:compliance_auditlog_changelist', 'admin:marketplace_apppermissionscope_changelist']`
- **Root cause:** New models on `platform_admin_site` without matching `PLATFORM_ADMIN_BRIDGES` `admin_url` values.
- **Category:** registry drift

## ERROR

### `EnsureDemoScheduledTaskTests.test_scheduled_demo_refresh_skips_when_slug_unset`

- **Traceback:** `NameError: name 'os' is not defined` at `patch.dict(os.environ, ...)`
- **Category:** stale test expectation

### `EnsureDemoScheduledTaskTests.test_scheduled_demo_refresh_calls_command_when_slug_set`

- **Traceback:** Same `NameError` for `os`.
- **Category:** stale test expectation

### `AIGatewaySmokeTests.test_gateway_response_passes_user_id_to_invoke`

- **Traceback:** `ValidationError: "namespace(id=11, ...)" is not a valid UUID` via `TenantBlueprint.objects.filter(school=school)` from monetization → billing → policies.
- **Root cause:** Smoke test uses `SimpleNamespace` as `request.school`; `_gateway_response` records usage and hits the ORM.
- **Category:** stale test expectation

### `AIGatewaySmokeTests.test_gateway_response_uses_school_pk_when_id_attribute_is_missing`

- **Traceback:** Same UUID validation with `SimpleNamespace(pk='school-pk-only', ...)`.
- **Category:** stale test expectation

### `AppPurchaseIntentTests.test_paid_app_redirects_to_checkout_when_stripe_ready`

- **Traceback:** `ValidationError: {'is_intentionally_free': ['Confirm this is an intentional free listing...']}`
- **Root cause:** `pricing_model` defaulted to FREE while manifest described paid; model clean/save enforces explicit free confirmation or paid model.
- **Category:** product bug (tests/data inconsistent with model rules)

### `AppPurchaseIntentTests.test_paid_app_falls_back_to_plan_when_stripe_missing`

- **Traceback:** Same validation on `MarketplaceApp.objects.create`.
- **Category:** product bug

### `PlatformBillingWebhookTests.test_relay_webhook_checkout_completed_applies_marketplace_addon`

- **Traceback:** Same `is_intentionally_free` validation for catalog app row.
- **Category:** product bug

## Remediation applied (implementation pass)

1. Added `schools/super_security_hub.html` to `PHASE8_DECLARATIONS`.
2. Added `compliance_audit_log` and `app_permission_scopes` to `PLATFORM_ADMIN_BRIDGE_ORDER` and `PLATFORM_ADMIN_BRIDGES`.
3. `import os` in `test_growth_funnel.py`.
4. `@patch("apps.marketplace.monetization.record_usage_meter_increment")` on the two `_gateway_response` smoke tests.
5. `pricing_model=MarketplaceApp.PricingModel.SUBSCRIPTION` on paid-app `MarketplaceApp.objects.create` calls in purchase-intent and billing webhook tests.

## Second full-suite pass (before i18n sync)

After the above code fixes, the first full run (`certifier_final_run.log`) failed **one** test:

- `TenantSettingsLintTests.test_verify_i18n_catalog_fresh_passes` — four new `_("...")` strings from `PLATFORM_ADMIN_BRIDGES` were missing from `locale/en/LC_MESSAGES/django.po`.

**Fix:** `python manage.py sync_i18n_catalog --compile` (updates `.po` / `.mo` for all locales). A subsequent full suite (`certifier_final_run2.log`) completed **OK** (`Ran 2518 tests … OK (skipped=5)`).
