# Customer success / implementation / onboarding operations

Surfaces and processes for support, implementation, and onboarding (Execution Master Phase 7 §31).

## Existing surfaces

- **Control plane:** Support dashboard (`super:support_dashboard`), Customer Success dashboard (`super:customer_success_dashboard`), Tenant Health, Pulse, Billing. Use these for ops and health visibility.
- **Tenant onboarding:** Provision tenant (create_school_wizard), post-provision flows (welcome email, first-login). Guided onboarding templates exist (e.g. customersuccess/guided_onboarding.html, support_copilot.html).
- **Documentation:** Knowledge base (kb), developer portal/sdk pages. Extend for implementation runbooks and publisher docs (see DEVELOPER_PLATFORM_SDK_ARCHITECTURE).

## Requirements

- **Support:** Triage queue, tenant context, and audit access from control plane; no ad-hoc DB access in production.
- **Implementation:** Checklist or workflow for new tenant go-live; config (blueprint, policy, branding) from platform; no one-off scripts in production without review.
- **Onboarding:** Self-serve or guided flows for first-time admin/teacher/parent; terminology and branding from runtime.
- **Maturity:** Document escalation, rollback, and incident response; link from control plane (e.g. Incidents, Support).

## References

- apps/customersuccess (views_super, guided_onboarding, support_copilot)
- apps/schools/super_urls.py (support_dashboard, customer_success_dashboard)
- docs/architecture/SECURITY_AND_PRODUCTION_MATURITY.md
- docs/architecture/PLATFORM_ENGINES.md
