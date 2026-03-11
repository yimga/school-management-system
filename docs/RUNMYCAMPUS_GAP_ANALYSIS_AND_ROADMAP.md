# RunMyCampus — First-in-Class Powerhouse: Gap Analysis & Roadmap

**Doc status: Closed.** Open gap/backlog rows are reconciled with **`docs/PHASE_10_BACKLOG.md`** and **`docs/WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md`**. No open required work on this doc.

**Platform name:** **RunMyCampus**. Domain (when purchased): e.g. **runmycampus.com**; tenant subdomains **school-name.runmycampus.com**.

This document is the **single in-repo reference** for "what we have," "what we're missing," and "what to build next" when briefing Cursor or Codex. The full, detailed gap analysis lives in the Cursor plan file: `first-in-class_powerhouse_gap_analysis_3cd87439.plan.md` (in `.cursor/plans/`).

---

## Current State Summary

The codebase already implements a **strong multi-tenant foundation**:

- Subdomain and path-based tenant resolution (`apps/schools/middleware.py`), PostgreSQL RLS on major tables, `School` as tenant with `subdomain` / `custom_domain`
- Super-admin at `/super/`, provisioning wizard with education profiles, Render deployment (web + Celery + Beat)
- Global search (Ctrl+K), modular feature toggles, grading scales (0–20, 0–100, GPA, letter), competency/clock-hour models
- Offline/PWA stack, early-warning/ML analytics

The gaps below are relative to the **full** "powerhouse" and "global education OS" vision.

---

## Suggested Priority Order (for Cursor/Codex)

1. **High impact, already adjacent:** Rosetta Stone API + optional `normalized_value` on grades; Parent Wallet (balance + pay from wallet); attendance CSV export + bulk PATCH; MoE/country compliance report presets.
2. **Differentiation:** Student Passport/vault (lifetime identity + verified docs); self-service tenant signup; AI narrative feedback (achievement → parent message with approval).
3. **Global readiness:** RTL (`RegionConfig.is_rtl` + `<html dir>`); Michaelmas/Lent/Trinity (or UK) term preset; deeper nested tenancy if selling to ministries/chains.
4. **Education-type expansion:** Certification/badge expiry alerts; employer portal for apprentices; dual transcript (academic vs vocational track).
5. **Polish:** Redis tenant cache; dedicated admin subdomain; marketing landing (RunMyCampus brand); full WhatsApp Business API and push notifications.
6. **2026 trends & predictive powerhouse:** Predictive Engine (pgvector/StudentSignals, nightly risk score, XAI); At-Risk Dashboard (heat map, trend lines, "Why" column); Automated Intervention (Amber/Red levels, Intervention_Logs, Recovery Rate); Executive Dashboard (unified Finance + HR + outcomes); optional blockchain credentials and adaptive learning integration.
7. **Universal Education OS:** Locale-aware middleware; 100+ languages + RTL + UTF-8; regional formatting (date/time/currency); GDPR/FERPA/NDPR in Tenant Setup; polymorphic academic groups and Education DNA JSON; logical CSS (ps-/pe-) for RTL; Rosetta Stone normalized 0–1; CDN/edge for global latency; custom domains per tenant.

---

## Key Technical Prompts (from the plan)

### Predictive Engine (XVIII)

> Design a Predictive Analytics Service (Python/Django + optional FastAPI) using pgvector. Create a **StudentSignals** (or equivalent) table for time-series data (attendance, grades, login gaps). Implement a **Risk Score** algorithm that weights Attendance at 40% and Recent Grade Trends at 60%. Build a Celery task that runs nightly to calculate At-Risk scores per tenant. Output a **RiskFactor**-style object for the teacher dashboard with an **Intervention Suggestion** (e.g. GPT-4–generated).

### At-Risk Dashboard & Intervention (XIX)

> Build a multi-tenant **Intervention Engine**. Background worker checks Risk_Scores nightly. If score > 80, use GPT-4o (or configured LLM) to generate a **Recovery Roadmap** for the student based on failing subjects. Implement an **Action Center** UI where teachers approve or dismiss AI-suggested interventions in one click. Log all intervention emails in **Intervention_Logs** for audit.

### RunMyCampus UI (XX)

> Design RunMyCampus UI with Primary Navy (#1A2B4C) and Teal (#00C4B4). Use Inter as primary typeface. Buttons: rounded-lg (8px). High-contrast **Dark Mode** for teachers grading late. Card-based layout with subtle shadows (shadow-sm) to separate modules (e.g. Attendance, Risk Analytics).

### Education DNA JSON (XXI)

Use a structure like the following in `EducationSystemProfile.config` / RegionConfig for country-specific logic:

```json
{
  "curriculums": {
    "british_igcse": {
      "terms": ["Michaelmas", "Lent", "Trinity"],
      "grading": { "type": "letter", "scale": ["A*", "A", "B", "C", "D", "E", "F", "G"] },
      "weighting": "Summative"
    },
    "west_african_waec": {
      "terms": ["First", "Second", "Third"],
      "grading": { "type": "alphanumeric", "scale": ["A1", "B2", "B3", "C4", "C5", "C6", "D7", "E8", "F9"] },
      "weighting": { "CA": 0.3, "Exam": 0.7 }
    },
    "francophone_bac": {
      "terms": ["Trimestre 1", "Trimestre 2", "Trimestre 3"],
      "grading": { "type": "numeric", "max": 20, "passing": 10 },
      "terminology": { "teacher": "Enseignant", "grade": "Note", "average": "Moyenne" }
    }
  }
}
```

---

## RunMyCampus Brand (XX)

- **Primary (Powerhouse Blue):** `#1A2B4C`
- **Action (Campus Teal):** `#00C4B4`
- **Risk (Warning Amber):** `#F59E0B`
- **Background (System Gray):** `#F8FAFC`
- **Tagline:** "Don't just record your school. Run your campus."
- **Value prop:** "The only Multi-Tenant OS that speaks every education system on Earth."

---

## Multi-Tenancy Strategy (Render)

**Recommended:** Schema-Based Multi-Tenancy (best balance of security and cost). Current codebase uses **Shared Table (RLS)**; consider a path to schema-based (e.g. django-tenants) or keep RLS strict and ensure all tenant queries are covered.

---

## Related Docs

- **Actionable task list:** [RUNMYCAMPUS_ROADMAP_TASKS.md](./RUNMYCAMPUS_ROADMAP_TASKS.md)
- **Full plan:** `.cursor/plans/first-in-class_powerhouse_gap_analysis_3cd87439.plan.md`
