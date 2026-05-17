# Per-verb live analytics tracking plan

**Purpose:** The five marketing verbs (Run / Teach / Pay / Communicate / Grow)
are the primary segmentation of the funnel. "Per-verb live analytics" was
listed as an externally-bound item in the 12-pillar audit — it cannot be
gated by CI because it requires production traffic flowing through a
configured analytics provider.

This document is the **tracking plan**: the events the operator must
configure in the analytics provider so the data exists when traffic arrives.
It is honest scaffolding, not a CI gate.

---

## Event taxonomy (one row per verb × stage)

| Verb | Surface | Event name | Trigger | Required properties |
|---|---|---|---|---|
| Run | `/solutions/run/` | `verb_view` | Page load | `verb=run`, `referrer`, `utm_source`, `tenant_subdomain` (if any) |
| Run | `/solutions/run/` | `verb_cta_click` | Click on `[data-verb-cta]` | `verb=run`, `cta_label`, `cta_position` |
| Run | `/solutions/run/` | `verb_demo_request` | Submit demo form | `verb=run`, `school_type`, `student_count` |
| Teach | `/solutions/teach/` | `verb_view` | Page load | same as Run |
| Teach | `/solutions/teach/` | `verb_cta_click` | Click on `[data-verb-cta]` | same |
| Teach | `/solutions/teach/` | `verb_demo_request` | Submit demo form | same |
| Pay | `/solutions/pay/` | `verb_view` | Page load | same |
| Pay | `/solutions/pay/` | `verb_cta_click` | Click on `[data-verb-cta]` | same |
| Pay | `/solutions/pay/` | `verb_demo_request` | Submit demo form | same |
| Communicate | `/solutions/communicate/` | `verb_view` | Page load | same |
| Communicate | `/solutions/communicate/` | `verb_cta_click` | Click on `[data-verb-cta]` | same |
| Communicate | `/solutions/communicate/` | `verb_demo_request` | Submit demo form | same |
| Grow | `/solutions/grow/` | `verb_view` | Page load | same |
| Grow | `/solutions/grow/` | `verb_cta_click` | Click on `[data-verb-cta]` | same |
| Grow | `/solutions/grow/` | `verb_demo_request` | Submit demo form | same |
| (cross-verb) | nav bar | `verb_nav_select` | Click on a verb in the bridge chip | `from_verb`, `to_verb`, `page_path` |
| (cross-verb) | any | `verb_bridge_chip_view` | "was: Platform" chip enters viewport | `verb`, `page_path` |

---

## Provider-agnostic implementation contract

The code emits events through a single shim. Wherever the operator's
analytics provider lives (GA4 / Plausible / PostHog / Amplitude), the shim
is the boundary:

```html
<script nonce="{{ csp_nonce }}">
  window.rmcTrack = window.rmcTrack || function (name, props) {
    // Provider-specific bind goes HERE — set by the operator at
    // base-template level. The default is a noop so missing-provider
    // is fail-quiet.
  };
</script>
```

Template hooks already in place:

- `templates/marketing/_verb_section.html` emits `data-verb="<slug>"` on
  the wrapping section so the analytics provider's auto-track can scope
  events.
- `templates/marketing/_marketing_demo_form.html` carries
  `data-verb-form="<slug>"` when invoked from a verb route — the form
  submit handler reads it to populate the `verb` property.
- `templates/marketing/partials/_nav_bridge_chip.html` carries
  `[data-verb-nav]` on each clickable verb chip.

The operator configures the analytics provider once; the events flow
without further code changes per verb.

---

## Funnel KPIs (the actual question)

Once events are flowing, these are the questions the data must answer:

1. **Verb view → CTA click rate** per verb (which verb's pitch resonates).
2. **Verb CTA → demo request conversion** per verb (which verb's offer
   converts).
3. **Cross-verb bridge usage** (do visitors who land on `/solutions/run/`
   click into `/solutions/teach/` before converting? evidence that the
   bridge chip is doing work).
4. **Demo request → trial start** by verb of entry (the canonical funnel
   bottom).
5. **Trial start → first invoice** by verb of entry (P5 FinTech
   alignment).

KPI 1-3 live in the marketing analytics provider. KPI 4-5 cross the
trial / billing boundary and require joining marketing-side `verb`
attribution to the tenant's `School.created_at` and
`finance_invoice.first_paid_at` server-side. The join key is the demo
form's email + the operator's CRM merge logic — not CI-gateable.

---

## What this document does NOT replace

- **Analytics provider configuration** — the operator must set up the
  provider account, dashboards, and KPI definitions. This document tells
  them WHICH events to expect.
- **Marketing acquisition strategy** — channel mix, paid spend, organic
  SEO — not in scope here.
- **A/B testing infrastructure** — events emitted here are observational;
  any verb-targeted experiment goes through `apps/siteconfig/feature
  flags` and its own tracking.

---

## Honest framing

"Per-verb live analytics" was listed in the externally-bound bucket of
the 12-pillar audit because it cannot be code-closed: no traffic, no
data. What CAN be code-closed is **the tracking plan**: declaring
exactly which events the analytics provider should expect, where they
fire, and what properties they carry. That's this document.

When the operator wires up the provider (and traffic arrives), the data
flows by construction. Until then, the events fire into the noop shim
and nothing breaks.
