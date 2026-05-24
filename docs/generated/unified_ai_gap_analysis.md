# Unified AI — gap analysis (2026-05-22, gear 2)

**Verdict:** Lane 1 (repo) **Phase A + B + C + Gear 2 complete** per `scripts/verify_unified_ai_assistant.py` (49 checks) → **UNIFIED_AI_ASSISTANT_PASS**; Lane 2 contract → **UNIFIED_AI_LANE2_READINESS_PASS**; GEOS matrix composite gate → **GEOS_99_COMPOSITE_PASS** (100%) after batch **1476** internal-pilot evidence + register sync.

## Shipped in-repo (no duplicate stacks)

| Strategy item | Status | Proof |
| --- | --- | --- |
| One-brain context (Phase A) | DONE | `apps/portal/ai_surface_context.py` |
| Surface intent router (Gear 2) | DONE | `apps/portal/ai_intent_router.py` |
| RunMyCampus Guide hub (Gear 2) | DONE | `/portal/guide/`, `runmycampus_guide.html` |
| Lesson plan outline draft (Gear 2) | DONE | `services/teacher_lesson_plan.py`, `ai_draft_lesson_outline` |
| Operator copilot rail | DONE | `apps/observability/ai_copilot_service.py` |
| KB zero-result loop | DONE | `help_content_gaps.maybe_auto_draft_from_content_gap` |
| Support triage hooks | DONE | `support_ticket_hooks` |
| Migration intake AI | DONE | `intake_ai_ask` |
| Forum↔KB | DONE (1359) | `help_forum_kb_bridge.py` |
| Onboarding/offboarding playbook UI | DONE (1394) | `workflow_playbook_assistant.html` + APIs |
| Proactive tenant suggestions | DONE (1394+1396) | `tenant_proactive_suggestions.py` + guide CTA |
| Attendance / studio inline assistant | DONE (1394) | `help_proactive_inline.py` |
| Teacher/parent education pack UI | DONE (1395+1396) | packs + lesson outline UI |
| Tenant-authored KB | DONE (existing) | `kb_article_submit` + HITL |
| Partner doc assistant surface | DONE (1395) | `partner_documentation_assistant.html` |
| Product MCP scaffold | DONE (1395+1396) | 6 tools incl. lesson + guide |
| AI nutrition / transparency label | DONE (1395) | `partials/ai_nutrition_label.html` |
| Command palette AI surfaces | DONE (Gear 2) | `command_bar_registry.py` |

## Lane 2 — external (hooks only; enable when ready)

| Item | Env / action | Code hook |
| --- | --- | --- |
| Cloud generative AI | `AI_GATEWAY_ENABLED=1`, `LITELLM_*` | `docs/AI_DEPLOYMENT_POSTURE.md` |
| Support auto-triage | `SUPPORT_AI_AUTO_TRIAGE_ON_CREATE=1` | `support_ticket_hooks` |
| KB auto-draft from gaps | `HELP_ZERO_RESULT_AUTO_DRAFT_KB=1` | `help_content_gaps` |
| Product MCP clients | `RMC_PRODUCT_MCP_ENABLED=1` | `/api/ai/mcp/*` |
| WCAG axe on help/AI | `GEOS_A11Y_E2E=1` + live Django | `scripts/run_geos_ai_a11y_lane2.sh` |
| Formal WCAG auditor | External vendor | Not in repo |

## Honest residuals (product, not blockers for repo-done)

- Parent lane stays non-generative per `help_governance` (by design).
- Lesson outline and playbooks need live gateway for cloud-quality text; rules/Ollama tier still works offline.
- MCP invoke uses session auth today — service accounts are a future hardening slice.

## Verification commands

```bash
npm run verify:geos-ai-unified
python scripts/verify_greatest_education_os_matrix.py --write
```
