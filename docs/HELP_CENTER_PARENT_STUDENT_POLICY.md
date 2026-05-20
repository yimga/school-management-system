# Help Center — parent/student surface policy (batch 1354)

Parent and student feedback lanes intentionally expose **less** AI surface than staff:

| Surface | Staff / teacher | Parent / student |
| --- | --- | --- |
| KB browse + FAQ | Yes | Yes |
| Support deflection on submit | Yes | Yes (school feedback forms) |
| KB AI assistant panel on hub | When `enable_ai_help_assistant` | No (by policy) |
| Feature center | Yes | Redirect to role feedback |

Code: `apps/portal/help_governance.py::parent_student_help_surface_policy()`.

Marketing (`runmycampus.com`) remains outside the sovereign help engine by design.
