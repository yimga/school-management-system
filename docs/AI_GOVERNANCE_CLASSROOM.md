# AI governance — classroom and family lanes

Canonical policy for who may use RunMyCampus AI assistants on tenant hosts.

## Role matrix

| Role | KB “Ask with AI” panel | Floating AI copilot (assist dock) | Feature center | Support deflection on submit |
| --- | --- | --- | --- | --- |
| Staff / admin | Yes (tenant flag) | Yes | Yes | Yes |
| Teacher | Yes | Yes | Yes | Yes |
| Parent | No (browse KB + contact) | No | Redirect → Help Center | Yes |
| Student | No | No | Redirect → Help Center | Yes |

Implementation: `apps/portal/help_governance.py` and context processor `help_ai_governance`.

Tenant override: `SiteSettings.backend_feature_flags.enable_ai_help_assistant` (default on).

## Education AI (staff)

| Capability | Entitlement | Surfaces |
| --- | --- | --- |
| Parent message drafts | `AI_TEACHER_COMMS` | Direct compose, command bar |
| Report-card comment drafts | `AI_REPORT_CARD` | Draft API + inline partial |
| Lesson plan outline drafts | `AI_TEACHER_COMMS` | Education pack, MCP `lesson_plan_outline` |
| At-risk explanation | `AI_RISK_EXPLAIN` | Nightly batch + risk drivers “Regenerate” |

All calls route through `services.ai_helpers` / `services.ai_gateway` with school scope and PII redaction.

## Data minimization (FERPA-aligned)

- Student names in prompts use display names only inside tenant-scoped gateway metadata.
- Support AI never logs raw ticket bodies in metric labels.
- Parent/student lanes do not receive floating copilot or KB generative panel by default.
- Human review required before sending parent messages or publishing KB from HITL queue.

## Operator vs tenant

- **Manager host:** Studio copilot rail + AI Center (`settings.manage`).
- **Tenant host:** Help Center KB assistant + assist-dock copilot for staff/teacher; no duplicate FAB stacks.

## Education & partner surfaces (batches 1395–1396)

| Surface | Route | Generative AI |
| --- | --- | --- |
| RunMyCampus Guide | `portal:runmycampus_guide` | Directory only (links to grounded surfaces) |
| Teacher education pack | `portal:education_pack_teacher` | Draft APIs only (HITL) |
| Parent learning pack | `portal:education_pack_parent` | Browse-only (no copilot panel) |
| Partner doc assistant | `portal:partner_documentation_assistant` | `api:ai-interop-assistant` |
| Product MCP (optional) | `api:ai-mcp-list-tools` | Flag `RMC_PRODUCT_MCP_ENABLED` |

Surface intent keys (`apps/portal/ai_intent_router.py`) are attached to every `build_ai_surface_context` call for gateway metadata consistency.

## Related docs

- [HELP_CENTER_PARENT_STUDENT_POLICY.md](HELP_CENTER_PARENT_STUDENT_POLICY.md)
- [AI_DEPLOYMENT_POSTURE.md](AI_DEPLOYMENT_POSTURE.md)
- [AI_SURFACES_FAQ.md](AI_SURFACES_FAQ.md)
- [generated/unified_ai_gap_analysis.md](generated/unified_ai_gap_analysis.md)
