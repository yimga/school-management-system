# Standards & Interoperability Layer (Blueprint C)

This document describes the **interop layer**: canonical domain models ⇄ standard adapters. Business logic in core apps uses canonical models; standards-specific logic lives in adapters that map to/from OneRoster, LTI, Ed-Fi.

## Design principle

- **Canonical model:** School, StudentProfile, Classroom, Term, Evaluation, etc. (Django ORM in `apps.schools`, `apps.people`, `apps.academics`, `apps.evals`, …).
- **Adapters:** Translate between canonical and a standard’s payload/API. No standard-specific types or logic in core app business code.

## OneRoster

| Aspect | Location |
|--------|----------|
| **Views (API)** | `apps.api.oneroster_views` — tenant-scoped, Bearer token auth; schools, students, teachers, classes, enrollments. |
| **Discovery / readiness** | `apps.api.interop_stubs.oneroster_readiness` — discovery and configuration status. |
| **Canonical ⇄ OneRoster** | Adapter logic lives in `oneroster_views`: reads School, StudentProfile, TeacherProfile, Classroom, etc., and builds OneRoster JSON. No separate adapter package yet; can be extracted to `apps.interop.oneroster` when needed. |
| **URLs** | Mounted under `api/` (see `apps.api.urls` or config URL includes). |

## LTI (1.3 / AGS / NRPS / Deep Linking)

| Aspect | Location |
|--------|----------|
| **Launch & services** | `apps.schools.section8_views`: `lti_launch`, `lti_launch_callback`, `lti_ags_lineitems`, `lti_ags_scores`, `lti_ags_results`, `lti_nrps_memberships`, `lti_deep_linking`, `jwks_json`. |
| **Discovery / readiness** | `apps.api.interop_stubs.lti_readiness` — LTI 1.3 / platform status. |
| **Canonical ⇄ LTI** | Launch and AGS/NRPS use canonical models (Course ↔ Classroom, Member ↔ User/StudentProfile). Adapter logic is in section8_views; can be moved to `apps.interop.lti` for clarity. |
| **URLs** | `lti/launch/<tool_id>/`, `lti/service/<tool_id>/lineitems`, etc. (config.urls, config.public_urls). |

## Ed-Fi

| Aspect | Location |
|--------|----------|
| **Status** | Stub only. Discovery/readiness: `apps.api.interop_stubs.edfi_readiness` (if present). |
| **Future** | When implemented: create `apps.interop.edfi` (or `apps.api.edfi_views`) with canonical ⇄ Ed-Fi mapping; keep core apps unchanged. |

## Suggested package layout (optional)

To formalize further, introduce an `interop` app or package:

- `interop/oneroster/` — OneRoster adapter (serialize canonical → OneRoster JSON; parse incoming if needed).
- `interop/lti/` — LTI 1.3 launch, AGS, NRPS adapters (canonical ⇄ LTI payloads).
- `interop/edfi/` — Ed-Fi adapter (when built).

Core apps (academics, people, evals, schools) would only depend on canonical models; they would not import from `interop` or `api.oneroster_views`. All standard-specific code stays in `api` or `interop`.

## Discovery endpoints

- OneRoster: use interop_stubs discovery/readiness view (query param or tenant context).
- LTI: use interop_stubs LTI readiness view.
- Ed-Fi: readiness stub if implemented.

Rate limiting and tenant resolution are applied in the existing views and stubs.

## Syllabus (GlobalSyllabus ⇄ course syllabus)

| Concept | Location | Purpose |
|--------|----------|---------|
| **GlobalSyllabus** | `apps.siteconfig.models.GlobalSyllabus` | Global syllabus/standards nodes (code, name, description, parent, country_code). Used for semantic mapping: scanned/syllabus text → embeddings/similarity → suggest or map to nodes. National syllabus sync and AI tagging reference this. |
| **CourseSyllabus** | `apps.academics.models.CourseSyllabus` | Tenant per-subject syllabus (one per SubjectAssignment); builder_data JSON, optional link to curriculum nodes. Teacher-facing syllabus builder and portal. |
| **Mapping** | `siteconfig.tasks.national_syllabus_sync` (stub), future: OCR/LLM → GlobalSyllabus; tenant CourseSyllabus can reference or align to GlobalSyllabus nodes when “standards alignment” is enabled. | Scanned syllabi or ministry/OCR output → match to GlobalSyllabus by country_code and semantic similarity; 36-week schemes can be produced via Ollama. |

Canonical in-tenant syllabus is **CourseSyllabus**; **GlobalSyllabus** is the shared standards tree (public/siteconfig) for alignment and national sync.
