"""RunMyCampus canonical-template accelerator — the long-tail path.

The "Shopify CSV import" pattern applied to schools. Any operator with
data in Excel, Google Sheets, MS Access, a regional SIS not yet in the
signature table, or an in-house custom app can produce a canonical
RunMyCampus bundle by downloading our template, filling in what they
have, and uploading. No vendor accelerator needed.

Filename convention (case-insensitive, matched against the canonical
domain set):

    students.csv      staff.csv         guardians.csv      enrollment.csv
    sections.csv      attendance.csv    grades.csv         behavior.csv
    finance.csv       transcripts.csv   health.csv         payroll.csv
    communications.csv events.csv       library.csv        transport.csv
    hostel.csv        cafeteria.csv     alumni.csv         compliance.csv
    athletics_teams.csv  athletics_memberships.csv  athletics_fixtures.csv

Headers in each file ARE the canonical field names — there is no source-
column-to-canonical-field mapping needed because the column names already
*are* the canonical fields. The accelerator pre-classifies each file and
attaches an identity mapping so the mapper's AI tier never runs for these
columns. Custom / per-tenant columns past the canonical set still flow
through the universal mapper as ``custom_fields``.

This accelerator is what makes "RunMyCampus is the platform for the long
tail of K-12" credible — any school migrating from any tool can produce
this bundle. Pairs with a wizard-side "Download canonical template" UX
(separate workstream) that generates the empty template per-domain so
operators don't have to invent the header set.

Activation:
    - Filename matches one of the canonical names (case-insensitive), OR
    - First-row headers include >= 3 canonical field names for that
      domain (so a renamed file still gets recognized).

When in doubt the accelerator raises ``AcceleratorError`` so the
universal pipeline takes over. Never silently downgrade fidelity.
"""

from __future__ import annotations

import logging
from typing import Any


from .base import Accelerator, AcceleratorContract, AcceleratorError, register_accelerator

logger = logging.getLogger(__name__)


# Canonical filename → canonical domain. Headers in each file are the
# canonical field names themselves, so we don't need column mappings.
CANONICAL_FILENAME_TO_DOMAIN: dict[str, str] = {
    "students.csv": "students",
    "staff.csv": "staff",
    "teachers.csv": "staff",
    "guardians.csv": "guardians",
    "parents.csv": "guardians",
    "structure.csv": "structure",
    "specialties.csv": "specialties",
    "specialty.csv": "specialties",
    "filieres.csv": "specialties",
    "enrollment.csv": "enrollment",
    "enrollments.csv": "enrollment",
    "sections.csv": "sections",
    "classes.csv": "sections",
    "attendance.csv": "attendance",
    "grades.csv": "grades",
    "behavior.csv": "behavior",
    "incidents.csv": "behavior",
    "finance.csv": "finance",
    "invoices.csv": "finance",
    "receipts.csv": "finance",
    "payments.csv": "finance",
    "transcripts.csv": "transcripts",
    "health.csv": "health",
    "payroll.csv": "payroll",
    "communications.csv": "communications",
    "events.csv": "events",
    "library.csv": "library",
    "transport.csv": "transport",
    "transport_assignments.csv": "transport_assignments",
    "hostel.csv": "hostel",
    "hostel_assignments.csv": "hostel_assignments",
    "cafeteria.csv": "cafeteria",
    "cafeteria_assignments.csv": "cafeteria_assignments",
    "alumni.csv": "alumni",
    "compliance.csv": "compliance",
    "athletics_teams.csv": "athletics_teams",
    "teams.csv": "athletics_teams",
    "squads.csv": "athletics_teams",
    "athletics_memberships.csv": "athletics_memberships",
    "athletics_fixtures.csv": "athletics_fixtures",
    "fixtures.csv": "athletics_fixtures",
    "matches.csv": "athletics_fixtures",
}


# Per-domain canonical header set. Used as the secondary activation
# signal when filenames have been renamed (operator-friendly).
DOMAIN_CANONICAL_HEADERS: dict[str, set[str]] = {
    "students": {
        "external_id", "first_name", "last_name", "middle_name",
        "date_of_birth", "gender", "email", "phone", "grade_level",
        "enrollment_status", "admission_number", "address",
        # 2026-08-16 gap-analysis: real StudentProfile columns now in the
        # ontology AND landed by StudentLander. Expose them in the downloadable
        # canonical template so a school migrating from an old SIS knows these
        # are understood (they were invisible before -> never exported). Order
        # is load-bearing: keep the companion JSON mirrors in the SAME order
        # (scan_companion_canonical_headers_drift is order-sensitive).
        "place_of_birth", "joined_date", "joined_term", "section",
        "parent_phone", "exam_candidate_number", "exam_center_code",
        "exam_system",
    },
    "staff": {
        "staff_external_id", "first_name", "last_name", "email",
        "role", "department", "phone",
    },
    "guardians": {
        "guardian_external_id", "first_name", "last_name", "email",
        "phone", "relationship", "is_primary", "student_external_id",
        # Internal transfers: the guardian's platform username, so the
        # target re-links the SAME account instead of provisioning anew.
        "guardian_user_ref",
        # Consent / visibility / contact-preference carry: identity-mapped
        # so the guardian lander RECEIVES them (a header outside this set is
        # shunted to custom_fields and never reaches the lander) and the
        # target does not reset a transferred parent's channel opt-outs,
        # results-access restriction, or finance visibility to defaults.
        "receives_email", "receives_sms", "receives_whatsapp",
        "can_view_results", "can_view_finance",
        "preferred_contact", "whatsapp_number", "address",
    },
    "enrollment": {
        "student_external_id", "grade_level", "enrollment_status",
        "enrollment_date", "exit_date", "section",
        # Curriculum track — required for grade placement parity
        # (Evaluation.clean: student specialty must match the assignment's).
        "specialty",
    },
    "structure": {
        # SPLIT-only academic scaffold provisioned at the target BEFORE
        # enrollment/grades (StructureLander). Identity-mapped so every column
        # reaches the lander; a header outside this set is shunted to
        # custom_fields and lost.
        "academic_year", "year_start", "year_end", "year_is_active",
        "term", "term_label", "term_position", "term_start", "term_end",
        "department", "classroom", "specialty", "subject", "coefficient",
        "teacher_ref", "teacher_first_name", "teacher_last_name", "teacher_email",
    },
    # Subject catalog (AcademicsLander → apps.academics.Subject). Distinct from
    # ``sections`` (Classroom) and ``structure`` (SPLIT scaffold). Without this
    # domain, courses.csv identity-maps into custom_fields and grades cannot
    # resolve Subjects at the target.
    "academics": {
        "subject_code", "subject_name", "credits", "department", "name", "code",
    },
    # Specialty / trade / stream catalog (SpecialtyLander → apps.academics.Specialty
    # + its required Department). Shares name/code/department with academics, so a
    # filename hint breaks the tie (see reconcile_domain_with_filename / CATALOG).
    "specialties": {
        "name", "code", "department", "description", "specialty_name",
        "specialty_code",
    },
    "sections": {
        "section_external_id", "subject_code", "subject_name",
        "term", "academic_year", "teacher_external_id",
    },
    "attendance": {
        "student_external_id", "date", "status", "code", "notes",
    },
    "grades": {
        "student_external_id", "subject_code", "term", "score",
        "letter_grade", "comments",
        # FK-graph placement + faithful component copy (2026-07-09): the
        # grades lander resolves academic_year/term/subject/assignment at
        # the target and lands per-component scores, never a re-derived
        # aggregate. "grade_letter" is the envelope-side alias the transfer
        # exporter and older bundles already emit.
        "academic_year", "grade_letter", "max_score",
        "seq1_score", "seq2_score", "exam_score", "mock_score",
        "practical_score", "internship_score", "test1", "test2",
    },
    "behavior": {
        "student_external_id", "date", "category", "description",
        "action_taken",
    },
    "finance": {
        "reference", "student_external_id", "amount", "currency",
        "issued_date", "due_date", "status", "description",
    },
    "transcripts": {
        "student_external_id", "academic_year", "term", "subject_code",
        "final_grade", "credits_earned",
        # Vault-item fields the transcripts lander has always consumed
        # (its documented row shape) + transfer provenance (2026-07-09).
        "artifact_type", "artifact_ref", "issued_at", "issuing_school_id",
    },
    "health": {
        "student_external_id", "record_date", "category", "description",
        "provider", "follow_up",
    },
    "payroll": {
        "staff_external_id", "pay_period", "gross_amount", "net_amount",
        "currency", "issued_date",
    },
    "communications": {
        "recipient_external_id", "channel", "subject", "body",
        "sent_at", "status",
    },
    "events": {
        "title", "category", "starts_at", "ends_at", "location",
        "description",
    },
    "library": {
        "item_external_id", "title", "author", "isbn", "category",
        "status",
    },
    "transport": {
        "student_external_id", "route", "stop", "pickup_time",
        "dropoff_time", "vehicle",
    },
    "transport_assignments": {
        "student_external_id", "route", "stop", "pickup_time",
        "dropoff_time",
    },
    "hostel": {
        "student_external_id", "room", "bed", "checkin_date",
        "checkout_date",
    },
    "hostel_assignments": {
        "student_external_id", "hostel", "room", "checkin_date",
        "checkout_date",
    },
    "cafeteria": {
        "student_external_id", "meal_plan", "balance", "currency",
        "dietary_notes",
    },
    "cafeteria_assignments": {
        "student_external_id", "meal_plan", "balance", "currency",
        "dietary_notes",
    },
    "alumni": {
        "external_id", "first_name", "last_name", "graduation_year",
        "email", "phone", "current_employer", "current_role",
    },
    # Derived statistics reports (school_stats: per-class/specialty aggregates).
    # Detected up front by is_derived_report and skipped, never landed as records.
    "reports": {
        "class", "specialty", "total", "passed", "failed", "pass %",
        "best avg", "worst avg", "male", "female",
    },
    "compliance": {
        "subject_external_id", "category", "status", "due_date",
        "completed_date", "notes",
    },
    # Athletics module round-trip (2026-07-09). Order is load-bearing:
    # the companion JSON mirrors must match this source order exactly
    # (scan_companion_canonical_headers_drift.py compares order-sensitive).
    "athletics_teams": {
        "sport", "season", "team_name", "level", "gender",
        "roster_cap", "home_venue", "status",
    },
    "athletics_memberships": {
        "student_external_id", "team_name", "jersey_number", "position",
        "status", "joined_date",
    },
    "athletics_fixtures": {
        "team_name", "opponent_name", "fixture_type", "venue",
        "scheduled_start", "scheduled_end", "home_score", "away_score",
        "status",
    },
}


# Human-friendly labels for the per-file upload tagger (operator picks
# "this file is X"). Any domain not listed falls back to a title-cased slug,
# so the tagger never breaks when a new canonical domain is added above.
DOMAIN_UI_LABELS: dict[str, str] = {
    "students": "Students",
    "staff": "Teachers / Staff",
    "guardians": "Parents / Guardians",
    "enrollment": "Enrollment",
    "structure": "Academic structure",
    "academics": "Subjects / Courses",
    "specialties": "Specialties / Trades / Streams",
    "sections": "Classes / Sections",
    "attendance": "Attendance",
    "grades": "Grades / Marks",
    "behavior": "Behaviour / Discipline",
    "finance": "Invoices / Fees",
    "transcripts": "Transcripts",
    "health": "Health records",
    "payroll": "Payroll",
    "communications": "Communications",
    "events": "Events",
    "library": "Library",
    "transport": "Transport",
    "transport_assignments": "Transport assignments",
    "hostel": "Hostel / Boarding",
    "hostel_assignments": "Hostel assignments",
    "cafeteria": "Cafeteria / Meals",
    "cafeteria_assignments": "Meal plan assignments",
    "alumni": "Alumni",
    "reports": "Reports / Statistics (reference only)",
    "compliance": "Compliance",
    "athletics_teams": "Athletics — teams",
    "athletics_memberships": "Athletics — roster",
    "athletics_fixtures": "Athletics — fixtures",
}

# Filename tokens → domain, so the tagger can AUTO-DETECT a file's record type
# from its name (server-side fallback mirrored by the client JS). First match
# wins; longer/more-specific tokens are listed before their prefixes.
DOMAIN_FILENAME_HINTS: tuple[tuple[str, str], ...] = (
    ("transport_assignment", "transport_assignments"),
    ("hostel_assignment", "hostel_assignments"),
    ("cafeteria_assignment", "cafeteria_assignments"),
    ("meal_plan_assignment", "cafeteria_assignments"),
    ("student", "students"),
    ("pupil", "students"),
    ("learner", "students"),
    ("teacher", "staff"),
    ("staff", "staff"),
    ("employee", "staff"),
    ("faculty", "staff"),
    ("parent", "guardians"),
    ("guardian", "guardians"),
    ("contact", "guardians"),
    ("enrol", "enrollment"),
    ("enroll", "enrollment"),
    ("registration", "enrollment"),
    # Specialty / trade / stream catalogs → specialties (before the broader
    # subject/class tokens so "specialties_*.csv" never falls through to them).
    ("specialt", "specialties"),
    ("specialit", "specialties"),
    ("filiere", "specialties"),
    # Subject/course catalogs → academics (Subject model), NOT sections
    # (Classroom). Class/section filenames stay on sections.
    ("subject", "academics"),
    ("course", "academics"),
    ("class", "sections"),
    ("section", "sections"),
    ("attendance", "attendance"),
    ("grade", "grades"),
    ("mark", "grades"),
    ("score", "grades"),
    ("result", "grades"),
    ("behavior", "behavior"),
    ("behaviour", "behavior"),
    ("discipline", "behavior"),
    ("incident", "behavior"),
    ("invoice", "finance"),
    ("fee", "finance"),
    ("finance", "finance"),
    ("billing", "finance"),
    ("payment", "finance"),
    ("transcript", "transcripts"),
    ("health", "health"),
    ("medical", "health"),
    ("payroll", "payroll"),
    ("payslip", "payroll"),
    ("salary", "payroll"),
    ("message", "communications"),
    ("communication", "communications"),
    ("event", "events"),
    ("library", "library"),
    ("book", "library"),
    ("transport", "transport"),
    ("bus", "transport"),
    ("hostel", "hostel"),
    ("boarding", "hostel"),
    ("dorm", "hostel"),
    ("cafeteria", "cafeteria"),
    ("meal", "cafeteria"),
    ("canteen", "cafeteria"),
    ("alumni", "alumni"),
    ("alumnus", "alumni"),
    ("compliance", "compliance"),
)


# Person-roster domains share the SAME column shape (name / dob / gender /
# email / phone / address), so raw header overlap CANNOT tell a student roster
# from a teacher, guardian, or alumni roster — a ``teachers_2026.csv`` scores
# just as high on the ``students`` synonym set. When a file's NAME names the
# entity, that human-authored label is the stronger signal than the columns.
PERSON_ROSTER_DOMAINS: frozenset[str] = frozenset(
    {"students", "staff", "guardians", "alumni"}
)

# Catalog domains share name/code/department, so a specialties export scores
# just as high on the subjects (academics) synonym set and vice-versa. Same
# tie-break: trust the file's own name.
CATALOG_DOMAINS: frozenset[str] = frozenset(
    {"academics", "specialties", "sections"}
)

# Groups of domains that content-scoring cannot tell apart. A filename hint
# only overrides content WITHIN one of these groups — never across them.
_AMBIGUOUS_GROUPS: tuple[frozenset[str], ...] = (
    PERSON_ROSTER_DOMAINS,
    CATALOG_DOMAINS,
)


def reconcile_domain_with_filename(
    filename: str, content_domain: str | None
) -> str | None:
    """Prefer a filename entity-hint over a content guess ONLY when BOTH point
    at the SAME ambiguous group (which content-scoring cannot disambiguate).

    ``teachers_2026-01-18.csv`` whose columns scored ``students`` (shared
    name/dob/gender/email overlap) resolves to ``staff``; ``specialties_*.csv``
    scored ``academics`` (shared name/code/department) resolves to ``specialties``.
    ``student_grades.csv`` (filename hint ``students``, content ``grades``) is NOT
    overridden — ``grades`` is in no shared group with ``students``, so the columns
    are the reliable signal there. Content outside a shared group always wins.
    """
    hint = guess_domain_from_filename(filename)
    if hint and content_domain and hint != content_domain:
        for group in _AMBIGUOUS_GROUPS:
            if hint in group and content_domain in group:
                return hint
    return content_domain


def canonical_domain_label(slug: str) -> str:
    """Friendly label for a canonical domain slug (title-cased fallback)."""
    return DOMAIN_UI_LABELS.get(slug) or (slug or "").replace("_", " ").title()


def is_valid_canonical_domain(slug: str) -> bool:
    return bool(slug) and slug in DOMAIN_CANONICAL_HEADERS


def canonical_domain_choices() -> list[dict[str, str]]:
    """Ordered [{'slug','label'}] for the per-file upload domain selector."""
    return [
        {"slug": slug, "label": canonical_domain_label(slug)}
        for slug in sorted(DOMAIN_CANONICAL_HEADERS)
    ]


# A DERIVED statistics report (per-class / per-specialty aggregates: Total,
# Pass %, Passed, Male/Female breakdowns) is NOT a per-entity roster. Ingesting
# it fabricates phantom enrollment rows (one per aggregate line), so it is
# detected up front and routed to the report lander, which retains the file as
# reference and lands ZERO records.
_REPORT_FILENAME_TOKENS: tuple[str, ...] = (
    "stat", "summary", "census", "aggregate", "tally", "analytics",
)
_REPORT_STAT_HEADERS: frozenset[str] = frozenset({
    "total", "passed", "failed", "pass %", "pass%", "fail %", "best avg",
    "worst avg", "average", "male", "female", "male passed", "female passed",
    "count", "percentage", "subtotal", "grand total", "success rate", "pass rate",
})
_REPORT_MIN_STAT_HITS_WITH_NAME = 2  # magic-number-allow: report-detection threshold
_REPORT_MIN_STAT_HITS_ALONE = 4      # magic-number-allow: report-detection threshold


def is_derived_report(headers: Any, filename: str = "") -> bool:
    """True when an artifact is a DERIVED statistics report, not entity records.

    Trips when the file NAME says so (stats / summary / census) AND it carries a
    couple of aggregate columns, OR when aggregate columns dominate regardless of
    the name. A grades roster with a lone ``total`` column is NOT a report (needs
    several aggregate breakdowns), so real per-entity data still ingests.
    """
    name = (filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    fname_hit = any(tok in name for tok in _REPORT_FILENAME_TOKENS)
    norm = {(str(h) or "").strip().lower() for h in (headers or [])}
    stat_hits = len(norm & _REPORT_STAT_HEADERS)
    if fname_hit and stat_hits >= _REPORT_MIN_STAT_HITS_WITH_NAME:
        return True
    return stat_hits >= _REPORT_MIN_STAT_HITS_ALONE


def guess_domain_from_filename(filename: str) -> str:
    """Best-effort canonical domain from a filename (server-side auto-detect).

    Returns '' when nothing matches (the tagger then shows 'Auto-detect' and the
    classifier decides). Mirrors the client-side JS so a JS-off submit still gets
    a sensible default.
    """
    name = (filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    for token, domain in DOMAIN_FILENAME_HINTS:
        if token in name:
            return domain
    return ""


# Minimum canonical headers that must be present for the second-tier
# (header-only) activation to fire when the filename has been renamed.
HEADER_MATCH_MIN_HITS = 3


class RunMyCampusCanonicalAccelerator(Accelerator):
    """Accelerator for the canonical RunMyCampus template format.

    Activates when uploaded artifacts match either the canonical
    filename set or the canonical header set per domain. Pre-classifies
    each artifact with identity mappings so the mapper's AI tier never
    runs for known canonical columns.
    """

    source = "runmycampus_canonical"
    version = "1.0"

    def is_handle_supported(self, handle: Any) -> bool:
        from apps.migration_cloud.models import MigrationBundle

        if not isinstance(handle, MigrationBundle):
            return False
        # Filename signal first (cheap).
        artifact_names = {
            (name or "").strip().lower()
            for name in handle.artifacts.values_list("filename", flat=True)
        }
        if artifact_names & CANONICAL_FILENAME_TO_DOMAIN.keys():
            return True
        # Header signal second — covers renamed files.
        for artifact in handle.artifacts.all():
            domain = _domain_from_headers(artifact)
            if domain is not None:
                return True
        return False

    def execute(self, *, bundle_id: int, handle: Any) -> AcceleratorContract:
        from apps.migration_cloud.models import MigrationBundle

        if not isinstance(handle, MigrationBundle) or handle.pk != bundle_id:
            raise AcceleratorError(
                "RunMyCampus canonical accelerator requires the MigrationBundle as handle."
            )

        artifacts = list(handle.artifacts.all())
        if not artifacts:
            raise AcceleratorError("Bundle has no artifacts to accelerate.")

        contract = AcceleratorContract(bundle_id=bundle_id)
        matched = 0
        for artifact in artifacts:
            domain = _domain_for_artifact(artifact)
            if domain is None:
                continue
            canonical_headers = DOMAIN_CANONICAL_HEADERS.get(domain, set())
            # Identity mapping: every header that matches a canonical field
            # name is mapped to itself. Unknown headers stay for the mapper
            # to handle as custom_fields.
            artifact_headers = _artifact_headers(artifact)
            mappings = {h: h for h in artifact_headers if h in canonical_headers}
            contract.pre_classified_artifacts[artifact.path_within_bundle] = {
                "domain": domain,
                "canonical_mappings": mappings,
                "method": "accelerator_runmycampus_canonical",
            }
            matched += 1

        if matched == 0:
            raise AcceleratorError(
                "RunMyCampus canonical accelerator did not match any artifacts; "
                "falling back to universal pipeline."
            )

        # Common enum normalizations operators are likely to use in the
        # canonical template (English-language defaults).
        contract.vendor_enum_tables["enrollment_status"] = {
            "active": "active",
            "enrolled": "active",
            "current": "active",
            "withdrawn": "withdrawn",
            "dropped": "withdrawn",
            "graduated": "graduated",
            "inactive": "inactive",
        }
        contract.vendor_enum_tables["is_primary"] = {
            "yes": "true", "true": "true", "1": "true", "y": "true",
            "no": "false", "false": "false", "0": "false", "n": "false",
        }
        contract.notes.append(
            f"Pre-classified {matched} canonical-template artifact(s) with "
            "identity mappings; universal mapper still runs for non-canonical columns."
        )

        logger.info(
            "migration_cloud.accelerators.runmycampus_canonical: "
            "contract built for bundle %s with %d artifacts",
            bundle_id, matched,
        )
        return contract


def _artifact_headers(artifact: Any) -> set[str]:
    """Pull the lowercased canonical header set from an artifact's profile."""
    profile = getattr(artifact, "profile", None) or {}
    cols = profile.get("columns") or []
    headers = set()
    for c in cols:
        name = (c.get("name") or "").strip().lower()
        if name:
            headers.add(name)
    return headers


def _domain_from_headers(artifact: Any) -> str | None:
    """Best-matching domain based on canonical-header overlap, or None."""
    headers = _artifact_headers(artifact)
    if not headers:
        return None
    best_domain: str | None = None
    best_hits = 0
    for domain, canonical in DOMAIN_CANONICAL_HEADERS.items():
        hits = len(headers & canonical)
        if hits >= HEADER_MATCH_MIN_HITS and hits > best_hits:
            best_domain = domain
            best_hits = hits
    return best_domain


def _domain_for_artifact(artifact: Any) -> str | None:
    """Resolve an artifact to a canonical domain via filename first, then headers.

    An EXACT canonical filename (``teachers.csv``) is authoritative. Otherwise we
    score headers, then let a filename entity-token break the person-roster tie
    the columns cannot (``teachers_<timestamp>.csv`` scored ``students`` → ``staff``).
    """
    filename = ((getattr(artifact, "filename", "") or "").strip().lower())
    # A derived statistics report is caught BEFORE any roster matching so its
    # aggregate lines never land as phantom enrollment/records.
    if is_derived_report(_artifact_headers(artifact), filename):
        return "reports"
    if filename in CANONICAL_FILENAME_TO_DOMAIN:
        return CANONICAL_FILENAME_TO_DOMAIN[filename]
    return reconcile_domain_with_filename(filename, _domain_from_headers(artifact))


register_accelerator("runmycampus_canonical", RunMyCampusCanonicalAccelerator())
