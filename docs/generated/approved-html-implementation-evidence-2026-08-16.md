# Approved HTML implementation evidence

This file maps the four approved browser contracts to shipped code and repeatable checks. A mockup is not considered implemented merely because an HTML file exists.

## Tenant login — 12 upgrades

Production surfaces: `templates/auth/login.html`, `templates/auth/partials/login_immersive_canvas.html`, `static/css/auth-login-canvas.css`, `static/js/rmc-auth-login-immersive.js`, `static/js/rmc-offline-auth-vault.js`, `static/js/rmc-offline-auth-enrollment.js`, and `static/js/rmc-offline-login-unlock.js`.

The twelve bound capabilities are passkeys/trusted devices, returning-user entrance, role-aware methods, trusted-device local mode, school-day information, tenant publishing, governed partner placement, guided recovery, verified-school protection, accessible authentication, public-data-only assistance, and operator-visible health. Regression evidence is in `apps/accounts/tests/test_login_front_door_12_contract.py`.

## Tenant dashboard page-aware color

Production surfaces: `templates/accounts/backend_dashboard.html`, `static/css/backend-dashboard-v2.css`, and `static/css/backend-dashboard-v2-contract.css`.

Tenant brand tokens remain authoritative; status colors retain stable semantic meaning; widget accents follow content purpose; text/badges accompany color; role and page attributes select the correct surface; grids reflow through explicit breakpoints. Regression evidence is in `apps/accounts/tests/test_tenant_dashboard_page_aware_contract.py`.

## Signup wizard and compact review

Production surfaces: `templates/schools/signup_school.html`, `static/css/rmc-signup-balanced-v3.css`, `static/js/rmc-signup-wizard-v4.js`, `apps/schools/signup_views.py`, and `apps/schools/onboarding_recommendations.py`.

The twelve bound capabilities are a five-stage adaptive journey, encrypted device-local draft, country intelligence, institution intelligence, comparable alternatives, honest confidence, contradiction reporting, versioned explainability, signup-to-launch handoff, Tenant 360 visibility, transactional production safety, and privacy-minimized journey measurement. The same canonical recommendation engine serves preview and persistence. A score above 90 is available only when critical evidence is complete, registries resolve, and contradictions are absent; it is explicitly labeled recommendation readiness rather than predictive probability. Regression evidence is in `apps/schools/tests/test_signup_wizard_confidence_contract.py`.

## Release evidence

- `python manage.py test apps.accounts.tests.test_tenant_dashboard_page_aware_contract apps.accounts.tests.test_login_front_door_12_contract apps.schools.tests.test_signup_wizard_confidence_contract --no-input`
- `node --check static/js/rmc-signup-wizard-v4.js`
- `python manage.py check`
- `python scripts/verify_service_worker_version.py`

The broader database-backed onboarding group timed out during test-database setup on the Windows workstation on 2026-08-16. A timeout is not represented as a passing result; CI or a migrated integration environment must execute that group before production promotion.

## Final re-audit corrections

The final promise-to-production audit found and corrected four gaps rather than preserving a false completion claim:

- wizard journey interactions now use their own `signup_journey` event type and migration instead of inflating `signup_started`;
- queued-offline submission recovery emits the delayed queue measurement after connectivity returns;
- storage-restricted browsers receive an explicit graceful-degradation message instead of silent draft failure;
- two login strings with broken character encoding were corrected, and the real-browser verifier now asserts the approved five-stage wizard rather than the retired one-page grid.

“Implemented” means the production route, template, engine, persistence contract, migration, cache release and regression guard exist. Provider- or tenant-dependent activation (for example passkey browser support, tenant sponsor content, or a trusted-device offline grant) remains correctly conditional and is not represented as globally active without its required configuration.
