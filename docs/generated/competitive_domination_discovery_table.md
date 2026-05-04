# Competitive domination — discovery (repo-controlled areas)

| Area | Current repo support | Missing gap (before this slice) | User pain solved | Files touched (representative) | Risk | Test | Verifier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A Trust center | trust-center CMS pages | Dedicated `/trust/` template + honesty blockers | Procurement / parent trust | `competitive_marketing_views.py`, `trust_center.html`, `public_urls.py`, `urls.py` | Marketing drift | `test_marketing_trust_center` | `validate_marketing_urls --smoke` |
| B Compliance evidence | audits, evidence commands | Still need curated *institutional* packet workflow | Audit fatigue | (future) evidence exports | Low | existing gates | `verify_compliance_evidence` |
| C Security evidence | route/security audits | Packet = sales-led, not fake certs | RFP delays | trust center CTA | Low | audits | `audit_security_surface` |
| D Pilot evidence | scorecard JSON | Operator dashboard + schema | No honest pilot story | `pilot_evidence.py`, `pilot_readiness_scorecard.json`, template | Redaction miss | `test_pilot_evidence` | — |
| E Implementation factory | scattered setup | Command center checklist | Slow TTV | `implementation_checklist.py`, `views_operational_center.py`, template | Wrong reverses | `test_implementation_command_center` | — |
| F Support playbooks | ad hoc | JSON registry + center | Repeat tickets | `support_playbooks.json`, template | Stale copy | `test_support_playbook_center` | — |
| G Customer success | playbooks overlap | Same registry; CS copy blocks | Inconsistent guidance | JSON + template | Low | support tests | — |
| H Pricing clarity | generic pricing page | Package registry + caveat | Wrong SKU choice | `pricing_packages.json`, `pricing_packages.html` | Overclaim | `test_marketing_pricing_packages` | marketing smoke |
| I School storytelling | many marketing slugs | Competitive story routes | Weak differentiation | `competitive_story.html`, `public_urls.py` | Broken CTAs | marketing tests | `validate_marketing_urls` |
| J Enrollment comms | portal/email apps | Not expanded in this slice | Parent confusion | — | — | — | — |
| K Developer onboarding | developer hub exists | Gallery links to outcomes/designer | Partner trust | `workflow_template_gallery.py` | Staff-only | `test_workflow_template_gallery` | — |
| L Workflow templates | playbooks internal | Public gallery surface | “Does automation exist?” | `automation/urls.py`, template | — | automation test | — |
| M Admin adoption | funnel metrics | Event-log honest metrics | Unknown usage | `operator_adoption_metrics.py`, lifecycle template | False positives | `test_operator_adoption_metrics` | — |
| N Feedback / defects | issues informal | JSON defect loop | Lost defects | `pilot_defect_closure.py`, registry | Process | `test_pilot_defect_closure_loop` | — |
| O First 100 schools | sales pipeline | `/sales/first-100/` tracker | Founder visibility | `sales/views.py`, template | Manager URL | `test_first_100_schools_dashboard` | — |

Full-market category-defining status remains blocked until listed external dependencies (live PSP merchant onboarding, production keys, webhooks, settlement, live corridor transactions, etc.) are verified live or formally scoped out.
