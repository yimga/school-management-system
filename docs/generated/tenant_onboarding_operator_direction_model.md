# Tenant Onboarding Operator Direction Model

Generated: 2026-05-21T00:33:02+00:00


```json
{
  "generated_at": "2026-05-21T00:33:02+00:00",
  "operator_roles": [
    "platform_implementation_operator",
    "school_owner",
    "tenant_admin",
    "registrar",
    "bursar",
    "academic_lead",
    "teacher_lead",
    "support_success_operator"
  ],
  "launch_lanes": [
    {
      "key": "start_setup",
      "label": "Start setup",
      "purpose": "Open the activation checklist and first incomplete step.",
      "url_name": "siteconfig:onboarding",
      "owner": "tenant_admin",
      "required": true
    },
    {
      "key": "essentials",
      "label": "Complete essentials",
      "purpose": "Academic year, people, classes, and guided configuration.",
      "url_name": "siteconfig:onboarding",
      "owner": "tenant_admin",
      "required": true
    },
    {
      "key": "import_data",
      "label": "Import data",
      "purpose": "Migration Cloud connectors, CSV import, and quarantine review.",
      "url_name": "school_setup_imports",
      "owner": "registrar",
      "required": false
    },
    {
      "key": "operations",
      "label": "Configure operations",
      "purpose": "Billing, workflows, offline sync, and security surfaces.",
      "url_name": "school_money",
      "owner": "bursar",
      "required": false
    },
    {
      "key": "readiness",
      "label": "Review readiness",
      "purpose": "Health score, blockers, and launch checklist.",
      "url_name": "school_studio",
      "owner": "school_owner",
      "required": true
    },
    {
      "key": "launch",
      "label": "Launch school",
      "purpose": "Execute guided launch when checklist and health allow.",
      "url_name": "siteconfig:guided_onboarding",
      "owner": "school_owner",
      "required": true
    }
  ],
  "steps": [
    {
      "step_key": "academic_year",
      "name": "Academic year",
      "owner": "academic_lead",
      "required": true,
      "prerequisites": [],
      "blocker_if": "no_active_academic_year",
      "completion": "data_driven_or_operator_mark",
      "next_action_hint": "Add at least one academic year before importing classes.",
      "help_url_name": "siteconfig:onboarding_step",
      "ai_guidance": "route_aware_setup_step",
      "proof": "apps.platform_runtime.onboarding"
    },
    {
      "step_key": "students",
      "name": "Students",
      "owner": "registrar",
      "required": true,
      "prerequisites": [
        "academic_year"
      ],
      "blocker_if": "zero_active_students",
      "completion": "data_driven",
      "next_action_hint": "Import or enroll students from the student roster.",
      "help_url_name": "accounts:backend_student_list",
      "ai_guidance": "route_aware_setup_step",
      "proof": "apps.platform_runtime.onboarding"
    },
    {
      "step_key": "teachers",
      "name": "Teachers / staff",
      "owner": "tenant_admin",
      "required": true,
      "prerequisites": [],
      "blocker_if": "zero_teachers",
      "completion": "data_driven",
      "next_action_hint": "Invite teaching staff before assigning classes.",
      "help_url_name": "accounts:backend_teacher_list",
      "ai_guidance": "route_aware_setup_step",
      "proof": "apps.platform_runtime.onboarding"
    },
    {
      "step_key": "guided_configuration",
      "name": "Tenant settings",
      "owner": "tenant_admin",
      "required": true,
      "prerequisites": [
        "academic_year"
      ],
      "blocker_if": "site_settings_incomplete",
      "completion": "data_driven",
      "next_action_hint": "Finish branding and runtime settings in Configure.",
      "help_url_name": "siteconfig:console_domains_hub",
      "ai_guidance": "missing_context_fallback",
      "proof": "apps.platform_runtime.onboarding"
    },
    {
      "step_key": "plan_entitlements",
      "name": "Plan review",
      "owner": "bursar",
      "required": false,
      "prerequisites": [],
      "blocker_if": "no_plan_assigned",
      "completion": "data_driven",
      "next_action_hint": "Review plan and billing readiness.",
      "help_url_name": "siteconfig:billing_plan_readonly",
      "ai_guidance": "billing_usage_explain",
      "proof": "apps.platform_runtime.onboarding"
    }
  ]
}
```
