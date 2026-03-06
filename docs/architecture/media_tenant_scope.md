# Media and File Upload — Tenant Scope (Section 25.3, 27.1)

Architecture requires: **Media/static tenant-prefixed; object storage path = `storage/<tenant-id-or-schema>/<module>/<entity>/<file>`.**

## Pattern for new fields

Use tenant-prefixed `upload_to` so files are stored per tenant and cannot be accessed cross-tenant by path guess.

**Option A — Siteconfig helper (recommended when model has school/school_id):**

```python
from apps.siteconfig.models import _tenant_upload_to

class MyModel(models.Model):
    school = models.ForeignKey(School, ...)
    attachment = models.FileField(upload_to=_tenant_upload_to("my_module/attachments"), ...)
```

This produces paths like `tenants/<school_id>/my_module/attachments/<filename>`.

**Option B — Callable that gets school from instance:**

```python
def my_upload_to(instance, filename):
    school_id = getattr(instance, "school_id", None) or getattr(getattr(instance, "school", None), "id", None)
    if school_id:
        return f"tenants/{school_id}/my_module/{filename}"
    return f"shared/my_module/{filename}"  # only for control-plane models
```

## Audit results (FileField/ImageField)

| App | Model / location | upload_to | Tenant-scoped? | Note |
|-----|------------------|-----------|----------------|------|
| siteconfig | SiteSettings (branding, etc.) | branding/..., branding/themepack/... | No | Global/site-level; consider tenant prefix if multi-tenant SiteSettings |
| siteconfig | WaiverRequest.proof_file | tenant_upload_to_waiver_requests | **Yes** | Uses _tenant_upload_to |
| siteconfig | OfficialReportTemplate.template_file | report_templates/official/ | No | Add tenant prefix in new migration if per-tenant |
| siteconfig | ReportCardStyle.watermark_logo | branding/reportcard/watermarks/ | No | Per-style; consider tenant if style is tenant-scoped |
| people | TeacherProfile.profile_photo | tenant_upload_to_teacher_profile_photo | **Yes** | people.models (tenant_uploads/people/profiles/teachers or tenants/{id}/…) |
| people | StudentProfile.profile_photo | tenant_upload_to_student_profile_photo | **Yes** | people.models (tenant_uploads/people/profiles/students or tenants/{id}/…) |
| people | PassportDocument.file | _passport_doc_upload_to | **Yes** | verified_by_school_id or tenant_uploads/people/passport_docs |
| accounts | User profile_photo | profiles/ | No | User may be cross-tenant; scope by school when linked |
| portal | FormSignature.signed_pdf | _form_signature_upload_to | **Yes** | school from student |
| portal | LessonPlan.file | _lesson_plan_upload_to | **Yes** | school from teacher |
| portal | LessonPlanAttachment.file | _lesson_plan_attachment_upload_to | **Yes** | school from lesson_plan.teacher |
| portal | TeacherTrainingEntry.document | _training_entry_upload_to | **Yes** | school from teacher |
| portal | AttendanceJustification.document | _justification_upload_to | **Yes** | school from student |
| portal | PhotoUploadToken.photo | _photo_upload_token_upload_to | **Yes** | school from student or teacher |
| portal | Document (PortalFeatureItem.file) | _portal_feature_item_file_upload_to | **Yes** | school FK added; tenant prefix when school_id set (Section 25.3) |
| portal (kb) | KB article attachments, ODT | kb/attachments/, kb/odt/ | No | Tenant-scoped; add tenant prefix when KB has school |
| academics | CourseSyllabus.uploaded_file | _syllabus_upload_to | **Yes** | school from subject_assignment.academic_year |
| reports | ReportCard.pdf_file | reportcard_pdf_upload_to | **Yes** | tenants/{school_id}/reports/reportcards/ or tenant_uploads/… |
| communication | ContactRequestAttachment.file | contact_request_attachment_upload_to | **Yes** | school_id or request.school_id |
| analytics | GradeImportJob.uploaded_file | grade_import_job_upload_to | **Yes** | school from academic_year |
| finance | Invoice attachment, payment_proof | _invoice_attachment_upload_to, _invoice_payment_proof_upload_to | **Yes** | Uses _tenant_upload_to("finance/invoices"), ("finance/payment_proofs") |
| finance | (receipt, statement if any) | finance/... | No | Add tenant prefix if present |
| evals | EvaluationEvidence.file | _evaluation_evidence_upload_to | **Yes** | school from evaluation |
| emis | EMISExport.file_path | _emis_export_upload_to | **Yes** | school from academic_year |

## Refactor order (Phase 3)

1. **High impact:** finance (invoices, payment proofs), people (profile photos, passport docs), portal (documents, signed forms, lesson notes).
2. **Medium:** reports (reportcards), communication, academics, evals, analytics.
3. **Siteconfig:** branding/themes may be global or per-tenant depending on product; document decision then add tenant prefix if per-tenant.

## Migration strategy

- **New fields:** Use _tenant_upload_to or tenant-prefixed callable from day one.
- **Existing fields:** Add a migration that (1) adds a new field with tenant-prefixed upload_to, (2) backfills from old path to new path (or run a one-off script), (3) removes old field and renames new to old. Alternatively, keep existing paths and enforce tenant isolation via RLS/schema only (files under same storage bucket; access control by app layer). Document choice per module.

## Static files

- **Static:** Already versioned and shared; no tenant prefix required.
- **Media:** Per above; tenant prefix for all tenant-scoped file uploads.

## Section 25.3 — Search, cache, async (isolation hardening)

- **Search:** GlobalSearchAPI (`apps/api/search_api.py`) filters all querysets by `request.school` when set (StudentProfile, TeacherProfile, Classroom, Subject, Invoice). KB search remains region-filtered per product.
- **Cache:** Search suggestions use `tenant_cache_key()` so history is per-tenant. Other caches already use `get_tenant_cache_prefix` or `tenant_cache_key` (see cache_utils.py).
- **Async:** Tasks that touch tenant data should receive `school_id` and use schema/school context; audit per task when adding new ones.
- **Analytics:** Tenant-tag metrics; avoid PII in shared logs (observability middleware).
