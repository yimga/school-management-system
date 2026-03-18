# Land-and-expand: read-only legacy SIS (BR-09)

**Purpose:** Analytics and interop against **lawfully obtained** CSV/API exports from incumbent SIS — no scraping without contract.

**Configuration:** Superuser/staff: `POST /api/internal/br/legacy-sis-readonly/` with tenant context and body `{"enabled": true, "label": "PowerSchool export"}` — stores under `school.settings["legacy_sis_readonly"]`.

**Status:** `GET` same path returns `{ configured, mode: "csv_api" }`.

**Product:** Ship packaged dashboards fed by scheduled CSV drops or partner API when licensed.
