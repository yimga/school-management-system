# RunMyCampus — Buyer personas (GTM)

Short, product-specific notes for discovery calls. All flows assume **CP-first** navigation; **admin is Advanced fallback** for superuser edge cases.

## School owner / director

- **Jobs**: keep the school running, protect reputation, control spend.
- **Cares about**: uptime, data residency posture where applicable, who can change branding and critical settings, audit evidence for accreditation conversations.
- **RunMyCampus angle**: Configuration Control Center, tenant runtime snapshot, feature control, evidence pages for publish and reports.

## Principal / head of school

- **Jobs**: academic quality, parent confidence, staff coordination.
- **Cares about**: term publish status, class-level visibility, teacher tools vs admin clutter.
- **RunMyCampus angle**: Term publish evidence, report builder + Studio Output, teacher dashboard separation from platform admin.

## Registrar / records officer

- **Jobs**: correct cohorts, calendars, and transcript/report readiness.
- **Cares about**: academic years, departments, schedules of record, export evidence.
- **RunMyCampus angle**: Academic years and departments (setup evidence), scheduled reports evidence, report templates catalog, report output history (read-only).

## Finance / school administrator (operator)

- **Jobs**: fee clearance hooks, batch comms, scheduled operational reports.
- **Cares about**: who receives scheduled runs, when next run is due, bulk letters (where enabled).
- **RunMyCampus angle**: Scheduled report delivery hub, bulk letters operator surface, API list endpoints documented on hub pages.

## Teacher

- **Jobs**: teach, assess, communicate with class and parents.
- **Cares about**: fast grading and classroom context, not school-wide config.
- **RunMyCampus angle**: Role-appropriate entry (portal/teacher), Studio for outputs where licensed; no tenant-wide settings in daily path.

## Parent / guardian

- **Jobs**: see child progress, download official PDFs when published.
- **Cares about**: clarity, no surprise data from other families.
- **RunMyCampus angle**: Parent portal, publish gates, hash/audit on report outputs where models exist.

## District / regional operator (when applicable)

- **Jobs**: standards, interoperability, roster integrity.
- **Cares about**: OneRoster/interop modules, district hub patterns, auditability.
- **RunMyCampus angle**: Interop surfaces and compliance hooks as enabled per deployment; not oversold in generic demos.
