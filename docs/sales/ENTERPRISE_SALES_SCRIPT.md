# Enterprise sales script (30–45 minutes)

**Audience:** Head of school, IT lead, and/or business officer. **Rule:** Use only what exists in the product (CCC, evidence, reports, Studio OS, marketplace). No logos, “everyone uses us,” or case studies you cannot verify.

## Opening (2–3 min)

- Confirm goals: *visibility, auditability, multi-campus control, and safe rollout* (not a generic LMS pitch).
- One sentence: *RunMyCampus is a control-plane and operations layer for the school, with a portal for daily work.*

## Act 1 — Control plane and CCC (7–8 min)

- **Narrative:** *Single place to see how the tenant is wired: domains, email posture, and runtime—before you touch academic data.*
- **Show:** `siteconfig:console_domains_hub` at `/siteconfig/console/` (tenant or manager, both mount `siteconfig` where allowed).
- **Tie to risk:** *Misconfiguration is visible; you are not grepping the database to know if DNS is right.*

## Act 2 — Multi-campus and governance (5–6 min)

- **Narrative:** *District and groups-of-schools use the same **patterns**: tenant isolation, operator flows, and evidence—without claiming a feature the deployment does not have turned on.*
- **Show (if in scope for this tenant):** trust / operator surfaces you actually use, or the **read-only** evidence pages in smoke tests—never invent a district dashboard.

## Act 3 — Reporting and evidence (8–10 min)

- **Narrative:** *Reporting is not only PDFs: scheduled delivery, template catalog, and **evidence** pages that show what is configured and published.*
- **Show:** scheduled delivery hub, report templates or schedules evidence, term publish (per `LAUNCH_SMOKE_TEST.md` and entitlements). State clearly: **email delivery needs workers/cron in their environment**.

## Act 4 — Studio OS and marketplace (5–6 min)

- **Studio / launch** where your deployment exposes it: readiness and operator bundles—not “magic go-live” without their data and DNS.
- **Marketplace / app catalog:** *Optional installs are explicit and scoped*—no fake app revenue.

## Close — pilot (3–5 min)

- Propose: **1–2 campus, time-boxed pilot** (see `ENTERPRISE_PILOT_PLAN.md`) with a written success checklist (academic year, people, at least one report path green).

## Objection handling (short)

| Objection | Response direction |
|----------|-------------------|
| **Internal approval** | Offer a **read-only** walkthrough and a 1–2 page scope sheet: domains, year/term, one report, support channel. No fake ROI. |
| **Change management** | CP-first: fewer admin screens for daily operators; **Advanced/Admin** remains fallback for edge cases. |
| **Budget** | Anchor on **outcomes** (visibility + audit) and **pilot** pricing from your actual plan objects (`PRICING_PACKAGES.md`), not a slide-deck number. |
| **Existing SIS/ERP** | RunMyCampus is the **operating and control layer**; interop and imports exist where you have integrated them—do not claim bidirectional sync you have not implemented. |

## Related

- `ENTERPRISE_PILOT_PLAN.md` · `ENTERPRISE_ROLLOUT_CHECKLIST.md` · `DEMO_SCRIPT.md` · `docs/deployment/LAUNCH_SMOKE_TEST.md`
