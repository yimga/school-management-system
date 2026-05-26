# University Applications Registry — Counselor Guide

**Wave O · v3.95.0 · 2026-05-26**

Senior-year sticky moat. Students whose RMC record generates their UCAS / Common App / WAEC / IB / Joint Admissions package develop a hard-to-break dependency on the platform.

This module is the **read-only pathway specs registry** — what each major university application platform requires, in what format, with what supporting documents.

## Pathways (7 seeded)

| Pathway | Region | Window | Transcript format | Fee |
|---|---|---|---|---|
| `ucas-uk` | UK | Sept–Jan | UCAS XML | £28.50 |
| `common-app-us` | US | Aug–Feb | Common App JSON | Per-college (Common App itself free) |
| `ib-dp-result-release` | Global-IB | July | IB official release | — |
| `waec-nigeria` | Nigeria | Jan–Apr | WAEC CSV batch | ₦27,500 |
| `jamb-utme-nigeria` | Nigeria | Jan–Mar | JAMB CSV batch | ₦4,700 |
| `cuet-india` | India | Mar–Apr | CUET CSV batch | ₹850 (general) |
| `kuccps-kenya` | Kenya | May–Jun | KUCCPS CSV batch | KES 1,500 |

## What each pathway declares

```python
@dataclass(frozen=True)
class UniversityPathway:
    pathway_id: str
    display_name: str
    region: str
    submission_window_months: tuple[int, ...]
    transcript_format: str
    fields_required: tuple[FieldRequirement, ...]    # required vs optional
    documents_required: tuple[DocumentRequirement, ...]
    fee_amount_minor: int
    fee_currency: str
```

Each `FieldRequirement` is `(field_name, required, notes)` where `field_name` is the canonical RMC data path (e.g. `student.gcse_results`, `student.aadhaar_number`). Each `DocumentRequirement` is `(doc_id, display_name, required, file_types)`.

## Completeness checker

The registry ships a `check_completeness()` helper that runs the eligibility check:

```python
from apps.student360.university_apps_registry import (
    get_pathway, check_completeness,
)

pathway = get_pathway("ucas-uk")

def field_resolver(field_name: str):
    # Tenant-scoped: read the canonical RMC field for this student.
    return resolve_student_field(student_id, field_name)

def doc_resolver(doc_id: str):
    return Document.objects.filter(student=student, doc_id=doc_id).exists()

report = check_completeness(
    pathway,
    field_value_resolver=field_resolver,
    document_present_resolver=doc_resolver,
)
# → CompletenessReport(pathway_id='ucas-uk', ready=False,
#       missing_fields=['student.personal_statement'],
#       missing_documents=['teacher_reference'])
```

Resolver exceptions are caught and treated as missing — the checker never raises into the caller.

## Boundary

- Pure read-only registry. No I/O inside the module itself. **All ORM access happens in the caller's resolver callbacks** — this preserves tenant scope and avoids any cross-tenant query risk.
- Live submission (UCAS XML upload, Common App JSON push) requires per-platform partner agreements and counsel signoff. Wave O+1 ships once each agreement is in place.

## Tests

[apps/student360/tests/test_university_apps_registry.py](beta/school-management-system/apps/student360/tests/test_university_apps_registry.py) — 15 unit tests covering registry shape, region filters, completeness checker (required vs optional, exception handling).
