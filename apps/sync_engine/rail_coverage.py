"""Edge-sync rail coverage: a declared posture for EVERY tenant model.

Why this module exists
----------------------
The edge appliance replicates a small fraction of the product. Measured on
2026-08-31: **17 entities ride the delta rail**, of which **15 are tenant
business models**, against **326 models across the 15 apps in ``TENANT_APPS``**
-- about **4.6%**. The rail side is read from the live entity registry; the 326
is read from MIGRATION STATE, for reasons ``tenant_models`` sets out at length. Two of the 17 (``sync_schedule``,
``sync_policy``) live in the SHARED ``sync_engine`` app: they are the rail's own
configuration, not school data, so they are counted separately.

That number is not, by itself, a defect. Some absences are correct and are
argued in the repo -- ``finance.Payment`` is held out for two independently
sufficient reasons (``docs/EDGE_SYNC_FINANCE_HOLD.md``), and
``policy_registry.POLICIES`` declares ``payment_settlement`` ONLINE_REQUIRED
because charging a gateway is a live transaction.

The defect is that **most absences carried no recorded decision at all**. Eleven
of the fifteen tenant apps had zero entities and zero written rationale, so "the
box cannot send a message / produce a report card / log a safeguarding incident /
run payroll" was true by accident rather than by choice, and nothing would have
noticed a new model quietly joining that silence.

What this module is
-------------------
A machine-readable declaration mapping every ``TENANT_APPS`` model to one of
three postures:

``RIDES``
    The model is registered on the edge delta rail. **Never written by hand.**
    It is DERIVED from the live registry (``apps.api.sync_services``) on every
    call, so it cannot drift: register an entity and this module says RIDES the
    same second, without anyone editing a list here.

``HELD``
    A deliberate, argued exclusion. **Requires** a written ``rationale`` AND an
    ``argued_in`` pointer to where the decision is made (a doc, a policy row, a
    test). A HELD entry missing either one is a hard failure -- an unargued
    "held" is just a NOT_YET wearing a badge.

``NOT_YET``
    Honest backlog. Nobody has decided. It carries NO rationale, and declaring a
    rationale on a NOT_YET is a hard failure precisely so the two cannot blur:
    if you have the argument, you are HELD.

``scripts/audit_rail_coverage.py`` runs this and fails on an UNDECLARED model,
so a newly added tenant model must state its rail posture -- the same way this
repo already forces a model to declare its tenancy.

Reading the numbers honestly
----------------------------
Model counts come from the **live Django app registry**, not from grepping
``class X(models.Model)``. The two disagree, and the registry is right: e.g.
``apps/evals/models_enhanced.py`` defines 12 model classes that are never
imported and have no migrations (``apps/evals/urls.py`` calls one of them
"abandoned"), so a grep says evals has 22 models while the registry -- and the
database -- has 10. A model with no table cannot ride anything.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Postures
# ---------------------------------------------------------------------------

RIDES = "RIDES"
HELD = "HELD"
NOT_YET = "NOT_YET"
#: Not a posture anyone may write -- the auditor's name for a model that has none.
UNDECLARED = "UNDECLARED"

#: The only postures a human may put in ``DECLARATIONS``. ``RIDES`` is absent on
#: purpose: it is derived from the live registry, never asserted here, so the
#: declaration cannot claim coverage the rail does not actually provide.
DECLARABLE_POSTURES = (HELD, NOT_YET)

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO_ROOT / "config" / "settings.py"


@dataclass(frozen=True)
class Declaration:
    """One model's recorded rail posture.

    ``rationale`` and ``argued_in`` are REQUIRED for ``HELD`` and FORBIDDEN for
    ``NOT_YET``. The asymmetry is the point: a decision must be written down and
    must point at where it is argued, while a non-decision must not be dressed up
    as one.
    """

    posture: str
    rationale: str = ""
    argued_in: str = ""


def _held(rationale: str, argued_in: str) -> Declaration:
    return Declaration(posture=HELD, rationale=rationale, argued_in=argued_in)


_NOT_YET = Declaration(posture=NOT_YET)


# ---------------------------------------------------------------------------
# Argued holds. Everything here must be defensible from the repo, not invented.
# ---------------------------------------------------------------------------

_HELD_PAYMENT = _held(
    rationale=(
        "Two independently sufficient reasons, both verified rather than predicted. "
        "(1) No delta cursor exists: finance.Payment has no `updated_at` column at all, "
        "and the incremental bundle filters `updated_at__gt=since`, so registering it "
        "raises FieldError rather than degrading. Adding `auto_now` is not a benign "
        "additive migration -- it rewrites the value on every save of the money ledger, "
        "the table most likely to be reconciled and audited byte-for-byte. "
        "(2) Payment carries live settlement state (gateway_transaction_id, "
        "gateway_response, external_reference, completed_at, failed_at, "
        "compliance_checked), and policy_registry already declares `payment_settlement` "
        "ONLINE_REQUIRED -- executing a charge against a gateway is a live transaction. "
        "Putting it on a two-way rail would contradict the platform's own rule."
    ),
    argued_in=(
        "docs/EDGE_SYNC_FINANCE_HOLD.md; "
        "apps/sync_engine/tests/test_edge_sync_finance_down_only_2026_08_17.py; "
        "apps/sync_engine/policy_registry.py::POLICIES['payment_settlement']"
    ),
)

_HELD_PAYMENTPROOFUPLOAD = _held(
    rationale=(
        "Held with finance.Payment and for the first of the same reasons: it has no "
        "`updated_at` column, so the incremental delta cannot even query it. Its "
        "receipt bytes are a second obstacle -- a bundle carries column values, never "
        "file bytes, so a synced path would point the box at a file that does not "
        "exist there. The revisit condition is a real file channel plus a decision "
        "about which subset of payment evidence is offline-replayable, not a "
        "mechanical registration."
    ),
    argued_in=(
        "docs/EDGE_SYNC_FINANCE_HOLD.md; "
        "apps/sync_engine/tests/test_edge_sync_finance_down_only_2026_08_17.py"
    ),
)


# ---------------------------------------------------------------------------
# The declaration.
#
# Keys are `app_label.modelname` exactly as Django's `Model._meta.label_lower`
# renders it, so a typo cannot silently "cover" a model -- an entry whose key
# matches no live tenant model is itself a hard failure (`unknown_model`).
#
# Models that RIDE are deliberately ABSENT from this table. Their posture is
# read from the live registry every time, so adding an entity to
# `_DERIVED_ENTITY_SPECS` changes this module's answer with no edit here.
# ---------------------------------------------------------------------------

DECLARATIONS: dict[str, Declaration] = {
    # -- portal: 28 model(s). On the rail (0): none.
    "portal.announcement": _NOT_YET,
    "portal.attendancejustification": _NOT_YET,
    "portal.cahierdetexteentry": _NOT_YET,
    # Migrated by portal/migrations/0038_community_forums_1357.py but defined in
    # the LAZILY imported apps/portal/models_forums.py, so a cold registry walk
    # misses all three. See tenant_models() -- this trio is why that enumeration
    # reads migration state.
    "portal.communityforumcategory": _NOT_YET,
    "portal.communityforumreply": _NOT_YET,
    "portal.communityforumtopic": _NOT_YET,
    "portal.documentcategory": _NOT_YET,
    "portal.event": _NOT_YET,
    "portal.faq": _NOT_YET,
    "portal.faqcategory": _NOT_YET,
    "portal.formsignature": _NOT_YET,
    "portal.guardianlinkinvitation": _NOT_YET,
    "portal.hostedofficedocument": _NOT_YET,
    "portal.kbarticle": _NOT_YET,
    "portal.kbarticleattachment": _NOT_YET,
    "portal.kbcategory": _NOT_YET,
    "portal.kbcomment": _NOT_YET,
    "portal.lessonplan": _NOT_YET,
    "portal.lessonplanattachment": _NOT_YET,
    "portal.parentmessage": _NOT_YET,
    "portal.parentstudentlink": _NOT_YET,
    "portal.pendingguardianinvite": _NOT_YET,
    "portal.photouploadtoken": _NOT_YET,
    "portal.portalauditlog": _NOT_YET,
    "portal.portalfeatureaccess": _NOT_YET,
    "portal.portalfeatureitem": _NOT_YET,
    "portal.portalnotification": _NOT_YET,
    "portal.portalpreferences": _NOT_YET,
    "portal.portalsession": _NOT_YET,
    "portal.teachertrainingentry": _NOT_YET,
    "portal.usercontribution": _NOT_YET,

    # -- academics: 48 model(s). On the rail (9): AcademicYear, Attendance, Classroom, Department, Specialty, SpecialtySubject, Subject, SubjectAssignment, Term.
    "academics.academicstructurenode": _NOT_YET,
    "academics.behaviorpointledger": _NOT_YET,
    "academics.certificationauditlog": _NOT_YET,
    "academics.certificationcandidate": _NOT_YET,
    "academics.certificationcandidatedocumentstatus": _NOT_YET,
    "academics.certificationdocumentchecklist": _NOT_YET,
    "academics.certificationdocumentitem": _NOT_YET,
    "academics.certificationexampreset": _NOT_YET,
    "academics.certificationexamsession": _NOT_YET,
    "academics.certificationfeeline": _NOT_YET,
    "academics.certificationfeetemplate": _NOT_YET,
    "academics.classbooklist": _NOT_YET,
    "academics.classroompromotionmapping": _NOT_YET,
    "academics.coursesyllabus": _NOT_YET,
    "academics.curriculumallocation": _NOT_YET,
    "academics.curriculumnode": _NOT_YET,
    "academics.curriculumstandard": _NOT_YET,
    "academics.degreeprogram": _NOT_YET,
    "academics.graduatemilestone": _NOT_YET,
    "academics.holidaycalendar": _NOT_YET,
    "academics.incident": _NOT_YET,
    "academics.instructionday": _NOT_YET,
    "academics.instructionshift": _NOT_YET,
    "academics.lmsassignment": _NOT_YET,
    "academics.lmssubmission": _NOT_YET,
    "academics.reportcardstyleassignment": _NOT_YET,
    "academics.restorativeaction": _NOT_YET,
    "academics.rolloverproposal": _NOT_YET,
    "academics.rolloverproposalitem": _NOT_YET,
    "academics.room": _NOT_YET,
    "academics.schedule": _NOT_YET,
    "academics.scheduleentry": _NOT_YET,
    "academics.schedulingconstraint": _NOT_YET,
    "academics.studentdegreeenrollment": _NOT_YET,
    "academics.teacheravailability": _NOT_YET,
    "academics.timeslot": _NOT_YET,
    "academics.transfercourseequivalency": _NOT_YET,
    "academics.transfercredit": _NOT_YET,
    "academics.workflowconfig": _NOT_YET,

    # -- people: 31 model(s). On the rail (4): Applicant, StudentNote, StudentProfile, TeacherProfile.
    "people.admissionnumbersequence": _NOT_YET,
    "people.apprenticeplacement": _NOT_YET,
    "people.badge": _NOT_YET,
    "people.badgescanevent": _NOT_YET,
    "people.badgetype": _NOT_YET,
    "people.employerprofile": _NOT_YET,
    "people.enrollment": _NOT_YET,
    "people.informationtag": _NOT_YET,
    "people.passportdocument": _NOT_YET,
    "people.passportschoolinvite": _NOT_YET,
    "people.recordmergeoperation": _NOT_YET,
    "people.retentionalert": _NOT_YET,
    "people.schooltransferbatch": _NOT_YET,
    "people.specialeducationplan": _NOT_YET,
    "people.staffcompliancerecord": _NOT_YET,
    "people.studentguardian": _NOT_YET,
    "people.studentpassport": _NOT_YET,
    "people.studentpassportmembership": _NOT_YET,
    "people.studentresourcereturn": _NOT_YET,
    "people.teacherattendance": _NOT_YET,
    "people.teacherleaverequest": _NOT_YET,
    "people.teacherpayrecord": _NOT_YET,
    "people.tenantauditlog": _NOT_YET,
    "people.transcriptvaultitem": _NOT_YET,
    "people.transfercase": _NOT_YET,
    "people.transferconsent": _NOT_YET,
    "people.vocationalcertification": _NOT_YET,

    # -- schoolops: 38 model(s). On the rail (0): none.
    "schoolops.biometricattendancelog": _NOT_YET,
    "schoolops.biometricdevice": _NOT_YET,
    "schoolops.bookableresource": _NOT_YET,
    "schoolops.bus": _NOT_YET,
    "schoolops.busboardingevent": _NOT_YET,
    "schoolops.campus": _NOT_YET,
    "schoolops.canteenmeal": _NOT_YET,
    "schoolops.emaildeadletter": _NOT_YET,
    "schoolops.emaildeliveryevent": _NOT_YET,
    "schoolops.healthrecord": _NOT_YET,
    "schoolops.hostel": _NOT_YET,
    "schoolops.hostelassignment": _NOT_YET,
    "schoolops.hostelroom": _NOT_YET,
    "schoolops.immunizationrecord": _NOT_YET,
    "schoolops.inventoryitem": _NOT_YET,
    "schoolops.inventorymovement": _NOT_YET,
    "schoolops.libraryitem": _NOT_YET,
    "schoolops.libraryloan": _NOT_YET,
    "schoolops.lostbelongingscustodyeventrecord": _NOT_YET,
    "schoolops.lostbelongingstagrecord": _NOT_YET,
    "schoolops.maintenancerequest": _NOT_YET,
    "schoolops.mealplanbalance": _NOT_YET,
    "schoolops.possaleline": _NOT_YET,
    "schoolops.purchaseorder": _NOT_YET,
    "schoolops.purchaseorderline": _NOT_YET,
    "schoolops.resourcebooking": _NOT_YET,
    "schoolops.route": _NOT_YET,
    "schoolops.stop": _NOT_YET,
    "schoolops.substitutecover": _NOT_YET,
    "schoolops.substitutehandoverpacketrecord": _NOT_YET,
    "schoolops.substitutemarketshift": _NOT_YET,
    "schoolops.supplyrequirement": _NOT_YET,
    "schoolops.suppressedrecipient": _NOT_YET,
    "schoolops.transportassignment": _NOT_YET,
    "schoolops.vaccinerequirement": _NOT_YET,
    "schoolops.vendor": _NOT_YET,
    "schoolops.vendorproduct": _NOT_YET,
    "schoolops.visitorcheckin": _NOT_YET,

    # -- finance: 57 model(s). On the rail (1): Invoice.
    "finance.aidauditlog": _NOT_YET,
    "finance.asset": _NOT_YET,
    "finance.assetcategory": _NOT_YET,
    "finance.awardsource": _NOT_YET,
    "finance.bankaccount": _NOT_YET,
    "finance.bankaccountchangerequest": _NOT_YET,
    "finance.bankstatemententry": _NOT_YET,
    "finance.bankstatementupload": _NOT_YET,
    "finance.budget": _NOT_YET,
    "finance.budgetline": _NOT_YET,
    "finance.cashofficeclosure": _NOT_YET,
    "finance.complianceprofile": _NOT_YET,
    "finance.contributionrule": _NOT_YET,
    "finance.counterparty": _NOT_YET,
    "finance.feeinstallment": _NOT_YET,
    "finance.feeitem": _NOT_YET,
    "finance.feeplan": _NOT_YET,
    "finance.financeofflinecapturerecord": _NOT_YET,
    "finance.financerequestaudit": _NOT_YET,
    "finance.financialaidapplication": _NOT_YET,
    "finance.fractionalpaymentledger": _NOT_YET,
    "finance.grant": _NOT_YET,
    "finance.grantallocation": _NOT_YET,
    "finance.invoiceline": _NOT_YET,
    "finance.invoicepayershare": _NOT_YET,
    "finance.invoicepayersharepaymentallocation": _NOT_YET,
    "finance.journalentry": _NOT_YET,
    "finance.journalline": _NOT_YET,
    "finance.ledgeraccount": _NOT_YET,
    "finance.notification": _NOT_YET,
    "finance.offlinepaymentintent": _NOT_YET,
    "finance.parentwallet": _NOT_YET,
    "finance.payment": _HELD_PAYMENT,
    "finance.paymentauditlog": _NOT_YET,
    "finance.paymentdispute": _NOT_YET,
    "finance.paymentgatewayhealthsnapshot": _NOT_YET,
    "finance.paymentmethod": _NOT_YET,
    "finance.paymentplan": _NOT_YET,
    "finance.paymentproofupload": _HELD_PAYMENTPROOFUPLOAD,
    "finance.paymentrail": _NOT_YET,
    "finance.paymentreconciliation": _NOT_YET,
    "finance.paymentreminder": _NOT_YET,
    "finance.paymentreminderlog": _NOT_YET,
    "finance.recurringpaymentsubscription": _NOT_YET,
    "finance.referralreward": _NOT_YET,
    "finance.refundrequest": _NOT_YET,
    "finance.regionpaymentprofile": _NOT_YET,
    "finance.reportrequest": _NOT_YET,
    "finance.scholarship": _NOT_YET,
    "finance.suspensepayment": _NOT_YET,
    "finance.suspensepaymentallocation": _NOT_YET,
    "finance.taxbracket": _NOT_YET,
    "finance.tenantpaymentpolicy": _NOT_YET,
    "finance.transaction": _NOT_YET,
    "finance.wallettransaction": _NOT_YET,
    "finance.webhooklog": _NOT_YET,

    # -- evals: 10 model(s). On the rail (1): Evaluation.
    "evals.assessmentweights": _NOT_YET,
    "evals.evaluationevidence": _NOT_YET,
    "evals.gradeapprovalrequest": _NOT_YET,
    "evals.gradeaudit": _NOT_YET,
    "evals.gradingscale": _NOT_YET,
    "evals.gradingscaleband": _NOT_YET,
    "evals.mockexamsetting": _NOT_YET,
    "evals.offlinemarkentry": _NOT_YET,
    "evals.teacherassignment": _NOT_YET,

    # -- reports: 11 model(s). On the rail (0): none.
    "reports.adhocreportdefinition": _NOT_YET,
    "reports.adhocreportexecution": _NOT_YET,
    "reports.emissubmission": _NOT_YET,
    "reports.promotionrule": _NOT_YET,
    "reports.reportcard": _NOT_YET,
    "reports.reportcardaudit": _NOT_YET,
    "reports.reportcardbatch": _NOT_YET,
    "reports.reportdocumenthash": _NOT_YET,
    "reports.reportpack": _NOT_YET,
    "reports.tenantreportschedule": _NOT_YET,
    "reports.termpublishstatus": _NOT_YET,

    # -- communication: 30 model(s). On the rail (0): none.
    "communication.achievementevent": _NOT_YET,
    "communication.alertrule": _NOT_YET,
    "communication.announcement": _NOT_YET,
    "communication.announcementauditlog": _NOT_YET,
    "communication.breakoutroom": _NOT_YET,
    "communication.classannouncement": _NOT_YET,
    "communication.communicationtemplate": _NOT_YET,
    "communication.consentevent": _NOT_YET,
    "communication.contactrequest": _NOT_YET,
    "communication.contactrequestattachment": _NOT_YET,
    "communication.directconversation": _NOT_YET,
    "communication.feeditem": _NOT_YET,
    "communication.message": _NOT_YET,
    "communication.messageattachment": _NOT_YET,
    "communication.messageblock": _NOT_YET,
    "communication.messagedeliveryreceipt": _NOT_YET,
    "communication.messagethread": _NOT_YET,
    "communication.narrativefeedback": _NOT_YET,
    "communication.notificationpreference": _NOT_YET,
    "communication.outboundmessagequeue": _NOT_YET,
    "communication.sessionparticipant": _NOT_YET,
    "communication.sessionrecording": _NOT_YET,
    "communication.smssendlog": _NOT_YET,
    "communication.threadmessage": _NOT_YET,
    "communication.threadmessageattachment": _NOT_YET,
    "communication.threadmessagemention": _NOT_YET,
    "communication.threadmute": _NOT_YET,
    "communication.threadreadstate": _NOT_YET,
    "communication.virtualclassroom": _NOT_YET,
    "communication.webpushsubscription": _NOT_YET,

    # -- feedback: 14 model(s). On the rail (0): none.
    "feedback.featurerequest": _NOT_YET,
    "feedback.feedbackattachment": _NOT_YET,
    "feedback.feedbackcomment": _NOT_YET,
    "feedback.feedbacksubmission": _NOT_YET,
    "feedback.feedbacktriageevent": _NOT_YET,
    "feedback.feedbackvote": _NOT_YET,
    "feedback.helpcontentgaptask": _NOT_YET,
    "feedback.helpsearchquerylog": _NOT_YET,
    "feedback.releasenote": _NOT_YET,
    "feedback.roadmapitem": _NOT_YET,
    "feedback.supportaiinteractionreview": _NOT_YET,
    "feedback.supportaisessionrating": _NOT_YET,
    "feedback.supportdeflectionevent": _NOT_YET,
    "feedback.surveyresponse": _NOT_YET,

    # -- analytics: 21 model(s). On the rail (0): none.
    "analytics.atriskinferencerun": _NOT_YET,
    "analytics.atriskmodelartifact": _NOT_YET,
    "analytics.atriskoutcomelabel": _NOT_YET,
    "analytics.atriskshadowcomparison": _NOT_YET,
    "analytics.atriskshadowrun": _NOT_YET,
    "analytics.attendancelog": _NOT_YET,
    "analytics.benchmarkaggregate": _NOT_YET,
    "analytics.governedsavedreport": _NOT_YET,
    "analytics.gradeimportjob": _NOT_YET,
    "analytics.gradeprediction": _NOT_YET,
    "analytics.gradepredictionlabel": _NOT_YET,
    "analytics.gradepredictionmodelartifact": _NOT_YET,
    "analytics.gradepredictionshadowcomparison": _NOT_YET,
    "analytics.gradepredictionshadowrun": _NOT_YET,
    "analytics.interventionlog": _NOT_YET,
    "analytics.mlmodel": _NOT_YET,
    "analytics.riskdigestrecipient": _NOT_YET,
    "analytics.riskfactor": _NOT_YET,
    "analytics.riskthresholds": _NOT_YET,
    "analytics.studentatrisksignal": _NOT_YET,
    "analytics.studentsignals": _NOT_YET,

    # -- payroll: 11 model(s). On the rail (0): none.
    "payroll.employmentcontract": _NOT_YET,
    "payroll.leaverequest": _NOT_YET,
    "payroll.payrollemployee": _NOT_YET,
    "payroll.payrollofflinecapturerecord": _NOT_YET,
    "payroll.payrollrun": _NOT_YET,
    "payroll.payrollrunapproval": _NOT_YET,
    "payroll.payscale": _NOT_YET,
    "payroll.payslip": _NOT_YET,
    "payroll.payslipline": _NOT_YET,
    "payroll.salaryadjustment": _NOT_YET,
    "payroll.timeentry": _NOT_YET,

    # -- school_events: 6 model(s). On the rail (0): none.
    "school_events.eventregistration": _NOT_YET,
    "school_events.eventsponsor": _NOT_YET,
    "school_events.eventsponsorcommitment": _NOT_YET,
    "school_events.eventtickettier": _NOT_YET,
    "school_events.eventvenue": _NOT_YET,
    "school_events.schoolevent": _NOT_YET,

    # -- student360: 1 model(s). On the rail (0): none.
    "student360.immutabletranscript": _NOT_YET,

    # -- athletics: 16 model(s). On the rail (0): none.
    "athletics.club": _NOT_YET,
    "athletics.clubadvisorassignment": _NOT_YET,
    "athletics.clubmembership": _NOT_YET,
    "athletics.coachassignment": _NOT_YET,
    "athletics.eligibilityrecord": _NOT_YET,
    "athletics.fixture": _NOT_YET,
    "athletics.fixtureresult": _NOT_YET,
    "athletics.fixturetravel": _NOT_YET,
    "athletics.fixturevenuebooking": _NOT_YET,
    "athletics.medicalclearance": _NOT_YET,
    "athletics.participationconsent": _NOT_YET,
    "athletics.season": _NOT_YET,
    "athletics.sport": _NOT_YET,
    "athletics.team": _NOT_YET,
    "athletics.teamkitfee": _NOT_YET,
    "athletics.teammembership": _NOT_YET,

    # -- studio_os: 1 model(s). On the rail (0): none.
    "studio_os.experienceregionapproval": _NOT_YET,
}


# ---------------------------------------------------------------------------
# Live inputs. Both sides of the comparison are MEASURED, never transcribed.
# ---------------------------------------------------------------------------


def _app_label(dotted: str) -> str:
    """'apps.feedback.apps.FeedbackConfig' -> 'feedback'; 'apps.finance' -> 'finance'."""
    parts = [p for p in dotted.split(".") if p]
    if not parts:
        return ""
    if parts[0] == "apps" and len(parts) >= 2:
        return parts[1]
    return parts[0]


def _tenant_apps_from_settings_source(path: Path | None = None) -> list[str]:
    """The ``TENANT_APPS`` literal, read from ``config/settings.py`` by AST.

    Read from the SOURCE, not from ``django.conf.settings``, because
    ``TENANT_APPS`` is only *assigned* inside the ``USE_DJANGO_TENANTS`` branch --
    on a dev machine or an RLS-mode deployment the setting does not exist at all
    (verified: ``hasattr(settings, "TENANT_APPS")`` is False under the default
    ``config.settings``). An auditor that read the attribute would report zero
    tenant models on exactly the machine a developer runs it on, which is the
    "a scan reporting 0 problems was broken" failure mode. This is also the
    approach ``scripts/scan_cross_tenancy_fk.py`` already takes.
    """
    source = path or SETTINGS_PATH
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "TENANT_APPS":
                value = node.value
                if isinstance(value, (ast.List, ast.Tuple)):
                    for elt in value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            found.append(elt.value)
    return found


def tenant_app_labels(path: Path | None = None) -> list[str]:
    """App labels for every entry in ``TENANT_APPS``, in declaration order."""
    labels: list[str] = []
    for dotted in _tenant_apps_from_settings_source(path):
        label = _app_label(dotted)
        if label and label not in labels:
            labels.append(label)
    return labels


_MIGRATION_STATE_CACHE: dict | None = None


def _migration_state_models() -> dict[str, str]:
    """``{app_label.modelname: app_label}`` from MIGRATION STATE, cached.

    Built from the migration files on disk, never from a database connection.
    """
    global _MIGRATION_STATE_CACHE
    if _MIGRATION_STATE_CACHE is None:
        from django.db.migrations.loader import MigrationLoader

        state = MigrationLoader(None, ignore_no_migrations=True).project_state()
        out: dict[str, str] = {}
        for (app_label, model_name), model_state in state.models.items():
            options = model_state.options
            # Proxies have no table of their own; unmanaged models are not ours
            # to replicate. Neither can be an independent rail entity.
            if options.get("proxy") or options.get("managed") is False:
                continue
            out[f"{app_label}.{model_name}"] = app_label
        _MIGRATION_STATE_CACHE = out
    return dict(_MIGRATION_STATE_CACHE)


def tenant_models() -> dict[str, str]:
    """``{app_label.modelname: app_label}`` for every model in every TENANT_APP.

    Derived from **migration state**, not from the runtime app registry, because
    the registry is not import-order-proof and this cost a real defect:

    ``apps/portal/models_forums.py`` defines three MIGRATED tenant models
    (``CommunityForumCategory`` / ``Topic`` / ``Reply``, tables created by
    ``portal/migrations/0038_community_forums_1357.py``) but is imported LAZILY,
    by ``views_forums.py`` rather than by ``portal/models.py``. A plain
    ``django.setup()`` registry walk therefore returns 323 tenant models on a
    cold process and 326 once any test has touched a forum view -- so the first
    seeding of ``DECLARATIONS`` silently missed all three, and the gate reported
    a truthful-looking **0 undeclared** that was measured against an incomplete
    denominator. It only surfaced when the whole ``apps/sync_engine/tests/``
    directory ran in one process and six of these tests went red.

    This is a known trap in this repo, not a novel one:
    ``apps/schools/tests/test_rls_tenant_table_coverage.py`` derives its tenant
    table set "from MIGRATION STATE (not the runtime app registry) so it is
    import-order-proof -- it sees models defined in lazily-imported modules
    (``apps/portal/models_forums.py``...)". This function now does the same.

    Migration state is also the *right* filter in the other direction, and gets
    for free what the registry walk had to argue for: ``apps/evals/
    models_enhanced.py`` defines 12 classes that were never migrated, and they
    are absent here because no migration ever created their tables. (Force-
    importing every ``models*.py`` would be worse than either: that module
    raises ``RuntimeError: Conflicting 'evaluationevidence' models`` partway
    through, leaving three abandoned models half-registered.)
    """
    labels = set(tenant_app_labels())
    return {
        label: app_label
        for label, app_label in _migration_state_models().items()
        if app_label in labels
    }


def rail_entity_config() -> dict:
    """The live edge-rail registry: ``{entity_type: (model, fields)}``.

    Resolved by NAME against ``apps.api.sync_services`` so this module keeps
    working if the accessor is renamed or promoted to a public API -- the point
    of deriving is that nothing here is a copy.
    """
    from apps.api import sync_services

    for name in (
        "get_edge_entity_config",
        "edge_entity_config",
        "entity_config",
        "_get_entity_config",
    ):
        fn = getattr(sync_services, name, None)
        if not callable(fn):
            continue
        try:
            return fn(include_derived=True)
        except TypeError:
            return fn()
    raise RuntimeError(
        "rail_coverage: apps.api.sync_services exposes no entity-config accessor; "
        "the rail registry could not be derived, so any coverage number would be a guess."
    )


def rail_models() -> dict[str, str]:
    """``{model_label_lower: entity_type}`` for EVERY entity on the rail.

    Includes the rail's own config models in the shared ``sync_engine`` app; the
    report separates them, because they are not school data and counting them as
    business coverage would overstate it by two.
    """
    return {
        model._meta.label_lower: entity
        for entity, (model, _fields) in rail_entity_config().items()
    }


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


@dataclass
class AppCoverage:
    label: str
    total: int = 0
    rides: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    not_yet: list[str] = field(default_factory=list)
    undeclared: list[str] = field(default_factory=list)


@dataclass
class CoverageReport:
    apps: list[AppCoverage] = field(default_factory=list)
    violations: list[dict] = field(default_factory=list)
    rides_outside_tenant_apps: dict[str, str] = field(default_factory=dict)
    #: Models that now RIDE but still carry a leftover ``NOT_YET`` line. Reported
    #: as housekeeping, NOT as a violation: nobody claimed they should not ride,
    #: so there is no contradiction to resolve -- the derived answer simply
    #: supersedes a non-decision. (A leftover ``HELD`` IS a contradiction and is
    #: raised as ``held_but_riding``.) Kept non-fatal on purpose so that
    #: registering an entity is never blocked by a tidy-up in a second file.
    stale_not_yet_now_riding: list[str] = field(default_factory=list)

    @property
    def total_models(self) -> int:
        return sum(a.total for a in self.apps)

    @property
    def total_rides(self) -> int:
        return sum(len(a.rides) for a in self.apps)

    @property
    def total_held(self) -> int:
        return sum(len(a.held) for a in self.apps)

    @property
    def total_not_yet(self) -> int:
        return sum(len(a.not_yet) for a in self.apps)

    @property
    def total_undeclared(self) -> int:
        return sum(len(a.undeclared) for a in self.apps)

    @property
    def not_yet_labels(self) -> list[str]:
        out: list[str] = []
        for a in self.apps:
            out.extend(a.not_yet)
        return sorted(out)

    @property
    def coverage_pct(self) -> float:
        return (100.0 * self.total_rides / self.total_models) if self.total_models else 0.0

    def as_dict(self) -> dict:
        return {
            "total_models": self.total_models,
            "rides": self.total_rides,
            "held": self.total_held,
            "not_yet": self.total_not_yet,
            "undeclared": self.total_undeclared,
            "coverage_pct": round(self.coverage_pct, 2),
            "rides_outside_tenant_apps": dict(sorted(self.rides_outside_tenant_apps.items())),
            "stale_not_yet_now_riding": sorted(self.stale_not_yet_now_riding),
            "apps": [
                {
                    "app": a.label,
                    "total": a.total,
                    "rides": sorted(a.rides),
                    "held": sorted(a.held),
                    "not_yet": sorted(a.not_yet),
                    "undeclared": sorted(a.undeclared),
                }
                for a in self.apps
            ],
            "violations": self.violations,
        }


def _violation(kind: str, model: str, detail: str) -> dict:
    return {"kind": kind, "model": model, "detail": detail}


def evaluate(declarations: dict[str, Declaration] | None = None) -> CoverageReport:
    """Measure the rail against the live model registry and the declaration.

    Everything the report says about what RIDES comes from
    ``rail_entity_config()``; everything it says about what is HELD or NOT_YET
    comes from ``DECLARATIONS``. The violations are the places those two
    disagree, plus the places the declaration is not a decision.
    """
    decls = DECLARATIONS if declarations is None else declarations
    models = tenant_models()
    riding = rail_models()
    report = CoverageReport()

    # A declaration that names nothing real. Left unchecked, a typo'd key looks
    # like coverage for a model that then goes UNDECLARED under a different name
    # -- or worse, keeps "covering" a model somebody deleted.
    for label, decl in sorted(decls.items()):
        if label not in models:
            report.violations.append(
                _violation(
                    "unknown_model",
                    label,
                    "declared here but not a live model in any TENANT_APPS app "
                    "(renamed, deleted, moved to a shared app, or mistyped)",
                )
            )
        if decl.posture not in DECLARABLE_POSTURES:
            report.violations.append(
                _violation(
                    "invalid_posture",
                    label,
                    f"posture {decl.posture!r} is not declarable; use one of "
                    f"{list(DECLARABLE_POSTURES)}. RIDES is DERIVED from the live "
                    "registry and must never be asserted by hand.",
                )
            )
            continue
        if decl.posture == HELD:
            if not decl.rationale.strip():
                report.violations.append(
                    _violation(
                        "held_without_rationale",
                        label,
                        "HELD requires a written rationale; an unargued hold is a NOT_YET",
                    )
                )
            if not decl.argued_in.strip():
                report.violations.append(
                    _violation(
                        "held_without_pointer",
                        label,
                        "HELD requires `argued_in` pointing at where the decision is made "
                        "(a doc, a policy row, a test)",
                    )
                )
        elif decl.posture == NOT_YET:
            if decl.rationale.strip() or decl.argued_in.strip():
                report.violations.append(
                    _violation(
                        "not_yet_with_rationale",
                        label,
                        "NOT_YET means nobody has decided, so it carries no argument. "
                        "If there is one, the posture is HELD.",
                    )
                )

    for app_label in tenant_app_labels():
        coverage = AppCoverage(label=app_label)
        for model_label in sorted(models):
            if not model_label.startswith(app_label + "."):
                continue
            coverage.total += 1
            decl = decls.get(model_label)
            if model_label in riding:
                coverage.rides.append(model_label)
                # Declared HELD yet actually on the rail: somebody recorded
                # "this must not ride" and then wired it. That is the exact
                # drift this module exists to make impossible to do quietly.
                if decl is not None and decl.posture == HELD:
                    report.violations.append(
                        _violation(
                            "held_but_riding",
                            model_label,
                            f"declared HELD ({decl.argued_in or 'no pointer'}) but IS "
                            f"registered on the live rail as entity "
                            f"{riding[model_label]!r}; resolve the contradiction",
                        )
                    )
                elif decl is not None and decl.posture == NOT_YET:
                    report.stale_not_yet_now_riding.append(model_label)
                continue
            if decl is None:
                coverage.undeclared.append(model_label)
            elif decl.posture == HELD:
                coverage.held.append(model_label)
            else:
                coverage.not_yet.append(model_label)
        report.apps.append(coverage)

    for model_label in sorted(models):
        if model_label in decls or model_label in riding:
            continue
        # Already recorded per-app above; this loop only exists to raise the
        # UNDECLARED finding as a violation, which is what makes the gate bite.
        report.violations.append(
            _violation(
                "undeclared",
                model_label,
                "tenant model with no edge-rail posture; declare it HELD (with a "
                "rationale and a pointer) or NOT_YET in "
                "apps/sync_engine/rail_coverage.py::DECLARATIONS",
            )
        )

    tenant_labels = set(tenant_app_labels())
    report.rides_outside_tenant_apps = {
        label: entity
        for label, entity in sorted(riding.items())
        if label.split(".", 1)[0] not in tenant_labels
    }

    # The AST reading of TENANT_APPS must agree with the runtime setting wherever
    # the runtime actually has one. If they ever diverge, every number above is
    # measured against the wrong denominator, and silence would be the worst
    # possible answer.
    try:
        from django.conf import settings as _settings

        runtime = getattr(_settings, "TENANT_APPS", None)
        if runtime is not None:
            runtime_labels = []
            for dotted in runtime:
                lab = _app_label(str(dotted))
                if lab and lab not in runtime_labels:
                    runtime_labels.append(lab)
            if runtime_labels != tenant_app_labels():
                report.violations.append(
                    _violation(
                        "tenant_apps_drift",
                        "config.settings.TENANT_APPS",
                        f"source AST says {tenant_app_labels()} but the running settings "
                        f"say {runtime_labels}; the coverage denominator is unreliable",
                    )
                )
    except Exception:  # noqa: BLE001 - never let a settings quirk break the audit
        pass

    return report


def posture_of(model_label: str) -> str:
    """The posture of one model: RIDES (derived), HELD, NOT_YET, or UNDECLARED."""
    label = str(model_label or "").strip().lower()
    if label in rail_models():
        return RIDES
    decl = DECLARATIONS.get(label)
    return decl.posture if decl is not None else UNDECLARED


__all__ = [
    "AppCoverage",
    "CoverageReport",
    "DECLARABLE_POSTURES",
    "DECLARATIONS",
    "Declaration",
    "HELD",
    "NOT_YET",
    "RIDES",
    "UNDECLARED",
    "evaluate",
    "posture_of",
    "rail_entity_config",
    "rail_models",
    "tenant_app_labels",
    "tenant_models",
]
