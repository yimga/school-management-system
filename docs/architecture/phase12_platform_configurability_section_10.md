# Phase 12 — Platform-Wide Configurability (Section 10)

Configurable items per module: where they are driven by policy, blueprint, or settings. Checklist 10.1–10.8.

---

## 10.1 — Admissions

| Configurable item | Where configured | Status |
|-------------------|------------------|--------|
| Admission number format | TenantAdmissionNumberPolicy (strategy, template, pattern, school_code, seq_width, reset_frequency); policy slice `admissions`; identifier_policy_service | Done |
| Required documents | Policy/school.settings["admissions"] or form_policy; document_required in form schema | Partial (form_policy) |
| Review stages, interview, seat hold | Policy/settings; workflow if present | Scoped |
| Payment timing | Policy/finance slice | Scoped |
| Approval chain | workflow_resolver; approval roles from policy | Done (approval workflow) |
| Re-enrollment | Policy/settings | Scoped |

**Ref:** policy_injection.md § Admissions; section_22; identifier_policy_service.

---

## 10.2 — Academics

| Configurable item | Where configured | Status |
|-------------------|------------------|--------|
| Grade scale | policy["grading_scale"]; GradingScaleConfig; get_grading_scale_choices_for_school(school) | Done |
| Term structure | Policy/region; academic year, term models | Partial |
| Class naming | Terminology/policy | Partial |
| Report card style | policy["report_labels"]; ReportCardStyle; get_report_template_family_for_school | Done |
| GPA, rubric, promotion rules | Policy/settings; evals rubric | Partial |
| Exam structure | Policy/settings | Scoped |

**Ref:** policy_injection.md § Gradebook/reports; siteconfig.get_grading_scale_choices_for_school; reports.services.

---

## 10.3 — Finance

| Configurable item | Where configured | Status |
|-------------------|------------------|--------|
| Invoice timing | policy["finance"]["invoice_timing"]; resolver defaults + bundle merge | Done (policy slice) |
| Fee templates, discounts, scholarship | policy["finance"]["fee_templates"]; Finance models | Partial |
| Late fee rules, collection flows, write-off | policy["finance"]["late_fee_rules"]; policy/settings | Partial |
| Payment providers | policy["payment_gateways"]; finance.gateways.registry | Done |

**Ref:** policy_injection.md (finance slice, payment_gateways); apps.policies.resolver (finance defaults); finance.gateways.

---

## 10.4 — Attendance

| Configurable item | Where configured | Status |
|-------------------|------------------|--------|
| Statuses | policy["attendance"]["statuses"]; resolver defaults + bundle merge | Done (policy slice) |
| Lateness rules, absence escalation | policy["attendance"]["lateness_rules"], ["escalation"] | Partial |
| Homeroom/class model, who marks | Policy/settings; role from policy | Partial |
| Parent notification timing | Policy/comms | Scoped |

**Ref:** policy_injection.md (attendance slice); apps.policies.resolver (attendance defaults); no hardcoded country (24.1).

---

## 10.5 — Communication

| Configurable item | Where configured | Status |
|-------------------|------------------|--------|
| Channels, fallback order | policy["communication"]["channel_order"], ["fallback_order"]; section_28 | Done (policy slice) |
| Opt-in/out, digest vs instant | Settings/policy | Scoped |
| Message approval, staff/parent segmentation | Settings/policy | Scoped |
| School/quiet hours | Settings/policy | Scoped |

**Ref:** policy_injection.md (communication slice); apps.policies.resolver (communication defaults); section_28_data_architecture_and_provisioning.md (28.8 MessagingProvider).

---

## 10.6 — HR/Staff

| Configurable item | Where configured | Status |
|-------------------|------------------|--------|
| Recruitment, onboarding, certification tracking | Settings/policy; people/HR models | Scoped |
| Review cycles, leave approvals, substitute workflows | workflow_resolver; policy | Scoped |

**Ref:** Workflow hub; policy slices.

---

## 10.7 — Compliance

| Configurable item | Where configured | Status |
|-------------------|------------------|--------|
| Retention | Policy/compliance profile; section_25_current_state (25.6) | Partial |
| Evidence packs, inspector portal | compliance app; export_compliance_evidence_pack | Partial |
| Document requirements, safeguarding, regional controls | Policy/settings | Scoped |

**Ref:** section_25_current_state.md (25.6); compliance app.

---

## 10.8 — Dashboards

| Configurable item | Where configured | Status |
|-------------------|------------------|--------|
| Shell | public/manager/tenant urlconf; backend_base, control-plane-shell | Done |
| Widgets | default_dashboard_widgets(role); DashboardTemplate; TenantLayoutAssignment; dashboard_resolver.for_role | Done |
| Density | Policy/theme; RESOLVED_BACKEND_CONSOLE_THEME; density modes | Partial |
| Theme | School branding; ThemePack; theme_root_variables | Done |
| Role/section assignment | TenantLayoutAssignment (template per role); portal_sidebar_items | Done |
| Seasonal/school-stage modes | Policy/settings | Scoped |

**Ref:** phase4_workflow_dashboard_hubs.md; section_28 (28.2, 28.3); backend_base.html.

---

## Summary

- **Implemented or partial:** Admissions (number format, approval), Academics (grade scale, report style), Finance (payment providers), Dashboards (shell, widgets, theme, role assignment).
- **Scoped / deferred:** Fine-grained config for attendance, communication, HR, compliance (retention, evidence), and optional items (seasonal modes, quiet hours, etc.) — drive from policy/settings when needed.

**Checklist to update:** Section 10.1–10.8 (mark done or partial with ref to this doc).
