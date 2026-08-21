"""
Phase G: Delta-Sync engine – apply only changed fields with updated_at conflict check.
When server has a newer version than client's base_timestamp, do not overwrite;
create a SyncConflict record and return it in results for Sync Center resolution.

Frontend MUST use tenant-scoped cache: IndexedDB key e.g. sync_queue_${school_id}
so that no cross-tenant data is ever visible (one school per device/session).
"""

import decimal as _decimal
import logging
import uuid as _uuid

from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)


# CLASS-A master-data models wired with AUTO-DERIVED syncable fields (Phase 3, staged
# to full coverage). Each MUST already carry both a ``client_offline_id`` anchor and an
# ``auto_now`` ``updated_at`` (so identity is stable across deployments and the delta
# cursor works) — verified before adding. Later slices append rows here (adding the
# anchor/timestamp schema first for models that lack it).
_DERIVED_ENTITY_SPECS: list[tuple[str, str, str]] = [
    ("applicant", "people", "Applicant"),
    ("student_note", "people", "StudentNote"),
    # Slice 2 — academic backbone (client_offline_id + updated_at added by migration).
    # term.academic_year_id references academic_year (also registered), so the derived
    # per-entity remap graph links them for new-references-new inserts.
    ("academic_year", "academics", "AcademicYear"),
    ("term", "academics", "Term"),
    ("department", "academics", "Department"),
    # Slice 3 — curriculum catalog (edge parity, 2026-08-16). Benign master data the
    # box needs to mirror the cloud: subjects, specialties (trades), and the
    # specialty↔subject curriculum links. Anchor (client_offline_id + updated_at)
    # added by academics migration 0080. FK remap: specialty.department_id →
    # department, and specialty_subject.{specialty,subject}_id → the entities below
    # (all registered), so a new-references-new insert resolves onto operator pks.
    ("specialty", "academics", "Specialty"),
    ("subject", "academics", "Subject"),
    ("specialty_subject", "academics", "SpecialtySubject"),
    # Slice 4 — the teaching grid (edge parity, 2026-08-17). SubjectAssignment is the
    # join the box needs so a term's gradeable slots exist offline: academic_year + term
    # + classroom + specialty + subject (+ coefficient). Anchor added by academics
    # migration 0081. All five FKs point at entities registered ABOVE, so a
    # new-references-new insert remaps cleanly onto the operator's pks.
    # NOTE: the `teachers` M2M does NOT ride — it targets the SHARED accounts.User,
    # whose pk is not portable box↔cloud (the same reason a FK to User is excluded), and
    # an M2M cannot appear in `save(update_fields=...)`. `_derive_sync_fields` drops it.
    ("subject_assignment", "academics", "SubjectAssignment"),
    # Slice 5 — grades, DOWN-ONLY (edge parity, 2026-08-17). evals.Evaluation is the mark
    # row. It is deliberately NOT in _LWW_SAFE_ENTITIES: `evaluation` aliases to the
    # protected `grade_entry` policy, so _conflict_decision applies it on a cloud-pull and
    # raises a Sync Center CONFLICT for a box push — a box can never silently overwrite a
    # mark the cloud holds. Anchor added by evals migration 0039 (it already had
    # updated_at). Its subject_assignment_id resolves onto the entity registered directly
    # above, which is why the teaching grid had to land first; student_id resolves onto
    # `student`. created_by/updated_by are FKs to the SHARED accounts.User and are dropped
    # automatically as non-portable.
    ("evaluation", "evals", "Evaluation"),
    # Slice 6 — finance, DOWN-ONLY and DELIBERATELY PARTIAL (edge parity, 2026-08-17).
    # Only the Invoice rides: the box learns what is OWED so a bursar can work through an
    # outage, and the protected `invoice` policy means it can never push a money change
    # back up. Its FileFields (attachment, payment_proof) are dropped by the FileField
    # guard — the bundle carries no bytes, so a synced path would dangle.
    #
    # finance.Payment and finance.PaymentProofUpload are HELD OUT, not overlooked:
    #   * neither has an `updated_at` column at all, so the incremental delta cannot even
    #     query them (`filter(updated_at__gt=since)` -> FieldError). Adding auto_now to the
    #     money ledger changes write behaviour on the platform's most sensitive tables.
    #   * Payment carries live settlement state (gateway_transaction_id, gateway_response,
    #     completed_at, failed_at), and POLICIES already declares `payment_settlement`
    #     ONLINE_REQUIRED — "executing a charge against a gateway is a live transaction".
    #     Putting that on a sync rail would contradict the platform's own rule.
    # Rationale + the conditions to revisit: docs/EDGE_SYNC_FINANCE_HOLD.md.
    ("invoice", "finance", "Invoice"),
    # Slice 7 — staff identity, MIXED DIRECTION (edge parity, 2026-08-17). people.
    # TeacherProfile is the staff master record. It was deferred while per-field direction
    # policy was a single-field seed; now that the policy is general AND enforced on the
    # insert path as well as the update path, the profile can converge two-way while
    # COMPENSATION rides down-only (see _DOWN_ONLY_FIELDS_PER_ENTITY["teacher"]). A
    # bursar's salary edit on the cloud reaches the box; a stale box can never move pay.
    #
    # IDENTITY (the reason this was the hard one). `user` is a non-nullable OneToOneField
    # to the SHARED accounts.User, whose pk differs box↔cloud, so `_derive_sync_fields`
    # already drops `user_id` as non-portable — verified by running it, not assumed. The
    # consequence is asymmetric and deliberate:
    #   * UPDATE of an existing profile is safe and is what this registration buys. The
    #     clone is pk-preserving, so the row matches by pk on both sides and each side
    #     keeps its OWN user link untouched.
    #   * INSERT of a box-created teacher is REFUSED, not attempted (see
    #     _INSERT_HELD_ENTITIES). Landing one would require the sync rail to mint an
    #     accounts.User on the cloud, and provisioning a login is an authentication
    #     decision — who may sign in, with what role, under whose authorization — not a
    #     data merge. A rail that creates identities is a rail that can grant access.
    # Rationale + the conditions to revisit: docs/EDGE_SYNC_IDENTITY_HOLD.md.
    ("teacher", "people", "TeacherProfile"),
    # Slice 8 — the tenant's own sync schedule (2026-08-20). The only entity on this rail
    # that is ABOUT the rail: it tells the box when to run a cycle.
    #
    # It has to ride the rail because of the NAT asymmetry. The cloud can never open a
    # connection to a box, so "the cloud triggers a sync at 09:00" is not implementable —
    # at 09:00 nobody is going to tell the box anything. The schedule is therefore
    # replicated like any other row and EVALUATED LOCALLY against the box's own copy,
    # which is also what keeps it working while the cloud is unreachable. A box that has
    # never pulled one runs the default.
    #
    # Consequence stated plainly rather than hidden: a schedule change reaches the box on
    # its NEXT cycle, not instantly. The Sync Center says so in those words.
    #
    # Unlike every other spec here this model lives in a SHARED app (sync_engine), which
    # the rail handles without a special case: `school` is excluded from the derived field
    # set and the delta builder scopes by `school_id`, so what actually matters is the
    # anchor + `updated_at`, and SyncSchedule carries both.
    ("sync_schedule", "sync_engine", "SyncSchedule"),
]

# Entities that sync as UPDATES but whose offline-CREATED rows are refused outright.
# Distinct from "not registered at all": the entity converges, but a NEW row cannot be
# manufactured on the far side because something non-data (here, an identity/login) would
# have to be invented to satisfy a required non-portable relation. Refusing explicitly
# beats letting the insert reach the database and die on an IntegrityError every cycle,
# which reports a confusing constraint error instead of the actual reason.
_INSERT_HELD_ENTITIES: dict[str, str] = {
    "teacher": (
        "a teacher record requires an accounts.User, and provisioning a login is an "
        "authentication decision the sync rail must not make; create the staff member on "
        "the cloud and the profile will sync down"
    ),
}

# Field names never synced as a value: the tenant scope, the identity anchor, and the
# auto timestamps (handled by the engine, not carried as data).
_SYNC_FIELD_EXCLUDE_NAMES = {"school", "client_offline_id", "created_at", "updated_at"}

# Per-entity fields REMOVED from the auto-derived sync set. These are ordinary editable
# scalars, but they are cloud-governance columns that must NOT converge by two-way LWW —
# a stale offline box edit must never silently override the cloud's value. Until per-field
# direction policy exists (the same gap that defers TeacherProfile compensation), the safe
# move is to keep them OFF the sync rail entirely:
#   * academic_year.is_locked / enable_gce_registration — the year-end lock and the exam-
#     registration gate (MEMORY M29). A box must never be able to reopen a year the cloud
#     locked; the cloud owns these. (The academic_year still syncs its benign fields.)
_SYNC_FIELD_EXCLUDE_PER_ENTITY: dict[str, set] = {
    "academic_year": {"is_locked", "enable_gce_registration"},
}

# Per-FIELD direction policy: columns that ride DOWN (cloud→box) but are NEVER accepted
# UPWARD, on an entity that is otherwise benign two-way LWW. `_conflict_decision` grades a
# whole ENTITY, so a single cloud-governed column previously had only two bad options —
# leave the entity two-way (a stale box can move it) or drop the column off the rail
# entirely (the box never receives it, so it cannot compute correctly offline). This gives
# the third, correct option: the box RECEIVES the cloud's value, and an upward write to it
# is refused and REPORTED rather than silently discarded.
#   * subject_assignment.coefficient — the per-subject weight that multiplies a mark into
#     the term average and the report card. Marks themselves are down-only (the protected
#     grade_entry policy), so letting a stale box overwrite the WEIGHT would move every
#     computed average by the back door while each individual mark stayed authoritative.
#     The box still needs the value to grade offline, so excluding it is not an option.
#   * teacher.<compensation> — pay grade, pay scale, salary, salary cap, pay date and
#     paystub text. Payroll is cloud-authoritative for the same reason money is: it is
#     computed and approved centrally, and a box that has been offline for a week holds a
#     stale figure. The box still RECEIVES the current values so a head teacher can see
#     accurate staffing costs offline; it simply cannot push a pay change up.
#     `payment_method` rides down-only too — it decides where money is SENT, so a box edit
#     to it is a payment-redirection vector, not a profile preference.
#   * teacher.allow_finance_panel / allow_paystub_access / allow_leave_approvals — these
#     read like preferences and are NOT: `allow_finance_panel` is the gate on the teacher
#     payroll block (PayrollEmployee, payslips, net pay — apps/portal/services.py
#     ::_teacher_finance_block), and `allow_leave_approvals` confers approval authority. A
#     box able to push these upward could grant payroll visibility or approval rights on
#     the cloud. POLICIES already states the rule for this class — `permission_grant` is
#     SERVER_AUTHORITATIVE because "authorization changes must be validated by the server"
#     — so these follow it.
#   * teacher.is_active / merged_into_id — offboarding and duplicate-merge are governance
#     actions, not roster edits. A stale box must not reinstate a staff member the cloud
#     deactivated, nor redirect a merge pointer.
#
# ENFORCEMENT IS ON EVERY INBOUND PATH. Direction is a property of the FIELD, so both
# _apply_changes_inner (update-by-pk) and apply_edge_inserts (upsert-by-client_offline_id)
# apply this map. Guarding only the update path made the whole policy bypassable by
# presenting an edit as a new row.
#
# A field listed here must also be in the entity's synced set — it is a direction rule, not
# an exclusion. Use it (rather than _SYNC_FIELD_EXCLUDE_PER_ENTITY) whenever the box needs
# to READ the value to behave correctly offline.
_DOWN_ONLY_FIELDS_PER_ENTITY: dict[str, set] = {
    "subject_assignment": {"coefficient"},
    "teacher": {
        # compensation
        "pay_grade",
        "pay_scale_id",
        "salary_amount",
        "salary_cap",
        "next_pay_date",
        "paystub_notes",
        "payment_method",
        # authorization
        "allow_finance_panel",
        "allow_paystub_access",
        "allow_leave_approvals",
        # governance
        "is_active",
        "merged_into_id",
    },
}

# Registered entities that are SAFE to converge by last-writer-wins and are NOT already
# classified in policy_registry.POLICIES. Kept EXPLICIT (not derived from the registry) so
# that adding a new entity to _DERIVED_ENTITY_SPECS without consciously listing it here —
# or giving it a POLICIES entry — makes _sync_conflict_policy fail CLOSED (protected
# manual review) rather than silently treating a possibly-sensitive entity as two-way LWW.
# When you add a benign master-data entity, add it here; a money/grade/identity entity must
# instead get a protected POLICIES row.
_LWW_SAFE_ENTITIES = frozenset(
    {
        "student", "classroom", "applicant", "academic_year", "term", "department",
        # Curriculum catalog (Slice 3): benign master data, safe to converge by
        # timestamp — a later admin edit wins, same as the other master-data rows.
        "specialty", "subject", "specialty_subject",
        # Teaching grid (Slice 4): benign master data — WHICH gradeable slots exist for a
        # term. It carries no marks (an Evaluation points AT a slot; grades ride their own
        # down-only rail), so a later admin edit winning is correct.
        "subject_assignment",
        # Staff roster (Slice 7): LWW-safe *because* the sensitive columns are handled by
        # per-FIELD direction rather than entity-level protection. What converges two-way
        # is genuinely benign roster/preference data — staff_id, phone, position_title,
        # department, reports_to, custom_attributes, dashboard + reminder preferences. Pay,
        # authorization and governance columns are in _DOWN_ONLY_FIELDS_PER_ENTITY, and a
        # box-created teacher is refused outright (_INSERT_HELD_ENTITIES). Marking the
        # whole entity protected instead would make every offline phone-number correction a
        # manual conflict while buying no additional safety.
        "teacher",
        # Sync schedule (Slice 8): the tenant's own configuration, on the tenant's own
        # deployment, so a later edit winning is exactly right — and it is the behaviour a
        # sovereign box needs, where the administrator may be sitting in front of the box
        # rather than the cloud. Nothing here grants access, moves money or changes a
        # mark; the worst a stale write can do is sync at the wrong time, which the next
        # edit corrects. Protecting it instead would turn every schedule change made
        # during an outage into a manual conflict for no safety gain.
        "sync_schedule",
    }
)


def _is_sync_tenant_model(model) -> bool:
    """True if ``model`` lives in a tenant app — so its pk is stable across the
    pk-preserving clone (or remappable when it is itself a synced entity). A FK to a
    SHARED/public model (e.g. ``accounts.User``) is NOT: its id differs box vs cloud, so
    such a link is never synced as a field."""
    if model is None:
        return False
    from apps.lifecycle.tenant_portability import TENANT_APP_LABELS

    return model._meta.app_label in TENANT_APP_LABELS


def _derive_sync_fields(model) -> set:
    """The syncable field set for a CLASS-A model: every editable concrete scalar plus
    FKs that point at a TENANT model (pk-stable / remappable). Excludes the pk, the
    tenant scope, the anchor, auto timestamps, and any FK to a shared/public model."""
    fields: set = set()
    for f in model._meta.get_fields():
        if not getattr(f, "concrete", False) or getattr(f, "primary_key", False):
            continue
        if getattr(f, "auto_created", False) or not getattr(f, "editable", True):
            continue
        if getattr(f, "auto_now", False) or getattr(f, "auto_now_add", False):
            continue
        if f.name in _SYNC_FIELD_EXCLUDE_NAMES:
            continue
        # MANY-TO-MANY IS NEVER A SYNCED FIELD. Django reports an M2M as concrete+editable,
        # so without this guard it lands in the set and breaks BOTH directions: the outbox
        # does ``getattr(instance, f)`` per allowed field, which for an M2M yields a
        # ManyRelatedManager that ``export_delta_bundle`` cannot JSON-serialize — and
        # because a bundle packs EVERY registered entity into ONE payload, that single bad
        # column takes down the whole push/pull cycle, not just its own entity. On the
        # inbound side an M2M cannot appear in ``save(update_fields=[...])`` either
        # (FieldError — the same phantom-field crash the curated ``classroom`` set warns
        # about above). A through-table link is its own relation and, when one is genuinely
        # needed on the rail, must be registered as its own entity with its own anchor.
        if getattr(f, "many_to_many", False):
            continue
        # A FileField/ImageField NEVER rides either. A delta bundle carries column VALUES
        # only — never file bytes — so shipping the stored path would point the box at a
        # file that does not exist on it, and the apply would report a clean 200 over a
        # broken reference. Files must travel by their own upload/artifact channel. This is
        # latent today (only `student` owns one, and it keeps a CURATED field set) but every
        # finance candidate — Invoice.attachment/payment_proof, Payment.receipt_file,
        # PaymentProofUpload.receipt_file — would hit it the moment money joins the rail.
        from django.db.models import FileField

        if isinstance(f, FileField):
            continue
        if getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False):
            # Resolve a possibly lazy-string related_model to its class first (same guard
            # tenant_portability._rel_model adds) so a string ref never AttributeErrors here.
            from apps.lifecycle.tenant_portability import _rel_model

            if not _is_sync_tenant_model(_rel_model(f)):
                continue  # FK to User/other shared model — id not portable across deployments
            fields.add(f.attname)  # sync the <name>_id
        else:
            fields.add(f.name)
    return fields


def _get_entity_config(include_derived=False):
    from apps.people.models import StudentProfile
    from apps.academics.models import Attendance, Classroom
    from django.apps import apps as django_apps

    # The original three entities keep their CURATED field sets verbatim, so their
    # long-tested sync behaviour is unchanged by the generalized registry.
    config = {
        "student": (
            StudentProfile,
            {
                "first_name",
                "last_name",
                "student_code",
                "classroom_id",
                "academic_year_id",
                "specialty_id",
                "status",
                "is_active",
            },
        ),
        "attendance": (
            Attendance,
            {"student_id", "classroom_id", "date", "status", "remarks"},
        ),
        # NOTE: no "is_active" — Classroom has no such field. Leaving the phantom in
        # would crash the UPDATE path (`save(update_fields=["is_active"])` → FieldError)
        # whenever a classroom edit carried it.
        #
        # `department_id` and `code` are on the set because without them a classroom can
        # never be CREATED across the boundary in EITHER direction — found by running the
        # insert, 2026-08-20: `Classroom.department` is NOT NULL and `code` is a required
        # UNIQUE column, so an insert carrying only {name, academic_year_id} dies on
        # `NOT NULL constraint failed: academics_classroom.department_id`, and a second one
        # would then collide on `code=""`. The practical effect was that a class created on
        # the cloud in September simply did not exist on the appliance, and a class created
        # offline could never be pushed up. Both are FKs/scalars to already-registered
        # benign master data, so they remap and converge like every other classroom field.
        # The exam/term governance booleans (gce_eligible, allows_third_term) deliberately
        # stay OFF the rail — those decide who may be registered for a certification exam,
        # which is the same class of cloud-governed switch as
        # academic_year.enable_gce_registration.
        "classroom": (Classroom, {"name", "academic_year_id", "department_id", "code"}),
    }
    # The expanded two-way registry is scoped to EDGE SYNC operations only — callers on
    # the edge push/pull paths pass include_derived=True. An ordinary online DeltaSyncAPI
    # request (sync_origin is None) NEVER includes them, so every other tenant, on ANY
    # deployment (including a shared cloud that also serves edge boxes), sees exactly the
    # original three entities. Isolation therefore does not depend on a deployment-global
    # switch — an unregistered/derived entity from a non-edge caller is simply rejected.
    if include_derived:
        for entity_type, app_label, model_name in _DERIVED_ENTITY_SPECS:
            try:
                model = django_apps.get_model(app_label, model_name)
            except LookupError:
                continue
            fields = _derive_sync_fields(model) - _SYNC_FIELD_EXCLUDE_PER_ENTITY.get(
                entity_type, set()
            )
            config[entity_type] = (model, fields)
    return config


# Which Django app owns each synced entity. The schema handshake (G4) degrades to a
# COMPATIBLE SUBSET rather than refusing a whole cycle, and this is what makes "subset"
# expressible: a box behind only on `finance` still receives its attendance. Derived from
# the same specs the registry is built from, plus the three curated entities, so a new
# entity cannot be added without its app being known here.
_CURATED_ENTITY_APPS = {
    "student": "people",
    "attendance": "academics",
    "classroom": "academics",
}


def entity_app_labels() -> dict:
    """``{entity_type: app_label}`` for every entity on the edge rail."""
    labels = dict(_CURATED_ENTITY_APPS)
    for entity_type, app_label, _model_name in _DERIVED_ENTITY_SPECS:
        labels[entity_type] = app_label
    return labels


def _insert_fk_targets(config) -> dict:
    """``{entity_type: {fk_attname: target_entity_type}}`` for FKs (in each entity's
    synced field set) that point at ANOTHER registered entity — so a new-references-new
    insert can be remapped onto the referent's operator pk. Derived PER ENTITY, so a
    field name that resolves to different targets on different models (e.g.
    ``merged_into_id`` on student vs teacher) is never conflated by a global map."""
    model_to_entity = {model: et for et, (model, _f) in config.items()}
    targets: dict = {}
    for et, (model, allowed) in config.items():
        per_entity: dict = {}
        for f in model._meta.get_fields():
            if not (getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False)):
                continue
            if not getattr(f, "concrete", False):
                continue
            attname = getattr(f, "attname", None)
            if attname not in allowed:
                continue
            from apps.lifecycle.tenant_portability import _rel_model

            target_et = model_to_entity.get(_rel_model(f))
            if target_et and target_et != et:
                per_entity[attname] = target_et
        targets[et] = per_entity
    return targets


def _fk_reference_targets(model, allowed) -> dict:
    """``{fk_attname: target_model}`` for every concrete FK inside ``allowed``.

    Deliberately broader than :func:`_insert_fk_targets`, which maps only the FKs pointing
    at ANOTHER REGISTERED entity because its job is remapping new-references-new pks.
    Referential integrity is not scoped to the rail: a pulled row can just as easily point
    at a parent living in a table sync never carries, and the database rejects that with
    exactly the same constraint error. Every FK that carries a value has to be checked.
    """
    from apps.lifecycle.tenant_portability import _rel_model

    targets: dict = {}
    for f in model._meta.get_fields():
        if not getattr(f, "concrete", False):
            continue
        if not (getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False)):
            continue
        attname = getattr(f, "attname", None)
        if attname in allowed:
            targets[attname] = _rel_model(f)
    return targets


def enrich_delta_rows_with_fk_referents(rows, school, config) -> list:
    """Attach referent rows referenced by FK fields so a box can apply dependents.

    Delta bundles normally ship only rows with ``updated_at > since``. A specialty
    edit therefore rides alone while its unchanged department does not — on a box
    that never received that department (sovereign seed without pk alignment), the
    apply dies on the FK. Pulling the referent's current snapshot closes the gap.

    When a referent cannot be resolved for this school at all, the CHILD is dropped
    rather than shipped with a reference the box can never satisfy — see the inline
    note at the lookup. One residual case is not chased here: a child whose parent
    is present in the bundle but is itself dropped. That is bounded, not fatal —
    ``_force_immediate_constraints`` makes the box isolate such a row per-row
    instead of failing the whole pull — and it self-heals on the next cycle.
    """
    if not rows:
        return rows
    fk_targets = _insert_fk_targets(config)
    present = {
        ((r.get("entity_type") or "").strip().lower(), r.get("id"))
        for r in rows
        if r.get("id") is not None
    }
    extras: list[dict] = []
    undeliverable: set[int] = set()
    for index, row in enumerate(rows):
        entity_type = (row.get("entity_type") or "").strip().lower()
        if entity_type not in config:
            continue
        for fk_field, target_et in fk_targets.get(entity_type, {}).items():
            fk_val = (row.get("changes") or {}).get(fk_field)
            if fk_val is None:
                continue
            key = (target_et, fk_val)
            if key in present:
                continue
            target_model, allowed = config[target_et]
            # Match the school's OWN rows and unowned/global ones, but never
            # another tenant's. ``school`` is nullable on several academics models
            # (Department.school is null=True), and production carries real rows
            # with school_id NULL -- e.g. Department pk=2 ("Science", SCI-2425).
            # A strict ``school=school`` lookup can never match those, so every
            # child pointing at an unowned parent looked unresolvable: before the
            # drop below existed it shipped dangling and killed the pull, and with
            # the drop alone it would silently never sync at all. Widening to
            # "mine OR unowned" ships the parent the box actually needs while
            # still refusing a parent owned by a DIFFERENT school.
            from django.db.models import Q

            ref = (
                target_model._default_manager.filter(pk=fk_val)
                .filter(Q(school=school) | Q(school__isnull=True))
                .first()
            )
            if ref is None:
                # The parent cannot be supplied to the box AT ALL -- it is absent
                # for this school (deleted, or owned by a different tenant, since
                # the lookup is school-scoped). Shipping the child anyway is what
                # produced the production failure: the box wrote a row pointing at
                # a parent it would never receive, and because Django defers FK
                # checks on Postgres the violation surfaced at COMMIT and took the
                # WHOLE pull with it -- every cycle, forever, because the cursor
                # never advanced. Dropping one unshippable child instead costs that
                # single row and lets the rest of the bundle land; it self-heals
                # the moment the parent becomes syncable.
                undeliverable.add(index)
                logger.warning(
                    "sync: dropping %s id=%s from bundle -- FK %s=%s has no "
                    "syncable %s for school %s",
                    entity_type, row.get("id"), fk_field, fk_val, target_et,
                    getattr(school, "pk", school),
                )
                continue
            extras.append(
                {
                    "entity_type": target_et,
                    "id": ref.pk,
                    "client_offline_id": getattr(ref, "client_offline_id", "") or "",
                    "changes": {
                        f: getattr(ref, f)
                        for f in sorted(allowed)
                        if hasattr(ref, f)
                    },
                    "updated_at": (
                        ref.updated_at.isoformat()
                        if getattr(ref, "updated_at", None)
                        else None
                    ),
                }
            )
            present.add(key)
    if undeliverable:
        rows = [r for i, r in enumerate(rows) if i not in undeliverable]
    if not extras:
        return rows
    order = _insert_dependency_order(config)

    def _rank(row):
        et = (row.get("entity_type") or "").strip().lower()
        return order.index(et) if et in order else len(order)

    combined = extras + rows
    combined.sort(key=lambda r: (_rank(r), r.get("updated_at") or ""))
    return combined


def _unresolvable_fk(model, allowed, payload, seen=None):
    """The first FK in ``payload`` whose parent row is absent - ``(attname, label, value)``.

    ``None`` when every reference resolves. ``seen`` is a caller-owned memo
    ``{(label, pk): bool}``: one bundle repeats the same handful of parents across hundreds
    of rows, so without it this would issue a query per FK per row.

    THE CHECK HAS TO HAPPEN BEFORE THE WRITE, because on PostgreSQL it cannot be caught
    after it. Django creates every foreign key as DEFERRABLE INITIALLY DEFERRED, so a
    violation is not raised by ``save()`` - it is raised by the COMMIT of the OUTERMOST
    transaction, long after the per-row savepoint written to contain it has been released.
    The whole bundle then dies together and the error escapes ``apply_changes`` entirely,
    surfacing as a cycle-level ``pull failed: ...``. SQLite checks immediately, which is
    precisely why the test suite never saw this and production did.

    Uses ``_base_manager``: the constraint cares whether the ROW exists, not whether a
    model's default manager chooses to show it (a soft-deleted parent still satisfies it).
    """
    if seen is None:
        seen = {}
    try:
        targets = _fk_reference_targets(model, allowed)
    except Exception:  # noqa: BLE001 - see below; a preflight must never be the crash
        logger.debug("could not derive FK targets for %s", model, exc_info=True)
        return None
    for attname, target_model in targets.items():
        if attname not in payload:
            continue
        value = payload[attname]
        if value is None:
            continue
        try:
            label = target_model._meta.label
            key = (label, value)
            exists = seen.get(key)
            if exists is None:
                exists = target_model._base_manager.filter(pk=value).exists()
                seen[key] = exists
        except Exception:  # noqa: BLE001
            # The lookup ITSELF failed — typically a value the pk column cannot even parse
            # (a string where a UUID/int is expected), which Django raises as
            # ValueError/ValidationError. Treat it as unresolvable rather than letting it
            # propagate: a preflight that can crash the bundle would reintroduce the exact
            # failure it exists to prevent.
            logger.debug("FK preflight lookup failed for %s.%s", model, attname, exc_info=True)
            return (attname, getattr(target_model._meta, "label", str(target_model)), value)
        if not exists:
            return (attname, label, value)
    return None


def check_constraints_immediately() -> None:
    """Switch PostgreSQL's deferred foreign-key checks to statement time.

    Kept as the strict, directly testable primitive. SQLite and other backends already
    enforce their own constraint timing and must not receive PostgreSQL-only SQL.
    """
    from django.db import connection

    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def _force_immediate_constraints():
    """Make deferred FK checks fire at statement time for the rest of this transaction.

    Django creates every foreign key on PostgreSQL as DEFERRABLE INITIALLY DEFERRED, so a
    violation surfaces at COMMIT instead of at ``save()``. That silently defeats every
    per-row savepoint in this module - they release cleanly, and the error then takes down
    the entire batch from OUTSIDE the handlers written to contain it. Switching the
    transaction to IMMEDIATE restores the behaviour those savepoints were always documented
    to provide: one un-appliable row degrades to a per-row status and the rest still lands.

    Belt to :func:`_unresolvable_fk`'s braces. The preflight prevents the case we understand;
    this bounds the blast radius of the one we have not thought of yet. No-op on backends
    that already check immediately (SQLite) or that lack SET CONSTRAINTS.
    """
    try:
        check_constraints_immediately()
    except Exception:  # noqa: BLE001
        logger.warning("could not switch FK constraints to IMMEDIATE", exc_info=True)


def _create_from_cloud_pull(
    school_id, user, entity_type, model, allowed, pk, changes, client_updated_at, fk_seen
):
    """Create a cloud-authored row on the box, PRESERVING the operator's pk.

    Cloud->box had no create path at all. A cloud-authored row carries an EMPTY
    ``client_offline_id`` (that column marks rows created offline ON A BOX), so
    :func:`apps.sync_engine.edge_inbox.apply_pulled_bundle` routes it to the update-by-pk
    path - which answered 404 and moved on. The practical effect: every record created on
    the cloud AFTER a box was cloned could never reach that box. Departments, subjects,
    specialties, terms, classrooms, all of it. Nothing reported a problem; the box quietly
    diverged, and then failed outright on the first child row that referenced one of the
    parents it had never been given.

    Creating BY PK is correct in this direction and only this direction: the clone is
    pk-preserving, the cloud is authoritative on a pull, and the pk being absent locally is
    exactly what the caller just established. The reverse - a box minting pks on the
    operator - stays refused; that is what ``client_offline_id`` and
    :func:`apply_edge_inserts` exist for.

    Returns ``(instance, None)`` or ``(None, {"status": int, "data": {...}})``.
    """
    from django.core.exceptions import FieldError, ValidationError
    from django.db import (
        DataError,
        IntegrityError,
        OperationalError,
        ProgrammingError,
        transaction,
    )

    from apps.api.entity_api import _is_admin_like

    # A create is a WRITE, so it answers to the same two gates every other inbound write
    # does. Skipping them because there is no existing row to compare against would make
    # this path the way AROUND them.
    #
    # 1) PRINCIPAL. Same bar as apply_edge_inserts: the box acts as a bound school admin.
    if not (
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or _is_admin_like(user)
    ):
        return None, {"status": 403, "data": {"error": "forbidden"}}

    # 2) POLICY. `_conflict_decision` with no server row still answers the question that
    #    matters here: an ONLINE_REQUIRED domain (credentials, lifecycle, payment
    #    settlement) is NEVER applied through the sync path, and that must hold whether the
    #    row already exists or not. Protected entities resolve to "apply" on a cloud-pull,
    #    which is the money = cloud-authoritative rule working as intended.
    decision = _conflict_decision(entity_type, "cloud-pull", client_updated_at, None)
    if decision != "apply":
        return None, {
            "status": 409,
            "data": {"error": "online_required" if decision == "reject" else decision,
                     "entity_type": entity_type},
        }

    if entity_type in _INSERT_HELD_ENTITIES:
        # The same rule the box-push insert path applies: an entity that must not be CREATED
        # across the rail is refused with its reason, in EITHER direction.
        return None, {
            "status": 409,
            "data": {
                "error": "insert_held_for_entity",
                "entity_type": entity_type,
                "reason": _INSERT_HELD_ENTITIES[entity_type],
            },
        }

    settable = _settable_field_names(model)
    values = {k: v for k, v in changes.items() if k in allowed and k in settable}
    missing = _unresolvable_fk(model, allowed, values, fk_seen)
    if missing is not None:
        return None, {
            "status": 409,
            "data": {
                "error": "missing_reference",
                "field": missing[0],
                "references": missing[1],
                "referenced_id": missing[2],
            },
        }
    values[model._meta.pk.attname] = pk
    if any(getattr(f, "attname", "") == "school_id" for f in model._meta.get_fields()):
        values["school_id"] = school_id
    try:
        with transaction.atomic():  # savepoint: a row we cannot build must not kill the batch
            instance = model(**values)
            instance.save(force_insert=True)
    except (
        IntegrityError, DataError, ValidationError, ValueError, TypeError, FieldError,
        OperationalError, ProgrammingError,  # a column this schema does not have yet
    ) as exc:
        # Usually a NOT NULL column that is not on the rail, so the bundle carried no value
        # for it. Reported per row rather than raised, so the rest of the pull still lands.
        return None, {"status": 422, "data": {"error": "create_failed", "detail": str(exc)[:200]}}
    return instance, None


def _reassert_row_after_refused_delete(model, school_id, pk):
    """Bump ``updated_at`` on a row whose DELETION this side refused.

    Without this, refusing a delete guarantees permanent divergence: the appliance has
    already removed the row locally, the cloud keeps it, and because the cloud copy's
    ``updated_at`` is older than the box's pull cursor the incremental delta will never
    offer it again. The row would be gone on one side and present on the other, forever,
    with nothing reporting a problem.

    Touching the timestamp puts the row back INSIDE the next pull window, where the
    cloud-authored create path lands it again by pk. The cloud is not accepting the box's
    change - it is re-asserting its own row, which is exactly what "money is
    cloud-authoritative" means.

    Uses ``.update()`` deliberately: it writes the column directly, without running
    ``auto_now``, signals, or model save hooks, so re-asserting a row can never fire
    another tombstone or a business side effect. Never raises.
    """
    if not any(getattr(f, "attname", "") == "updated_at" for f in model._meta.get_fields()):
        return False
    try:
        qs = model._base_manager.filter(pk=pk)
        if any(getattr(f, "attname", "") == "school_id" for f in model._meta.get_fields()):
            qs = qs.filter(school_id=school_id)
        return bool(qs.update(updated_at=timezone.now()))
    except Exception:  # noqa: BLE001 - a repair step must never break the batch
        logger.debug("could not re-assert %s:%s after a refused delete", model, pk, exc_info=True)
        return False


def apply_deletes(school_id, user, rows, *, sync_origin=None):
    """Apply DELETION rows (``op="delete"``) from a delta bundle.

    The third inbound path, alongside :func:`apply_changes` (update-by-pk) and
    :func:`apply_edge_inserts` (upsert-by-anchor). Until it existed a deletion was the
    one change the engine could not carry at all - see
    :mod:`apps.sync_engine.tombstones`.

    A delete is a WRITE, so it answers to every gate a write answers to:

      * **principal** - the same admin-like bar the insert path applies;
      * **policy** - via :func:`_conflict_decision`, so an ONLINE_REQUIRED domain is
        never deleted through the sync rail, and a protected (money / grade / identity)
        entity may be deleted DOWNWARD by the cloud but never UPWARD by a box. A refused
        upward delete re-asserts the cloud row so the appliance gets it back rather than
        the two sides diverging in silence;
      * **flood guard** - a bundle carrying more than
        ``RMC_SYNC_MAX_DELETES_PER_BUNDLE`` deletions is refused WHOLE. A mistaken bulk
        action on one side is then a loud refusal instead of a mirrored wipe.

    A tombstone is recorded on this side even when the row is already absent: knowing a
    row is buried is what stops it being re-created by a later bundle, and it is what
    makes delete-dominance answer the same way regardless of which side is asked first.

    Returns ``{"deleted", "results"}``; results carry per-row ``index``/``status``.
    """
    from django.core.exceptions import FieldError, ValidationError
    from django.db import (
        DataError,
        IntegrityError,
        OperationalError,
        ProgrammingError,
        transaction,
    )

    from apps.api.entity_api import _is_admin_like
    from apps.sync_engine import tombstones

    rows = list(rows or [])
    config = _get_entity_config(include_derived=sync_origin is not None)
    can_delete = bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or _is_admin_like(user)
    )
    if not school_id or not can_delete:
        reason = "tenant_context_required" if not school_id else "forbidden"
        return {
            "deleted": 0,
            "results": [
                {"index": i, "status": 403, "data": {"error": reason}}
                for i, _ in enumerate(rows)
            ],
        }
    if not tombstones.delete_propagation_enabled():
        return {
            "deleted": 0,
            "results": [
                {"index": i, "status": 409, "data": {"error": "delete_propagation_disabled"}}
                for i, _ in enumerate(rows)
            ],
        }

    cap = tombstones.max_deletes_per_bundle()
    if len(rows) > cap:
        # Refused WHOLE, on purpose. Applying the first `cap` and refusing the rest would
        # be the worst of both: a partial wipe plus an error. The far side keeps its
        # tombstones, so once an operator has decided the deletions are intended, raising
        # the cap (or a full resync) applies them - nothing is lost by refusing.
        return {
            "deleted": 0,
            "results": [
                {
                    "index": i,
                    "status": 409,
                    "data": {
                        "error": "delete_flood_guard",
                        "count": len(rows),
                        "max_deletes": cap,
                    },
                }
                for i, _ in enumerate(rows)
            ],
        }

    deleted = 0
    results: list[dict] = []
    for idx, item in enumerate(rows):
        entity_type = (item.get("entity_type") or "").strip().lower()
        pk = item.get("id")
        coid = (item.get("client_offline_id") or "").strip()
        deleted_at = _parse_client_updated_at(item.get("updated_at")) or timezone.now()

        if entity_type not in config or (pk is None and not coid):
            results.append(
                {"index": idx, "status": 400, "data": {"error": "entity_type_and_id_required"}}
            )
            continue
        model, _allowed = config[entity_type]

        decision = _conflict_decision(entity_type, sync_origin, deleted_at, None)
        if decision == "reject":
            results.append(
                {
                    "index": idx,
                    "status": 409,
                    "data": {"error": "online_required", "entity_type": entity_type},
                }
            )
            continue
        if decision == "conflict":
            # Protected entity, deletion travelling the wrong way. Refuse it AND put the
            # row back in the far side's next window, or the sides diverge for good.
            reasserted = _reassert_row_after_refused_delete(model, school_id, pk)
            results.append(
                {
                    "index": idx,
                    "status": 409,
                    "data": {
                        "error": "delete_refused_protected",
                        "entity_type": entity_type,
                        "reasserted": reasserted,
                    },
                }
            )
            continue

        # Record the burial FIRST. If the delete below fails we still know the row is
        # meant to be gone, so a later bundle cannot quietly re-create it; and a row that
        # is already absent locally still needs the tombstone for exactly that reason.
        tombstones.record_tombstone(
            school_id,
            entity_type,
            pk if pk is not None else coid,
            deleted_at=deleted_at,
            client_offline_id=coid,
            origin=sync_origin or "",
        )

        try:
            with transaction.atomic():  # savepoint: one undeletable row must not kill the batch
                qs = model._base_manager.all()
                if any(
                    getattr(f, "attname", "") == "school_id" for f in model._meta.get_fields()
                ):
                    qs = qs.filter(school_id=school_id)
                target = qs.filter(pk=pk).first() if pk is not None else None
                if target is None and coid:
                    target = qs.filter(client_offline_id=coid).first()
                if target is None:
                    results.append(
                        {"index": idx, "status": 200, "data": {"deleted": False, "already_absent": True}}
                    )
                    continue
                target_pk = target.pk
                with tombstones.applying_remote_delete():
                    # The INSTANCE's delete(), never a queryset delete. Several models
                    # here override it - finance.Invoice soft-deletes for legal
                    # traceability rather than removing the row - and a queryset delete
                    # would silently bypass that override and hard-delete a record the
                    # product deliberately keeps. The sync rail does not get to overrule a
                    # model's own deletion semantics.
                    target.delete()
                if model._base_manager.filter(pk=target_pk).exists():
                    # The model SOFT-deleted: the row is still there, marked void. It is
                    # not a deletion the far side needs a tombstone for - the void state
                    # is ordinary column data and travels on the update rail like any
                    # other change. Leaving the tombstone would be actively wrong: it
                    # would refuse every later update to a row that still exists.
                    tombstones.clear_tombstone(
                        school_id, entity_type, pk if pk is not None else coid
                    )
                    results.append(
                        {"index": idx, "status": 200,
                         "data": {"deleted": False, "soft_deleted": True}}
                    )
                    continue
                # The echo-suppression marker describes a row that no longer exists.
                from apps.sync_engine.models import SyncApplyLedger

                SyncApplyLedger.objects.filter(
                    school_id=school_id, entity_type=entity_type, local_pk=str(target_pk)
                ).delete()
        except (
            IntegrityError, DataError, ValidationError, ValueError, TypeError, FieldError,
            OperationalError, ProgrammingError,
        ) as exc:
            # A PROTECT/RESTRICT relation, or a schema this deployment has not migrated.
            results.append(
                {"index": idx, "status": 422, "data": {"error": "delete_failed", "detail": str(exc)[:200]}}
            )
            continue
        deleted += 1
        results.append({"index": idx, "status": 200, "data": {"deleted": True}})

    return {"deleted": deleted, "results": results}


# Distinguishable from a genuine ``None`` in the ledger lookup below.
_UNSET = object()


# Value types it is SAFE to compare by text. Anything else - a related manager, a file
# descriptor, a model instance - is deliberately excluded: see _same_value.
_COMPARABLE_SCALARS = (str, bytes, bool, int, float, _decimal.Decimal, _uuid.UUID)


def _same_value(current, incoming) -> bool:
    """Would writing ``incoming`` over ``current`` change anything?

    Compared as TEXT, but ONLY for plain scalars. The two sides arrive by different routes
    — a live model attribute and a JSON wire payload — so ``Decimal("1.00")`` vs
    ``"1.00"``, ``3`` vs ``"3"`` and a ``date`` vs its ISO string are the same value
    reported differently, and treating those as changes would defeat the check.

    ANYTHING ELSE IS TREATED AS CHANGED, on purpose. Django's ``BaseManager.__str__``
    returns ``"<app>.<Model>.<name>"``, so a many-to-many attribute stringifies to
    something a wire value can genuinely equal — and this check would then SKIP a write
    that was going to fail, converting a 422 into a green 200. A skip-the-redundant-write
    optimisation must never be able to change an outcome; when it cannot be sure, it must
    let the write happen and the real error surface.
    """
    if current is None or incoming is None:
        return current is None and incoming is None
    if current is incoming:
        return True
    if hasattr(current, "isoformat"):  # date / datetime / time
        try:
            return current.isoformat() == str(incoming)
        except Exception:  # noqa: BLE001 - an optimisation must never be the failure
            return False
    if not isinstance(current, _COMPARABLE_SCALARS):
        return False
    try:
        return str(current) == str(incoming)
    except Exception:  # noqa: BLE001
        return False


def _parse_client_updated_at(raw):
    if not raw:
        return None
    if hasattr(raw, "isoformat"):
        return (
            timezone.make_aware(raw, timezone.get_current_timezone())
            if timezone.is_naive(raw)
            else raw
        )
    parsed = parse_datetime(str(raw))
    if not parsed:
        return None
    return (
        timezone.make_aware(parsed, timezone.get_current_timezone())
        if timezone.is_naive(parsed)
        else parsed
    )


def _user_can_edit_entity(user, entity_type, instance):
    from apps.api.entity_api import _is_admin_like

    if user.is_superuser or user.is_staff:
        return True
    if entity_type == "student":
        return _is_admin_like(user)
    if entity_type == "attendance":
        if _is_admin_like(user):
            return True
        from apps.evals.models import TeacherAssignment

        teacher = getattr(user, "teacher_profile", None)
        if not teacher:
            return False
        classroom_ids = set(
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            TeacherAssignment.objects.filter(
                teacher=teacher, is_active=True
            ).values_list("subject_assignment__classroom_id", flat=True)
        )
        return getattr(instance, "classroom_id", None) in classroom_ids
    if entity_type == "classroom":
        return _is_admin_like(user)
    # Generalized CLASS-A master data (teacher, applicant, student_note, …): an
    # admin-like principal manages it. The edge sync principal is the school
    # owner/superuser, already allowed above; this also lets a tenant admin edit it
    # online. Unknown entity types still fall through to a hard deny.
    if entity_type in {spec[0] for spec in _DERIVED_ENTITY_SPECS}:
        return _is_admin_like(user)
    return False


def _sync_conflict_policy(entity_type):
    """``(strategy, protected)`` governing an entity's sync conflicts.

    A registered two-way entity with no explicit ``policy_registry`` entry is treated as
    LWW master data (it was deliberately chosen as safe to converge by timestamp). An
    entity the registry KNOWS — money (fee_payment / invoice_line / payment_proof),
    grades (grade_entry), identity (user_profile / permission_grant), etc. — keeps its
    declared, protected strategy. Aliases are normalized (attendance→attendance_record).
    """
    from apps.sync_engine.policy_registry import (
        MergeStrategy, POLICIES, get_policy, normalize_entity,
    )

    norm = normalize_entity(entity_type)
    if norm in POLICIES:
        p = get_policy(entity_type)
        return p.strategy, p.protected
    if norm in _LWW_SAFE_ENTITIES or entity_type in _LWW_SAFE_ENTITIES:
        return MergeStrategy.CAUSAL_LWW, False
    # Fail CLOSED for anything not explicitly classified — mirrors policy_registry's own
    # "unknown entities fail closed to protected manual review" default, so a sensitive
    # entity can never silently become two-way LWW.
    p = get_policy(entity_type)
    return p.strategy, p.protected


def _conflict_decision(entity_type, sync_origin, client_updated_at, server_dt):
    """Decide how to apply one delta row: ``"apply"`` | ``"conflict"`` | ``"reject"``.

    * LWW master data — newest ``updated_at`` wins; a provably older incoming change is a
      conflict (the local, newer record is kept).
    * Protected / authoritative (money, grades, identity) — the CLOUD is the source of
      truth. A ``cloud-pull`` (cloud→box) always wins on the box (``apply``); a box→cloud
      push or an online edit NEVER silently overwrites it (``conflict`` → Sync Center).
      This is the money = cloud-authoritative rule, enforced by policy not by entity name.
    * ``ONLINE_REQUIRED`` domains (credentials, lifecycle, settlement) are never applied
      through the offline/sync path (``reject``).
    """
    from apps.sync_engine.policy_registry import MergeStrategy

    strategy, protected = _sync_conflict_policy(entity_type)
    if strategy == MergeStrategy.ONLINE_REQUIRED:
        return "reject"
    if protected:
        return "apply" if sync_origin == "cloud-pull" else "conflict"
    # LWW: newest wins. A client row that cannot PROVE it is newer — a missing or
    # unparseable updated_at (client_updated_at is None) — must not silently overwrite a
    # server row that HAS a timestamp; treat it as a conflict for a human to resolve.
    # Both-missing (a brand-new row with no server-side timestamp to beat) still applies.
    if client_updated_at is None:
        return "conflict" if server_dt is not None else "apply"
    if server_dt is not None and client_updated_at < server_dt:
        return "conflict"
    return "apply"


def _serialize_instance_for_conflict(instance, entity_type, fields_subset):
    """Build server_data snapshot for conflict record (only allowed/relevant fields).

    Every value MUST survive ``json.dumps``: the snapshot lands in a JSONField, and if it
    cannot be encoded the CONFLICT RECORD ITSELF fails to save. That failure mode is worse
    than it looks — the row is then neither applied nor reviewable (it returns
    ``conflict_persist_failed`` instead of a 409 with a ``conflict_id``), which silently
    defeats MANUAL_REVIEW for exactly the protected entities that depend on it. ``Decimal``
    is the offender: a grade or money snapshot is full of them. Decimals are stringified,
    matching how the delta wire already ships them (``json.dumps(default=str)``), and a
    final encodability probe catches any other exotic type rather than letting one field
    lose a whole conflict.
    """
    import json
    from decimal import Decimal

    data = {}
    for f in fields_subset:
        if hasattr(instance, f):
            v = getattr(instance, f)
            if hasattr(v, "pk"):
                data[f] = v.pk
            elif hasattr(v, "isoformat"):
                data[f] = v.isoformat() if v else None
            elif isinstance(v, Decimal):
                data[f] = str(v)
            else:
                try:
                    json.dumps(v)
                    data[f] = v
                except (TypeError, ValueError):
                    data[f] = str(v)
    return data


def apply_changes(school_id, user, items, *, persist_conflicts=True, sync_origin=None):
    """Sentry-traced wrapper. Backs the `sync.conflict_pending` SLO.

    ``sync_origin`` (e.g. ``"cloud-pull"`` / ``"edge-push"``) marks that these writes
    are part of edge<->cloud SYNC, not a local user edit — each applied row then records
    an echo-suppression provenance marker so the reverse delta never ships it back
    (see apps.sync_engine.models.SyncApplyLedger). ``None`` (the online DeltaSyncAPI
    default) records nothing, so a genuine local edit still propagates.
    """
    from apps.observability.tracing import (
        finish_transaction, set_transaction_status, start_named_transaction,
    )

    _txn = start_named_transaction(
        "sync.delta_apply", op="task.hot_path",
        school_id=str(school_id) if school_id else "",
        item_count=len(items) if items else 0,
    )
    try:
        return _apply_changes_inner(
            school_id, user, items, persist_conflicts=persist_conflicts, sync_origin=sync_origin
        )
    except Exception:
        set_transaction_status(_txn, "internal_error")
        raise
    finally:
        finish_transaction(_txn)


def _apply_changes_inner(school_id, user, items, *, persist_conflicts=True, sync_origin=None):
    """
    Apply delta items for the given tenant (school). Sort by client timestamp;
    for each item: if server record exists and server.updated_at > client_updated_at
    -> conflict: do not apply, optionally create SyncConflict and add to results.

    Returns:
        dict with:
          success_count: int
          results: list of { "index", "status", "data", "conflict_id" (if conflict persisted) }
          conflicts: list of { "index", "entity_type", "entity_id", "client_data", "server_data",
                              "client_updated_at", "server_updated_at", "conflict_id" }
    """
    from django.core.exceptions import FieldError, ValidationError
    from django.db import (
        DataError,
        IntegrityError,
        OperationalError,
        ProgrammingError,
        transaction,
    )

    # Edge sync operations (sync_origin set) get the expanded registry; an online
    # DeltaSyncAPI call (sync_origin None) gets only the original three — other tenants
    # untouched.
    config = _get_entity_config(include_derived=sync_origin is not None)
    conflicts = []
    success_count = 0

    # Results are stored BY ORIGINAL INDEX and emitted in the caller's order at the end,
    # because rows are no longer processed in the order they arrived (see the dependency
    # sort below). Same contract apply_edge_inserts already keeps.
    results_by_index: dict[int, dict] = {}

    def _emit(row):
        results_by_index[row["index"]] = row

    # Parents this bundle has already proved present or absent, shared across every row so
    # a bundle with hundreds of children costs one existence query per DISTINCT parent.
    fk_seen: dict = {}

    if not school_id:
        return {
            "success_count": 0,
            "results": [
                {
                    "index": idx,
                    "status": 403,
                    "data": {"error": "Tenant context required"},
                }
                for idx, _ in enumerate(items)
            ],
            "conflicts": [],
        }

    # Apply REFERENTS BEFORE DEPENDENTS. The bundle is ordered by updated_at because that
    # is what makes a page boundary a safe cursor (edge_outbox.build_edge_delta_rows), and
    # updated_at order says nothing about dependency - a specialty can arrive ahead of the
    # department it points at and fail on a parent sitting later in the very same bundle.
    # Reordering the APPLY is free: the pull cursor comes from the bundle's high-water
    # header, never from the order rows were applied in.
    _order = _insert_dependency_order(config)

    # Rows this side has BURIED. Loaded once for the whole bundle. Without it a deletion
    # never really sticks: the far side, whose own copy is simply older than its cursor,
    # keeps re-offering the row and the ordinary apply path faithfully re-creates it -
    # a delete that undoes itself on the next cycle.
    from apps.sync_engine.tombstones import clear_tombstone, tombstone_index

    # Both preloads below are scoped to THIS bundle's keys. The ledger and the tombstone
    # table both grow with the deployment's whole history, so reading them whole would
    # make every apply slower the longer a school has been running - for an answer about
    # at most a few hundred rows.
    _bundle_pks = {str(i.get("id")) for i in items if i.get("id") is not None}

    _buried = tombstone_index(school_id, tuple(config), local_pks=_bundle_pks)

    # What SYNC last wrote, per row. Used below to stop this side mistaking its OWN
    # previous apply for a local edit. Loaded once for the bundle.
    _sync_applied: dict = {}
    if sync_origin == "cloud-pull" and _bundle_pks:
        try:
            from apps.sync_engine.models import SyncApplyLedger

            _sync_applied = {
                (row[0], row[1]): row[2]
                for row in SyncApplyLedger.objects.filter(
                    school_id=school_id, local_pk__in=sorted(_bundle_pks)
                ).values_list("entity_type", "local_pk", "applied_updated_at")
            }
        except Exception:  # noqa: BLE001 - a provenance read must never break an apply
            logger.debug("could not load the sync-apply ledger", exc_info=True)

    def _rank(pair):
        _idx, _item = pair
        _et = (_item.get("entity_type") or "").strip().lower()
        # Stable within a rank: same-entity rows keep the order the caller sent them in, so
        # two edits to one record still apply oldest-first.
        return (_order.index(_et) if _et in _order else len(_order), _idx)

    with transaction.atomic():
        _force_immediate_constraints()
        for idx, item in sorted(enumerate(items), key=_rank):
            entity_type = (item.get("entity_type") or "").strip().lower()
            pk = item.get("id")
            changes = item.get("changes") or {}
            client_updated_at = _parse_client_updated_at(item.get("updated_at"))

            if entity_type not in config or pk is None:
                _emit(
                    {
                        "index": idx,
                        "status": 400,
                        "data": {"error": "entity_type and id required"},
                    }
                )
                continue

            model, allowed = config[entity_type]

            # DELETE DOMINANCE, resolved by timestamp so both sides reach the same answer
            # no matter which is asked first. An incoming change to a row this side buried
            # is refused; a change that is strictly NEWER than the burial is the far side
            # deliberately resurrecting the row, so it wins and the tombstone is dropped
            # (leaving it would re-delete the row on the far side next cycle).
            _buried_at = _buried.get((entity_type, str(pk)))
            if _buried_at is not None:
                if client_updated_at is None or client_updated_at <= _buried_at:
                    _emit({
                        "index": idx,
                        "status": 409,
                        "data": {
                            "error": "deleted_upstream",
                            "entity_type": entity_type,
                            "deleted_at": _buried_at.isoformat(),
                        },
                    })
                    continue
                clear_tombstone(school_id, entity_type, pk)
                _buried.pop((entity_type, str(pk)), None)

            if not isinstance(changes, dict):
                _emit(
                    {
                        "index": idx,
                        "status": 400,
                        "data": {"error": "changes must be an object"},
                    }
                )
                continue
            updates = {k: v for k, v in changes.items() if k in allowed}
            if not updates:
                _emit(
                    {
                        "index": idx,
                        "status": 400,
                        "data": {"error": "No allowed fields to update"},
                    }
                )
                continue

            try:
                instance = model.objects.get(pk=pk)
            except model.DoesNotExist:
                # A PULLED row whose pk this box has never seen is a row CREATED ON THE
                # CLOUD after the box was cloned. It carries no client_offline_id (that
                # column marks box-created rows), so the insert path will never see it
                # either - answering 404 here is what made every post-clone cloud record
                # permanently invisible to the box, and what left children pointing at
                # parents that could never arrive. Any OTHER caller keeps the 404: only a
                # cloud-pull may create by pk (see _create_from_cloud_pull).
                if sync_origin != "cloud-pull":
                    _emit({"index": idx, "status": 404, "data": {"error": "Not found"}})
                    continue
                created_obj, create_err = _create_from_cloud_pull(
                    school_id, user, entity_type, model, allowed, pk, changes,
                    client_updated_at, fk_seen,
                )
                if create_err is not None:
                    _emit({"index": idx, **create_err})
                    continue
                # The memo may hold a negative for this pk from a child processed
                # earlier; it is a parent now.
                fk_seen.pop((model._meta.label, created_obj.pk), None)
                created_at_value = getattr(created_obj, "updated_at", None)
                # Provenance, exactly as on the update path: without it the box would push
                # the row it just received straight back up on the next cycle.
                from apps.sync_engine.models import record_sync_apply

                record_sync_apply(
                    school_id, entity_type, created_obj.pk, created_at_value, sync_origin
                )
                success_count += 1
                _emit({
                    "index": idx,
                    "status": 201,
                    "data": {
                        "id": created_obj.pk,
                        "created": True,
                        "updated_at": created_at_value.isoformat() if created_at_value else None,
                    },
                })
                continue

            if not _user_can_edit_entity(user, entity_type, instance):
                _emit(
                    {"index": idx, "status": 403, "data": {"error": "Forbidden"}}
                )
                continue

            if hasattr(instance, "school_id"):
                instance_school_id = getattr(instance, "school_id", None)
                if instance_school_id is None or str(instance_school_id) != str(
                    school_id
                ):
                    _emit(
                        {"index": idx, "status": 403, "data": {"error": "Forbidden"}}
                    )
                    continue

            server_dt = getattr(instance, "updated_at", None)
            if server_dt is not None and timezone.is_naive(server_dt):
                server_dt = timezone.make_aware(server_dt, timezone.get_current_timezone())

            # A row this side last wrote through SYNC ITSELF is not a local edit, even
            # though its updated_at is newer than the incoming one — the newer stamp came
            # from the apply, not from a human. Grading it as a conflict is how a simple
            # RETRY (a failed cycle, or the cursor overlap re-offering a row) manufactured
            # SyncConflict rows out of the engine's own writes, then asked an operator to
            # adjudicate between a value and itself.
            _grade_against = server_dt
            if (
                sync_origin == "cloud-pull"
                and _sync_applied.get((entity_type, str(pk)), _UNSET) == server_dt
            ):
                _grade_against = None

            decision = _conflict_decision(
                entity_type, sync_origin, client_updated_at, _grade_against
            )
            if decision == "reject":
                # Domain may only change through a live online transaction (policy
                # ONLINE_REQUIRED); an offline/sync replay must never apply it.
                _emit(
                    {
                        "index": idx,
                        "status": 409,
                        "data": {"error": "online_required", "entity_type": entity_type},
                    }
                )
                continue
            if decision == "conflict":
                # Do not overwrite; persist SyncConflict for Sync Center resolution. Fires
                # on a stale LWW change OR any box/online change to a cloud-authoritative
                # (protected) record — the cloud's copy is kept until a human decides.
                server_data = _serialize_instance_for_conflict(
                    instance, entity_type, allowed
                )
                conflict_id = None
                if persist_conflicts:
                    from apps.siteconfig.models import SyncConflict
                    from apps.schools.models import School

                    school = (
                        School.objects.filter(pk=school_id).first()
                        if school_id
                        else None
                    )
                    if school:
                        try:
                            # Savepoint: persisting the conflict record must not be able to
                            # abort the whole batch. (Also degrades gracefully if a future
                            # UUID-pk entity is registered before SyncConflict.entity_id is
                            # widened — a DataError here becomes a 422, never a batch 500.)
                            with transaction.atomic():
                                sc = SyncConflict.objects.create(
                                    school=school,
                                    entity_type=entity_type,
                                    entity_id=pk,
                                    client_data=dict(changes),
                                    server_data=server_data,
                                    client_updated_at=client_updated_at,
                                    server_updated_at=server_dt,
                                    reported_by=user,
                                    status=SyncConflict.Status.PENDING,
                                )
                            conflict_id = sc.pk
                        except (
                            IntegrityError, DataError, ValidationError,
                            ValueError, TypeError, FieldError,
                        ) as exc:
                            _emit({
                                "index": idx, "status": 422,
                                "data": {"error": "conflict_persist_failed", "detail": str(exc)[:200]},
                            })
                            continue
                conflicts.append(
                    {
                        "index": idx,
                        "entity_type": entity_type,
                        "entity_id": pk,
                        "client_data": dict(changes),
                        "server_data": server_data,
                        "client_updated_at": client_updated_at.isoformat()
                        if client_updated_at
                        else None,
                        "server_updated_at": server_dt.isoformat() if server_dt else None,
                        "conflict_id": conflict_id,
                    }
                )
                _emit(
                    {
                        "index": idx,
                        "status": 409,
                        "data": {
                            "error": "conflict",
                            "server_updated_at": server_dt.isoformat() if server_dt else None,
                            "conflict_id": conflict_id,
                        },
                        "conflict_id": conflict_id,
                    }
                )
                continue

            # Per-FIELD direction guard (see _DOWN_ONLY_FIELDS_PER_ENTITY). The entity-level
            # decision above already said "apply", but a cloud-governed column must still not
            # travel upward. Strip it from a box push / online edit and REPORT the refusal, so
            # a discarded write is visible instead of vanishing.
            rejected_down_only = []
            if sync_origin != "cloud-pull":
                for _f in sorted(_DOWN_ONLY_FIELDS_PER_ENTITY.get(entity_type, ())):
                    if _f in updates:
                        updates.pop(_f)
                        rejected_down_only.append(_f)
            if rejected_down_only and not updates:
                # The row carried nothing BUT down-only fields: refuse it outright rather than
                # bumping updated_at for a write that changed nothing (which would also re-ship
                # the row on the next delta).
                _emit({
                    "index": idx,
                    "status": 409,
                    "data": {
                        "error": "down_only_fields_rejected",
                        "fields": rejected_down_only,
                    },
                })
                continue

            # Referential preflight. A pulled row can point at a parent this box has
            # never been given; on PostgreSQL that failure CANNOT be caught after the write
            # (Django's FKs are DEFERRABLE INITIALLY DEFERRED, so the violation is raised by
            # the outermost COMMIT, outside every per-row savepoint below), so it has to be
            # caught before it. Reported as a distinct 409 rather than an opaque constraint
            # string, and self-healing: the parent now arrives on a pull too, so the row
            # applies on a later cycle instead of poisoning every cycle forever.
            missing_ref = _unresolvable_fk(model, allowed, updates, fk_seen)
            if missing_ref is not None:
                _emit({
                    "index": idx,
                    "status": 409,
                    "data": {
                        "error": "missing_reference",
                        "field": missing_ref[0],
                        "references": missing_ref[1],
                        "referenced_id": missing_ref[2],
                    },
                })
                continue

            # Nothing to do: every incoming value already matches. Saving anyway would
            # bump updated_at for a write that changed nothing, which re-enters this row
            # into the next delta in the OTHER direction — churn manufactured by the
            # engine, most visible now that the cursor overlap deliberately re-offers
            # recent rows.
            if all(
                _same_value(getattr(instance, _k, None), _v) for _k, _v in updates.items()
            ):
                if sync_origin:
                    from apps.sync_engine.models import record_sync_apply

                    record_sync_apply(
                        school_id, entity_type, instance.pk,
                        getattr(instance, "updated_at", None), sync_origin,
                    )
                success_count += 1
                _emit({
                    "index": idx,
                    "status": 200,
                    "data": {"id": instance.pk, "unchanged": True},
                })
                continue

            try:
                # Apply updates INSIDE the per-row guard. A bad value raises at ASSIGNMENT
                # time, before any save — a non-assignable descriptor raises TypeError, a
                # malformed value ValueError/ValidationError. While this loop sat outside
                # the try, such a row escaped `apply_changes` altogether and killed the
                # WHOLE bundle apply (every entity in it, not just the offending row),
                # instead of degrading this ONE row to the 422 the handler below already
                # returns. Keep assignment and save under the same guard.
                for key, value in updates.items():
                    setattr(instance, key, value)
                update_fields = list(updates.keys())
                if hasattr(instance, "updated_at"):
                    update_fields.append("updated_at")
                # Per-row savepoint: one un-appliable row (FK to a deleted parent, a
                # unique/not-null collision — SQLite doesn't enforce these, only prod
                # Postgres does) must roll back ONLY this row, never the whole bundle. The
                # save + its echo-suppression ledger write are one atomic unit so a saved
                # row can never be left without provenance (which would re-ship it forever).
                with transaction.atomic():
                    instance.save(update_fields=update_fields)
                    new_updated_at = getattr(instance, "updated_at", None)
                    if sync_origin:
                        # Provenance marker so the reverse delta won't echo this apply.
                        from apps.sync_engine.models import record_sync_apply

                        record_sync_apply(
                            school_id, entity_type, instance.pk, new_updated_at, sync_origin
                        )
            except (
                IntegrityError, DataError, ValidationError,
                ValueError, TypeError, FieldError,
                # A column this deployment's schema does not have yet. Without these two
                # the error escapes the savepoint and kills the WHOLE bundle; the run
                # message names the pending migrations (see sync_engine.schema_guard).
                OperationalError, ProgrammingError,
            ) as exc:
                _emit({
                    "index": idx, "status": 422,
                    "data": {"error": "apply_failed", "detail": str(exc)[:200]},
                })
                continue
            success_count += 1
            _data = {
                "id": instance.pk,
                "updated_at": new_updated_at.isoformat() if new_updated_at else None,
            }
            if rejected_down_only:
                # Partial acceptance: the benign fields landed, the cloud-governed ones did
                # not. Surfaced so the caller can reconcile rather than read a 200 as "all of
                # my changes were taken".
                _data["rejected_down_only_fields"] = rejected_down_only
            _emit({"index": idx, "status": 200, "data": _data})

    # Caller's ORIGINAL order, whatever dependency order the rows were processed in.
    results = [results_by_index[i] for i in sorted(results_by_index)]
    conflicts.sort(key=lambda c: c["index"])
    return {
        "success_count": success_count,
        "results": results,
        "conflicts": conflicts,
    }


def _insert_dependency_order(config) -> list:
    """Order the entity types so a new row that references ANOTHER new row is created
    AFTER its referent (whose operator pk we then substitute for the box's local pk).

    The edge graph is :func:`_insert_fk_targets` (derived per entity): an entity depends
    on another when one of its synced FK fields points at that other entity (e.g.
    ``attendance.student_id`` -> student, ``student.classroom_id`` -> classroom). A
    Kahn-style topological sort with a deterministic (sorted) tie-break; a cycle (e.g. a
    self-referential ``reports_to``) degrades gracefully to sorted order — those rows
    simply fall back to FK-drop, never mis-link.
    """
    fk_targets = _insert_fk_targets(config)
    deps: dict[str, set] = {}
    for entity_type in config:
        deps[entity_type] = {t for t in fk_targets.get(entity_type, {}).values() if t != entity_type}

    order: list = []
    placed: set = set()
    while len(placed) < len(deps):
        ready = sorted(et for et in deps if et not in placed and deps[et] <= placed)
        if not ready:  # cycle guard — deterministic fallback, never an infinite loop
            ready = sorted(et for et in deps if et not in placed)
        for et in ready:
            order.append(et)
            placed.add(et)
    return order


def _settable_field_names(model) -> set:
    """Concrete field names on ``model`` that can be passed to ``create`` — includes
    both the relation name and its ``<field>_id`` attname. Lets the insert path ignore
    any phantom entry in an allow-list (e.g. a field that doesn't exist on the model)."""
    names: set = set()
    for f in model._meta.get_fields():
        if not getattr(f, "concrete", False):
            continue
        if getattr(f, "name", None):
            names.add(f.name)
        attname = getattr(f, "attname", None)
        if attname:
            names.add(attname)
    return names


def apply_edge_inserts(school_id, user, rows, *, sync_origin=None):
    """Upsert offline-CREATED rows by ``(school, client_offline_id)`` — edge-only.

    The counterpart to :func:`apply_changes` (which is update-by-pk). Rows here were
    created on an edge box and carry a client-generated ``client_offline_id`` plus the
    box's LOCAL integer pks, which are meaningless on the operator — so we NEVER look
    up by pk; we upsert by ``(school, client_offline_id)`` under a per-row savepoint so
    one bad row never rolls back the batch. Only an admin-like / staff / superuser may
    create (the edge box acts as a bound school admin).

    **FK id-remapping (new-references-new).** A foreign key that points at ANOTHER
    insert-row's box-local pk cannot be applied verbatim (the operator assigns its own
    pk). Rows are therefore processed in dependency order (:func:`_insert_dependency_order`
    — referents before dependents), and each new row's freshly-assigned operator pk is
    recorded in a ``(entity_type, local_pk) -> operator_pk`` map; a dependent FK is then
    REMAPPED onto that operator pk. If the referent could not be created (or isn't in the
    bundle), the FK is dropped — the dependent row then links only to already-present
    (cloned, pk-stable) records or, if that FK was required, fails cleanly and is reported,
    never silently mis-linked. Results are returned in the caller's ORIGINAL row order
    regardless of the internal processing order.

    Returns ``{"created", "updated", "results"}`` (results carry per-row index/status).
    """
    from django.core.exceptions import FieldError, ValidationError
    from django.db import (
        DataError,
        IntegrityError,
        OperationalError,
        ProgrammingError,
        transaction,
    )

    from apps.api.entity_api import _is_admin_like
    from apps.schools.models import School

    # Edge sync operations (sync_origin set) get the expanded registry; an online
    # DeltaSyncAPI call (sync_origin None) gets only the original three — other tenants
    # untouched.
    config = _get_entity_config(include_derived=sync_origin is not None)
    school = School.objects.filter(pk=school_id).first() if school_id else None
    can_create = bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or _is_admin_like(user)
    )

    # Local pks that belong to NEW (insert) rows, keyed by entity — their operator pk
    # will differ, so a FK pointing at one of them must be remapped, never applied raw.
    new_local_pks: dict[str, set] = {}
    for item in rows:
        et = (item.get("entity_type") or "").strip().lower()
        pid = item.get("id")
        if et and pid is not None:
            new_local_pks.setdefault(et, set()).add(pid)

    created = 0
    updated = 0
    if school is None or not can_create:
        reason = "tenant_context_required" if school is None else "forbidden"
        return {
            "created": 0,
            "updated": 0,
            "results": [{"index": i, "status": 403, "data": {"error": reason}} for i, _ in enumerate(rows)],
        }

    # (entity_type, box-local pk) -> assigned operator pk, filled as referents are created
    # so a later dependent row can substitute the real pk for the box's local one.
    remap: dict[tuple, object] = {}
    # Parents already proved present/absent, shared across rows (see _unresolvable_fk).
    fk_seen: dict = {}
    order = _insert_dependency_order(config)
    fk_targets = _insert_fk_targets(config)  # {entity_type: {fk_attname: target_entity_type}}

    # Anchors this side has buried. An offline-created row is matched by
    # (school, client_offline_id), never by pk, so the pk-keyed index cannot answer for
    # it - and without this guard a box would re-create, on EVERY cycle, the very row the
    # cloud had just deleted: the upsert finds nothing, inserts afresh, the cloud deletes
    # it again, forever.
    from apps.sync_engine.tombstones import (
        clear_tombstone as _clear_tombstone,
        tombstone_index_by_client_offline_id,
    )

    buried_anchors = tombstone_index_by_client_offline_id(
        school_id,
        anchors={(r.get("client_offline_id") or "").strip() for r in rows},
    )

    def _rank(item):
        et = (item.get("entity_type") or "").strip().lower()
        return order.index(et) if et in order else len(order)

    # Process referents before dependents; stable by original index within a rank. Results
    # are stored by original index and emitted in original order below.
    ordered = sorted(enumerate(rows), key=lambda pair: (_rank(pair[1]), pair[0]))
    results_by_index: dict[int, dict] = {}

    for idx, item in ordered:
        entity_type = (item.get("entity_type") or "").strip().lower()
        coid = (item.get("client_offline_id") or "").strip()
        local_pk = item.get("id")
        changes = item.get("changes") or {}
        if entity_type not in config or not coid:
            results_by_index[idx] = {"index": idx, "status": 400, "data": {"error": "entity_type_and_client_offline_id_required"}}
            continue
        model, allowed = config[entity_type]

        # Delete dominance for anchored rows, same timestamp rule as the update path.
        _incoming_at = _parse_client_updated_at(item.get("updated_at"))
        _anchor_buried_at = buried_anchors.get((entity_type, coid))
        if _anchor_buried_at is not None:
            if _incoming_at is None or _incoming_at <= _anchor_buried_at:
                results_by_index[idx] = {
                    "index": idx,
                    "status": 409,
                    "data": {
                        "error": "deleted_upstream",
                        "entity_type": entity_type,
                        "deleted_at": _anchor_buried_at.isoformat(),
                    },
                }
                continue
            buried_anchors.pop((entity_type, coid), None)
            _clear_tombstone(school_id, entity_type, coid)

        if not any(getattr(f, "name", "") == "client_offline_id" for f in model._meta.get_fields()):
            results_by_index[idx] = {"index": idx, "status": 422, "data": {"error": "entity_not_insertable"}}
            continue
        # Entities that converge as UPDATES but may not be CREATED across the rail. Refused
        # here, with the reason, rather than being attempted and dying on a required
        # non-portable relation — which would report an opaque IntegrityError every cycle.
        if entity_type in _INSERT_HELD_ENTITIES:
            results_by_index[idx] = {
                "index": idx,
                "status": 409,
                "data": {
                    "error": "insert_held_for_entity",
                    "entity_type": entity_type,
                    "reason": _INSERT_HELD_ENTITIES[entity_type],
                },
            }
            continue

        valid_fields = _settable_field_names(model)
        ent_targets = fk_targets.get(entity_type, {})
        updates = {}
        dropped_fks = []
        # Per-FIELD direction guard, same policy as the UPDATE path (_apply_changes_inner).
        # It has to be applied HERE too: direction is a property of the field, so without
        # this the whole policy is bypassable by presenting an edit as a new row —
        # the value the update path refuses with 409 would land cleanly as an insert.
        rejected_down_only = []
        down_only = (
            set(_DOWN_ONLY_FIELDS_PER_ENTITY.get(entity_type, ()))
            if sync_origin != "cloud-pull"
            else set()
        )
        for key, value in changes.items():
            if key not in allowed or key not in valid_fields:
                continue  # not editable, or a phantom allow-list entry not on the model
            if key in down_only:
                # Dropped, not fatal: the row still lands, minus the cloud-owned column,
                # which then arrives on the next cloud->box pull. Reported so a discarded
                # write is visible rather than vanishing.
                rejected_down_only.append(key)
                continue
            target = ent_targets.get(key)
            if target and value is not None:
                if value in new_local_pks.get(target, set()):
                    # Points at another new row: substitute the referent's operator pk if it
                    # was already created this batch, else DROP (a required FK then fails
                    # cleanly; a nullable FK lands NULL — surfaced via dropped_fks so the
                    # caller can reconcile rather than treat a partial row as a clean success).
                    remapped = remap.get((target, value))
                    if remapped is None:
                        dropped_fks.append(key)
                        continue
                    value = remapped
                else:
                    # Points at an EXISTING (non-new) row of a registered entity: it MUST
                    # belong to THIS school. On the intended pk-preserving single-tenant
                    # clone it always does; a value that resolves to another tenant's row (a
                    # mis-provisioned box / stale reference) is DROPPED rather than linked
                    # cross-tenant. Guarantee #2 already holds (the created row is owned by
                    # `school`); this stops a wrong-but-in-schema link.
                    target_model = config[target][0]
                    if not target_model._default_manager.filter(pk=value, school=school).exists():
                        dropped_fks.append(key)
                        continue
            updates[key] = value

        # Referential preflight for the FKs the remap loop above does NOT cover: it only
        # knows FKs pointing at another REGISTERED entity (its job is remapping
        # new-references-new pks), and a derived field set can carry a FK to a tenant model
        # that is not itself on the rail. Reported as a precise 409 rather than an opaque
        # constraint string. (Unlike _apply_changes_inner this function runs in autocommit -
        # one real transaction per row - so its savepoint genuinely does see a deferred FK
        # error at its own COMMIT. A caller that ever wraps this loop in an OUTER atomic
        # must call _force_immediate_constraints() first, or that stops being true.)
        missing_ref = _unresolvable_fk(model, allowed, updates, fk_seen)
        if missing_ref is not None:
            results_by_index[idx] = {
                "index": idx,
                "status": 409,
                "data": {
                    "error": "missing_reference",
                    "field": missing_ref[0],
                    "references": missing_ref[1],
                    "referenced_id": missing_ref[2],
                },
            }
            continue

        try:
            with transaction.atomic():  # savepoint: isolate a bad row from the batch
                obj, was_created = model.objects.get_or_create(
                    school=school, client_offline_id=coid, defaults=updates
                )
                if not was_created and updates:
                    for key, value in updates.items():
                        setattr(obj, key, value)
                    update_fields = list(updates.keys())
                    if hasattr(obj, "updated_at"):
                        # Bump the change cursor, mirroring apply_changes — otherwise an
                        # UPDATE to an offline-created row keeps its old updated_at and is
                        # invisible to the incremental delta (filter(updated_at__gt=since)).
                        update_fields.append("updated_at")
                    obj.save(update_fields=update_fields)
        except (
            IntegrityError, DataError, ValidationError, ValueError, TypeError, FieldError,
            OperationalError, ProgrammingError,  # a column this schema does not have yet
        ) as exc:
            # DataError (value too long / out of range on Postgres) is a DatabaseError
            # sibling of IntegrityError; catching it keeps the per-row savepoint from
            # escaping and rolling back the whole batch (SQLite doesn't enforce
            # max_length, so only prod Postgres exercised this path).
            results_by_index[idx] = {"index": idx, "status": 422, "data": {"error": "insert_failed", "detail": str(exc)[:200]}}
            continue

        fk_seen.pop((model._meta.label, obj.pk), None)  # it is a valid parent now
        # Record the operator pk so later dependent rows can remap their FK onto it.
        if local_pk is not None:
            remap[(entity_type, local_pk)] = obj.pk

        if was_created:
            created += 1
        else:
            updated += 1
        if sync_origin:
            # Provenance marker so the reverse delta won't echo this sync-applied insert.
            from apps.sync_engine.models import record_sync_apply

            record_sync_apply(
                school_id, entity_type, obj.pk, getattr(obj, "updated_at", None), sync_origin
            )
        data = {"id": obj.pk, "created": was_created}
        if dropped_fks:
            data["dropped_fks"] = dropped_fks  # links that pointed at an uncreated new row
        if rejected_down_only:
            # Same key the UPDATE path reports, so a caller reconciles one contract.
            data["rejected_down_only_fields"] = rejected_down_only
        results_by_index[idx] = {"index": idx, "status": 201 if was_created else 200, "data": data}

    results = [results_by_index[i] for i in range(len(rows))]
    return {"created": created, "updated": updated, "results": results}
