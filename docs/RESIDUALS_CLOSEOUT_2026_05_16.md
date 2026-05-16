# Master-prompt residuals closeout — 2026-05-16 (v2.86)

The 4 items I had previously said were "not code-scope" turn out to have
real internal scaffolding. This wave ships all four.

## 1. Emotional UX confidence — heuristic scanner

Most "bad emotional UX" failure modes are empirically detectable. NEW
`scripts/audit_emotional_ux_signals.py` flags:

- **Hostile error copy** (`Error.`, `Invalid input`, `Failed.` with no
  nearby next-step verb)
- **Naked exception leakage** (`{{ exception }}`, `{{ traceback }}` etc.)
- **Alarming numbers without context** (red number alone, no descriptor)
- **Hostile empty states** ("No records." with no next-action affordance)
- **Imperative tone without reason** ("You must X" with no "because Y")

Output: `docs/generated/emotional_ux_audit.json` with severity +
suggested-fix per finding. Mark intentional sites with
`<!-- ux-allow: <reason> -->`. Baseline: 5 (current floor; all warning/info
severity, no criticals). Ratchet-only — every PR that adds a regression
fails the new `emotional-ux-signals` CI job.

## 2. Feedback loop live usage — consumption dashboard

NEW operator surface at `/feedback-loop/` (`manager_feedback_loop`) that
consumes existing telemetry (`FrictionEvent` rollups, `FeedbackSubmission`,
`AuditLog` rows for `portal.AICopilot`). 7d + 30d aggregates, top-10 stuck
views, feedback by category/severity, AI interaction count.

Empty state is honest signal: when no users have generated friction or
feedback yet, the page says so explicitly. The dashboard "lights up" as
real users start interacting.

Companion `python manage.py summarize_feedback_loop --days N` for shell
inspection / Slack digest wiring.

## 3. Studio OS per-mode polish — Launch, Experience, Automation

Each mode wrapped in `<section data-page-archetype="studio-os-<mode>"
aria-labelledby="studio-<mode>-hero">` with a shared `_mode_hero.html`
partial that gives each mode consistent grammar (mode label + one-line
purpose + primary action + optional secondary action + optional health
pill).

Same polish pattern as Control (v2.64.1) and Output (v2.70). Brings the
3 remaining modes up to the same archetype, accessibility, and
information-hierarchy bar.

## 4. External PSP / SOC2 / pilots — internal scaffolding

Lane-2 work is external, but internal preparedness is code-scope. NEW
3-register SOT system + single operator surface that consumes all three:

### PSP adapter registry (`apps/billing/psp_adapter_registry.py`)
- 7 PSPs: Stripe (in_progress), Paystack, Flutterwave, M-Pesa, Adyen,
  PayPal, Razorpay (planned).
- Per-row: capabilities, settlement currencies, status, optional
  proof_model + proof_route_name.
- Test: `live` rows must have a resolvable proof.

### SOC2 control register (`apps/compliance/soc2_control_register.py`)
- 14 TSC common-controls (CC6.1, CC6.2, CC6.6, CC6.7, CC6.8, CC7.1, CC7.2,
  CC7.3, CC8.1, PI1.4, C1.1, C1.2, P3.2, P5.1).
- Each control mapped to in-platform evidence: route, model, or scanner.
- Test: `implemented` rows must have at least one evidence source, and
  if it's a route it must resolve.

### Pilot tracker (`apps/sales/pilot_register.py`)
- 4 tracked pilots: gilead-tech-high (live), 3 reference deployments
  (prospect).
- Per-row: stage, region, institution type, blocking features +
  blocking PSPs, next gate, target quarter.
- Test: every blocking_psps / blocking_features slug references a real
  row in the corresponding register (no dangling references).

### Single consumer surface
`/lane2-readiness/` (`manager_lane2_readiness`) renders all three
registers in one place. Status counts at the top of each section.
Wired into the manager sidebar.

## CI gates after this wave

12 architectural gates green:
- All 11 previous gates unchanged
- NEW `emotional-ux-signals` baseline: 5 (ratchet-only)

Template render-safety / inline-style-off-token / undefined-CSS all
remain at 0 findings.

## Files changed

```
NEW  scripts/audit_emotional_ux_signals.py
NEW  var/security-audit-baseline-emotional-ux.json
NEW  config/manager_feedback_loop.py
NEW  config/manager_lane2_readiness.py
NEW  templates/schools/manager_feedback_loop.html
NEW  templates/schools/manager_lane2_readiness.html
NEW  apps/observability/management/commands/summarize_feedback_loop.py
NEW  apps/billing/psp_adapter_registry.py
NEW  apps/compliance/soc2_control_register.py
NEW  apps/sales/pilot_register.py
NEW  apps/schools/tests/test_lane2_readiness_registers.py
NEW  templates/studio_os/partials/_mode_hero.html
NEW  docs/RESIDUALS_CLOSEOUT_2026_05_16.md         (this file)

MOD  .github/workflows/architectural-boundaries.yml  (+emotional-ux-signals job)
MOD  config/manager_urls.py                          (+2 routes)
MOD  apps/schools/control_plane_nav.py               (+2 nav entries)
MOD  templates/studio_os/modes/launch.html           (mode-hero wrapper)
MOD  templates/studio_os/modes/experience.html       (mode-hero wrapper)
MOD  templates/studio_os/modes/automation.html       (mode-hero wrapper)
MOD  static/js/service-worker.js                     (CACHE_VERSION bump)
```

`sms-v2.86.0`.
