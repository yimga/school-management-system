# Metadata Lineage Approach

**Purpose:** §3.3 "Add lineage/dependency graph" in the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).

**Status:** PARTIAL — usage registry and package lineage exist; **unified lineage API** at `/api/internal/metadata/lineage/`; **lineage graph UI** at `/api/internal/metadata/lineage/graph/` (form, downstream table, blast radius, packages, SVG graph).

---

## 1. Current building blocks

- **usage_registry** (`apps/metadata/usage_registry.py`) — "what uses this" for registered objects.
- **Package engine** — payload registration, blast radius, dependency validation.
- **dashboard_resolver / workflow_resolver** — lineage registration for dashboards and workflows.
- **changelog** (`apps/metadata/changelog.py`) — metadata change audit.

---

## 2. Target lineage coverage

| Object type | Mechanism |
|-------------|-----------|
| Workflows | workflow_resolver + pack assignments |
| Dashboards | dashboard_resolver + pack assignments |
| Reports | Report templates + runtime_blueprints |
| APIs | INTEGRATION_CATALOG + API Center |
| Templates | Catalog / siteconfig references |
| Packs | Package dependency graph + apply order |

---

## 3. Next steps

- [x] Single "lineage API" aggregating usage_registry + package lineage + blast radius — `GET /api/internal/metadata/lineage/?object_type=entity&code=…` (entity | field | package | consumer); `apps/metadata/lineage_api.get_unified_lineage()`; staff-only.
- [x] Governance UI: search + graph view + "what uses this?" — search at /api/internal/metadata/governance/; lineage graph at /api/internal/metadata/lineage/graph/ (entity, field, package, consumer; downstream table + blast radius + packages + SVG node-edge graph). Workflows, dashboards, reports, APIs, templates, packs surface via usage_registry and lineage API.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §3.3.*
