# Test module canonical map

Prompts, documentation, and logs sometimes reference older **`manage.py test`** module paths. This table is the **contract**: the **actual module** column must exist in the repository.

| Prompt / legacy name | Actual module | Reason | Replacement command |
| --- | --- | --- | --- |
| `test_school_health` | `apps.platform_runtime.tests.test_customer_health` | Health scoring module naming | `python manage.py test apps.platform_runtime.tests.test_customer_health` |
| `test_billing_lifecycle` | `apps.billing.tests.test_platform_billing` | Platform billing coverage path | `python manage.py test apps.billing.tests.test_platform_billing` |
| `test_trial_signup` | `apps.schools.tests.test_sot_0155_signup_region_deep_link` | Signup region deep link slice | `python manage.py test apps.schools.tests.test_sot_0155_signup_region_deep_link` |

Scan sources: `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`, `docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md` (see `scripts/verify_test_module_contract.py`).
