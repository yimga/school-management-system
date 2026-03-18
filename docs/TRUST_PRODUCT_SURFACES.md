# Trust product (visible security and trust)

**Purpose:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §10.5.4 and [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md). Security and trust are visible in product surfaces, not only in backend and docs.

**Authority:** This doc defines required trust surfaces and maps them to current entry points. Completion gate: key trust dimensions (MFA, sessions, admin activity, audit exports) visible in a dedicated trust/security area or control plane; roadmap for the rest.

---

## 1. Required surfaces (checklist)

| Surface | Purpose | Status | Current entry point(s) | Roadmap |
|---------|---------|--------|------------------------|---------|
| **MFA status** | User sees if MFA is enabled and can set up or manage | **Exists** | `accounts:mfa_setup`, `accounts:mfa_verify`, passkey registration/authentication; MFA banner (dismiss_mfa_banner). | Surface MFA status and “Manage” in a dedicated Security/account area; link from role-home or shell. |
| **Device/session history** | User sees active sessions and devices; revoke if needed | **Partial** | Session claims API (`api:session-claims`); no dedicated “Sessions” or “Devices” page in UI. | Add accounts/super page: list sessions with device/location/last active; “Revoke” with audit. |
| **Admin activity** | Audit of admin actions (who did what, when) | **Partial** | Feature-control audit (`siteconfig:feature_control_audit`); Studio OS audit API (`studio_os:audit`); compliance audit trail; evals audit_trail; AI audit (log_ai_action, ai_copilot_audit). | Unify under a single “Admin activity” or “Audit log” surface in control plane / trust center; export for compliance. |
| **Impersonation/break-glass usage** | Log and visibility when staff impersonates a user | **Exists** | `accounts:impersonate_entry`, `accounts:end_impersonation`; `siteconfig:grant_impersonation_consent`, `revoke_impersonation_consent`. | Add “Impersonation log” in trust center or super: who impersonated whom, when, duration; require justification or audit-only. |
| **Integration/API key governance** | View and manage integrations; API keys; kill switch; health | **Partial** | API Center / Integration (apicenter, siteconfig Integration); INTEGRATION_API_CENTER_UNIFIED.md; rate limit, audit, scopes. | Expose in Control Studio or dedicated “Integrations & API keys” in trust area; key lifecycle (rotate, revoke); health status visible. |
| **Policy enforcement status** | Visibility into which policies apply and enforcement state | **Partial** | Runtime inspector; policy bundles; feature control. | Control Studio or trust center: “Active policies” and “Why this is on/off”; link to policy bundle and entitlement. |
| **Data residency/regional behavior** | Where data is stored; regional defaults | **Backlog** | Runtime precedence (regional default); no dedicated “Data residency” page. | Add trust center section: region, residency summary, link to runtime/legal. |
| **Audit exports** | Export audit logs for compliance or review | **Partial** | Compliance audit trail report; certification export; AI audit feed. No single “Export all audit” for tenant/super. | Add “Export audit” in trust center: date range, scope (admin, AI, login, impersonation), format (CSV/JSON); rate-limited. |
| **Role/permission reviews** | See and review who has what access | **Partial** | RBAC dashboard (`accounts:rbac_dashboard`); backend dashboard; permission model in code. | Trust center or Control: “Access review” — list roles and permissions; link to RBAC and delegation. |
| **Risky action approvals** | Approval or confirmation for high-impact actions | **Partial** | Some flows require confirm (e.g. rollback, delete); no unified “Risky actions” or approval log. | Define risky actions (impersonate, rollback, delete tenant, bulk export); require reason or approval; show in audit. |

---

## 2. Dedicated trust/security area

**Goal:** One place (or a small set of linked places) where users and operators see trust dimensions.

| Scope | Suggested location | Contents |
|-------|--------------------|----------|
| **User (tenant staff)** | Accounts “Security” or “Trust” section (e.g. under backend dashboard or profile) | MFA status and setup; Sessions/devices; “Who has access” (link to RBAC if permitted). |
| **Operator / admin** | Control Studio or siteconfig “Security & trust” hub | MFA enforcement; admin activity / audit log; impersonation log; integration/API governance; policy enforcement summary; audit export. |
| **Super / platform** | Super dashboard or “Trust center” | All of the above at platform scope; tenant-level audit; data residency; risky-action log; role/permission review. |

**Current state:** Super **Trust center** (`super:trust_center`) links Compliance, API Center, Sessions, Audit export, SSO health, Platform events, developer API. MFA and impersonation under accounts; feature-control and Studio audit under siteconfig/studio_os; compliance/evals retain dedicated trails.

**Roadmap:**
1. Add a **Trust** or **Security & trust** entry in the unified shell (sidebar or Control Studio) that links to: MFA, Sessions, Admin activity, Impersonation log, Integrations/API keys, Audit export.
2. Implement **Sessions/devices** page (accounts or trust) and **Audit export** (date range, scope, format).
3. Add **Impersonation log** view (super or tenant admin) and **Risky action** logging where missing.
4. Surface **Policy enforcement** and **Data residency** in Control or trust center when product prioritizes them.

---

## 3. Single entry point (control plane / super)

Key trust dimensions are visible today via the following; together they satisfy the gate that trust is in product/control plane, not only backend.

| Entry point | Surface | Notes |
|-------------|---------|--------|
| **Control plane nav** | Security & Trust | `super:trust_center` — hub linking Compliance, API Center, Sessions, Audit export ([control_plane_nav.py](../apps/schools/control_plane_nav.py) "Security & Trust"). |
| **Control plane nav** | Compliance | `super:compliance_overview` — policy pack, audit review, export risk. |
| **Control plane nav** | API Center | `apicenter:dashboard` — integration/API key governance. |
| **Super** | Audit export | `super:audit_export` — date range, CSV/JSON, rate-limited (60s). |
| **Super** | Platform events | `super:platform_events` — PlatformEventLog (pack apply/rollback, emit_platform_event); linked from trust center. |
| **Accounts** | Sessions | `accounts:sessions_page` — list sessions, revoke; `accounts:sessions_revoke` POST. |
| **Accounts (user)** | MFA | `accounts:mfa_setup`, `accounts:mfa_verify`; MFA banner in admin context. |
| **Accounts (user)** | Security activity & export | `accounts:api_security_strength`, `accounts:api_security_activity`, `accounts:api_security_export_log`, `accounts:api_security_lockdown` (profile/security/*). |
| **Accounts (operator)** | Impersonation | `accounts:impersonate_entry`, `accounts:end_impersonation`; consent via siteconfig. |

**Rule:** New trust dimensions (e.g. Sessions page, unified audit export, impersonation log) should be added to §1 and surfaced via this table and the roadmap in §2.

---

## 4. Completion gate (§10.5.4)

- **Key dimensions visible:** MFA (accounts MFA setup/verify and banner) is visible; sessions are partially visible via API — add Sessions page to meet gate. Admin activity is visible in multiple audit trails (feature_control_audit, studio_os audit, compliance, AI). Audit exports exist per-domain (e.g. compliance, certification); add a unified “Export audit” for gate.
- **Dedicated area:** Trust is visible via control plane (Compliance, API Center) and accounts (profile/security, MFA, impersonation). §3 documents entry points; §2 roadmap defines Trust hub and remaining surfaces.
- **Gate met when:** (1) At least one “Trust” or “Security & trust” entry in shell or Control Studio linking MFA, Sessions (once built), Admin activity, Audit export; and (2) roadmap for remaining surfaces documented (this doc).

---

## 5. Status

- **Doc:** This file. Surfaces and entry points (§1, §3); Trust center, Sessions page, and unified audit export implemented.
- **Gate (§10.5.4):** Met — Trust center in control plane; Sessions page and audit export implemented; key dimensions visible.
- **Roadmap:** Impersonation log view; policy enforcement and data residency in trust area (see §2).
