"""Seed canonical platform-wide DynamicFieldDefinition rows.

The DynamicFieldDefinition model supports ``school=NULL`` for
platform-wide definitions (see model docstring). This command upserts
a canonical recipe set so every tenant gets a sensible default custom
field vocabulary on day one.

Per-tenant overrides remain possible by creating rows with
``school=<School>`` — the existing resolution code already prefers
tenant-specific rows over platform-wide.

Idempotent: ``update_or_create(entity_type=..., field_key=..., school=None)``.

Run:
    python manage.py seed_dynamic_field_recipes
    python manage.py seed_dynamic_field_recipes --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.metadata.models import DynamicFieldDefinition


# The form filter (apps.metadata.dynamic_forms._entity_type_for_model) keys every
# definition on "<app_label>.<model_name>" (e.g. "people.studentprofile"). These
# recipes historically used bare domain nouns ("student"), so EVERY row this
# command wrote was permanently invisible to every form — an entity_type mismatch
# that silently dropped the whole seeded vocabulary. Normalize each recipe's
# entity_type to the model label the forms actually query so the seed and the
# form filter speak ONE vocabulary. (apps.metadata.country_eav_catalog already
# uses the dotted form, which is why the country identity fields worked.)
_ENTITY_TYPE_TO_MODEL_LABEL: dict[str, str] = {
    "student": "people.studentprofile",
    "guardian": "people.studentguardian",
    "teacher": "people.teacherprofile",
    "classroom": "academics.classroom",
    "invoice": "finance.invoice",
    "payment": "finance.payment",
    "attendance": "academics.attendance",
    "evaluation": "evals.evaluation",
    "applicant": "people.applicant",
    "event": "school_events.schoolevent",
    "discipline_incident": "academics.incident",
    "medical_visit": "schoolops.healthrecord",
}


def canonical_entity_type(raw: str) -> str:
    """Translate a bare recipe entity noun to the dotted "app_label.model_name"
    the forms query. Already-dotted or unmapped values pass through unchanged."""
    if "." in raw:
        return raw
    return _ENTITY_TYPE_TO_MODEL_LABEL.get(raw, raw)


# Canonical platform-wide custom-field recipes.
# Format: (entity_type, field_key, label, data_type, required)
# entity_type is written as a bare domain noun for readability and normalized to
# the dotted model label via canonical_entity_type() at write time.
PLATFORM_FIELD_RECIPES: list[tuple[str, str, str, str, bool]] = [
    # === Student profile ===
    ("student", "preferred_name", "Preferred name", "string", False),
    ("student", "pronouns", "Pronouns", "string", False),
    ("student", "ethnicity", "Ethnicity", "string", False),
    ("student", "primary_language", "Primary language at home", "string", False),
    ("student", "secondary_language", "Secondary language", "string", False),
    ("student", "religion", "Religion", "string", False),
    ("student", "dietary_restrictions", "Dietary restrictions", "string", False),
    ("student", "allergies", "Allergies (severe)", "string", False),
    ("student", "medical_conditions", "Medical conditions", "string", False),
    ("student", "medications", "Daily medications", "string", False),
    ("student", "iep_active", "IEP active", "boolean", False),
    ("student", "iep_review_date", "IEP next review date", "date", False),
    ("student", "504_plan_active", "504 plan active", "boolean", False),
    ("student", "transport_route", "Transport route", "string", False),
    ("student", "transport_pickup_stop", "Pickup stop", "string", False),
    ("student", "cafeteria_meal_plan", "Cafeteria meal plan", "string", False),
    ("student", "boarder_status", "Boarder status", "string", False),
    ("student", "house", "House / pastoral group", "string", False),
    ("student", "previous_school", "Previous school", "string", False),
    ("student", "scholarship_status", "Scholarship status", "string", False),
    ("student", "emergency_contact_name", "Emergency contact name", "string", False),
    ("student", "emergency_contact_phone", "Emergency contact phone", "string", False),
    ("student", "emergency_contact_relationship", "Emergency contact relationship", "string", False),
    ("student", "guardian_consent_photography", "Photo consent on file", "boolean", False),
    ("student", "guardian_consent_data_sharing", "Data-sharing consent on file", "boolean", False),

    # === Guardian profile ===
    ("guardian", "occupation", "Occupation", "string", False),
    ("guardian", "employer", "Employer", "string", False),
    ("guardian", "preferred_contact_method", "Preferred contact method", "string", False),
    ("guardian", "preferred_language", "Preferred communication language", "string", False),
    ("guardian", "primary_address", "Primary address", "string", False),
    ("guardian", "alternate_phone", "Alternate phone", "string", False),
    ("guardian", "is_emergency_contact", "Is emergency contact", "boolean", False),
    ("guardian", "is_pickup_authorized", "Authorized for pickup", "boolean", False),
    ("guardian", "billing_responsible", "Responsible for billing", "boolean", False),

    # === Teacher / staff profile ===
    ("teacher", "qualification_level", "Highest qualification", "string", False),
    ("teacher", "subject_specialism", "Subject specialism", "string", False),
    ("teacher", "years_experience", "Years experience", "number", False),
    ("teacher", "certifications", "Certifications", "string", False),
    ("teacher", "languages_taught", "Languages taught", "string", False),
    ("teacher", "homeroom", "Homeroom classroom", "string", False),
    ("teacher", "extracurricular_clubs", "Extracurricular clubs led", "string", False),
    ("teacher", "is_substitute", "Substitute teacher", "boolean", False),

    # === Classroom ===
    ("classroom", "room_number", "Room number", "string", False),
    ("classroom", "capacity", "Capacity", "number", False),
    ("classroom", "has_projector", "Has projector", "boolean", False),
    ("classroom", "has_whiteboard", "Has whiteboard", "boolean", False),
    ("classroom", "has_smartboard", "Has interactive whiteboard", "boolean", False),
    ("classroom", "wheelchair_accessible", "Wheelchair accessible", "boolean", False),
    ("classroom", "building", "Building / wing", "string", False),

    # === Invoice ===
    ("invoice", "po_number", "Purchase order number", "string", False),
    ("invoice", "scholarship_code", "Scholarship code", "string", False),
    ("invoice", "discount_code", "Discount code", "string", False),
    ("invoice", "discount_reason", "Discount reason", "string", False),
    ("invoice", "approved_by", "Approved by", "string", False),
    ("invoice", "approval_date", "Approval date", "date", False),
    ("invoice", "payment_plan_active", "Payment plan active", "boolean", False),
    ("invoice", "fiscal_year", "Fiscal year tag", "string", False),

    # === Payment ===
    ("payment", "external_reference", "External gateway reference", "string", False),
    ("payment", "settlement_date", "Settlement date", "date", False),
    ("payment", "reconciled", "Reconciled", "boolean", False),
    ("payment", "reconciled_by", "Reconciled by", "string", False),
    ("payment", "exchange_rate_used", "Exchange rate used", "number", False),

    # === Attendance ===
    ("attendance", "excuse_reason", "Excuse reason", "string", False),
    ("attendance", "documentation_attached", "Documentation attached", "boolean", False),
    ("attendance", "notified_guardian", "Guardian notified", "boolean", False),

    # === Evaluation / grade ===
    ("evaluation", "rubric_used", "Rubric used", "string", False),
    ("evaluation", "secondary_assessor", "Secondary assessor", "string", False),
    ("evaluation", "rerubricked", "Re-rubricked", "boolean", False),

    # === Application / admissions ===
    ("applicant", "previous_school_country", "Previous school country", "string", False),
    ("applicant", "siblings_currently_enrolled", "Siblings currently enrolled", "boolean", False),
    ("applicant", "referral_source", "Referral source", "string", False),
    ("applicant", "interview_score", "Interview score", "number", False),
    ("applicant", "entrance_exam_score", "Entrance exam score", "number", False),
    ("applicant", "scholarship_requested", "Scholarship requested", "boolean", False),

    # === Event / calendar ===
    ("event", "location_room", "Location / room", "string", False),
    ("event", "external_url", "External URL", "string", False),
    ("event", "requires_rsvp", "Requires RSVP", "boolean", False),
    ("event", "rsvp_deadline", "RSVP deadline", "date", False),

    # === Discipline ===
    ("discipline_incident", "witnesses", "Witnesses", "string", False),
    ("discipline_incident", "evidence_url", "Evidence attachment URL", "string", False),
    ("discipline_incident", "parent_notified_at", "Parent notified at", "date", False),
    ("discipline_incident", "appeal_filed", "Appeal filed", "boolean", False),

    # === Medical visit ===
    ("medical_visit", "primary_complaint", "Primary complaint", "string", False),
    ("medical_visit", "vital_signs", "Vital signs (JSON)", "json", False),
    ("medical_visit", "medication_dispensed", "Medication dispensed", "string", False),
    ("medical_visit", "returned_to_class", "Returned to class", "boolean", False),
    ("medical_visit", "guardian_contacted", "Guardian contacted", "boolean", False),
]


class Command(BaseCommand):
    help = "Seed canonical platform-wide DynamicFieldDefinition rows. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report only; no writes.")

    def handle(self, *args, **options):
        dry = bool(options.get("dry_run"))
        created = 0
        updated = 0
        for raw_entity_type, field_key, label, data_type, required in PLATFORM_FIELD_RECIPES:
            entity_type = canonical_entity_type(raw_entity_type)
            if dry:
                exists = DynamicFieldDefinition.objects.filter(
                    entity_type=entity_type, field_key=field_key, school=None
                ).exists()
                if not exists:
                    created += 1
                continue
            _, was_created = DynamicFieldDefinition.objects.update_or_create(
                entity_type=entity_type,
                field_key=field_key,
                school=None,
                defaults={
                    "label": label,
                    "data_type": data_type,
                    "required": required,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        verb = "would create" if dry else "ensured"
        self.stdout.write(
            self.style.SUCCESS(
                f"DynamicFieldDefinition recipes: {len(PLATFORM_FIELD_RECIPES)} {verb} "
                f"(new={created}, updated={updated})."
            )
        )
