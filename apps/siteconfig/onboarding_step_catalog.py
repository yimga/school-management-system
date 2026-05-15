"""Canonical onboarding step catalog — declarative SOT.

Like ``apps/communication/template_catalog.py``, this module is the
declarative inventory of every named onboarding step the platform can
present. The existing `_compute_data_driven_onboarding_steps` in the
platform-runtime module reads runtime state to *check* completion; this
catalog declares *what* should be checked.

Each step has:
  * ``key``: stable identifier
  * ``label``: human-readable name for the wizard UI
  * ``description``: longer help text
  * ``audience``: ``"any"`` / ``"admin"`` / ``"bursar"`` / ``"teacher_lead"``
  * ``required``: whether the step is mandatory to mark onboarding "complete"
  * ``estimated_minutes``: rough time-to-complete estimate
  * ``deep_link``: optional `reverse()`-able URL name for the wizard CTA
  * ``check_hint``: hint for the data-driven completion checker
    (e.g. "has-at-least-one-classroom", "has-bursar-role")

The platform-wide STEPS list is the universal default. Per-blueprint
overrides live in ``STEPS_BY_BLUEPRINT_PACK`` so each blueprint (e.g.
``primary-school``, ``ib-world-school``, ``cameroon-francophone``)
ships its own canonical step order.
"""

from __future__ import annotations


# === Universal step catalog (every step the platform can present) ===

ONBOARDING_STEPS: dict[str, dict] = {
    # Identity + branding
    "brand.identity": {
        "label": "Set school name, logo, and brand colors",
        "description": "Upload your school logo, set the primary brand color, and confirm display name.",
        "audience": "admin",
        "required": True,
        "estimated_minutes": 4,
        "deep_link": "siteconfig:theme_colors_page",
        "check_hint": "has-logo-and-primary-color",
    },
    "brand.contact_info": {
        "label": "Add school contact information",
        "description": "Office phone, email, physical address, and admissions hours.",
        "audience": "admin",
        "required": True,
        "estimated_minutes": 3,
        "check_hint": "has-contact-info",
    },
    "brand.domain": {
        "label": "Confirm tenant subdomain",
        "description": "Choose the subdomain that parents will use to log in.",
        "audience": "admin",
        "required": True,
        "estimated_minutes": 2,
        "check_hint": "has-subdomain",
    },

    # Calendar + terms
    "calendar.academic_year": {
        "label": "Create the academic year",
        "description": "Define start and end dates for the current academic year.",
        "audience": "admin",
        "required": True,
        "estimated_minutes": 3,
        "check_hint": "has-active-academic-year",
    },
    "calendar.terms": {
        "label": "Define terms / semesters",
        "description": "Set the boundaries for each term in the academic year.",
        "audience": "admin",
        "required": True,
        "estimated_minutes": 4,
        "check_hint": "has-at-least-one-term",
    },
    "calendar.holidays": {
        "label": "Add school holidays and breaks",
        "description": "Mark school-wide closures so attendance and timetables skip them.",
        "audience": "admin",
        "required": False,
        "estimated_minutes": 5,
        "check_hint": "has-holiday-entries",
    },

    # People + roles
    "people.admin_roles": {
        "label": "Invite school administrators",
        "description": "Send invitations to head teacher, principal, and IT admin accounts.",
        "audience": "admin",
        "required": True,
        "estimated_minutes": 5,
        "check_hint": "has-multiple-admin-users",
    },
    "people.teachers": {
        "label": "Invite teaching staff",
        "description": "Bulk-invite or import teachers via CSV.",
        "audience": "admin",
        "required": True,
        "estimated_minutes": 10,
        "check_hint": "has-at-least-one-teacher",
    },
    "people.bursar_role": {
        "label": "Assign a bursar / finance officer",
        "description": "At least one user with the bursar role is required to issue invoices.",
        "audience": "admin",
        "required": False,
        "estimated_minutes": 2,
        "check_hint": "has-bursar-role",
    },

    # Curriculum
    "curriculum.classrooms": {
        "label": "Create classrooms",
        "description": "Each cohort/class students will be enrolled into.",
        "audience": "admin",
        "required": True,
        "estimated_minutes": 6,
        "check_hint": "has-at-least-one-classroom",
    },
    "curriculum.subjects": {
        "label": "Add subjects / courses",
        "description": "Subjects, with passing scores and weights per term.",
        "audience": "admin",
        "required": True,
        "estimated_minutes": 8,
        "check_hint": "has-at-least-one-subject",
    },
    "curriculum.grading_scale": {
        "label": "Confirm grading scale",
        "description": "Letter, percentage, or band — based on your blueprint pack's default.",
        "audience": "admin",
        "required": True,
        "estimated_minutes": 3,
        "check_hint": "has-grading-scale-resolved",
    },
    "curriculum.timetable": {
        "label": "Build initial timetable",
        "description": "Class periods per classroom + teacher assignments.",
        "audience": "admin",
        "required": False,
        "estimated_minutes": 25,
        "check_hint": "has-at-least-one-timetable-period",
    },

    # Students + enrolment
    "students.import": {
        "label": "Import or add students",
        "description": "Migration Cloud upload (recommended) or one-by-one in the admin UI.",
        "audience": "admin",
        "required": True,
        "estimated_minutes": 15,
        "deep_link": "migration_cloud:bundle_list",
        "check_hint": "has-at-least-one-student",
    },
    "students.guardian_links": {
        "label": "Link guardians to students",
        "description": "Each student has at least one guardian record. Required for parent portal access.",
        "audience": "admin",
        "required": True,
        "estimated_minutes": 10,
        "check_hint": "has-guardian-links",
    },

    # Finance
    "finance.fee_schedule": {
        "label": "Define fee schedules",
        "description": "Tuition + applicable add-ons per grade level.",
        "audience": "bursar",
        "required": False,
        "estimated_minutes": 12,
        "check_hint": "has-fee-schedule",
    },
    "finance.payment_gateway": {
        "label": "Connect a payment gateway",
        "description": "Stripe Connect / Flutterwave / Paystack / Razorpay credentials.",
        "audience": "admin",
        "required": False,
        "estimated_minutes": 8,
        "check_hint": "has-active-payment-gateway",
    },
    "finance.currency": {
        "label": "Confirm currency",
        "description": "The currency invoices and receipts are issued in.",
        "audience": "bursar",
        "required": True,
        "estimated_minutes": 1,
        "check_hint": "has-currency-resolved",
    },

    # Communications
    "comms.email_sender": {
        "label": "Configure outbound email sender",
        "description": "Confirm SMTP / SES / SendGrid / Postmark + verified sender address.",
        "audience": "admin",
        "required": False,
        "estimated_minutes": 6,
        "check_hint": "has-email-sender-configured",
    },
    "comms.sms_gateway": {
        "label": "Connect SMS / WhatsApp gateway",
        "description": "Twilio / Africa's Talking / Termii credentials for parent SMS + WhatsApp.",
        "audience": "admin",
        "required": False,
        "estimated_minutes": 6,
        "check_hint": "has-sms-gateway-configured",
    },

    # Policy + compliance
    "policy.handbook": {
        "label": "Upload student handbook",
        "description": "PDF or markdown that becomes searchable in the AI policy explainer.",
        "audience": "admin",
        "required": False,
        "estimated_minutes": 5,
        "check_hint": "has-policy-doc-ingested",
    },
    "policy.consent_records": {
        "label": "Set up guardian consent topics",
        "description": "Topics requiring guardian consent (data sharing, photography, etc.).",
        "audience": "admin",
        "required": False,
        "estimated_minutes": 6,
        "check_hint": "has-consent-topics",
    },

    # AI
    "ai.policy_review": {
        "label": "Review AI privacy policy",
        "description": "Confirm AI features are enabled and whether external providers are allowed.",
        "audience": "admin",
        "required": False,
        "estimated_minutes": 3,
        "check_hint": "has-ai-policy-reviewed",
    },

    # Launch
    "launch.test_run": {
        "label": "Run a dry-run scenario",
        "description": "Issue a test invoice, send a test message, record a test attendance.",
        "audience": "admin",
        "required": False,
        "estimated_minutes": 10,
        "check_hint": "has-dry-run-completed",
    },
    "launch.invite_parents": {
        "label": "Send parent welcome emails",
        "description": "Trigger the first bulk welcome to invited guardians.",
        "audience": "admin",
        "required": False,
        "estimated_minutes": 4,
        "check_hint": "has-parent-welcome-sent",
    },
}


# === Per-blueprint canonical step order ===
#
# Each blueprint pack's slug maps to the *ordered* list of step keys
# that the wizard should display, in order. Steps not in this list are
# hidden for that institution type. The "default" key is the fallback
# when no blueprint is matched.

STEPS_BY_BLUEPRINT_PACK: dict[str, list[str]] = {
    "default": [
        "brand.identity", "brand.contact_info", "brand.domain",
        "calendar.academic_year", "calendar.terms",
        "people.admin_roles", "people.teachers",
        "curriculum.classrooms", "curriculum.subjects", "curriculum.grading_scale",
        "students.import", "students.guardian_links",
        "finance.currency",
        "launch.test_run",
    ],
    "early-learning": [
        "brand.identity", "brand.contact_info",
        "calendar.academic_year", "calendar.terms", "calendar.holidays",
        "people.admin_roles", "people.teachers",
        "curriculum.classrooms",
        "students.import", "students.guardian_links",
        "policy.consent_records",
        "comms.sms_gateway",
        "launch.test_run", "launch.invite_parents",
    ],
    "primary-school": [
        "brand.identity", "brand.contact_info", "brand.domain",
        "calendar.academic_year", "calendar.terms", "calendar.holidays",
        "people.admin_roles", "people.teachers", "people.bursar_role",
        "curriculum.classrooms", "curriculum.subjects", "curriculum.grading_scale",
        "students.import", "students.guardian_links",
        "finance.currency", "finance.fee_schedule",
        "comms.email_sender",
        "launch.test_run", "launch.invite_parents",
    ],
    "secondary-school": [
        "brand.identity", "brand.contact_info", "brand.domain",
        "calendar.academic_year", "calendar.terms", "calendar.holidays",
        "people.admin_roles", "people.teachers", "people.bursar_role",
        "curriculum.classrooms", "curriculum.subjects", "curriculum.grading_scale", "curriculum.timetable",
        "students.import", "students.guardian_links",
        "finance.currency", "finance.fee_schedule", "finance.payment_gateway",
        "comms.email_sender", "comms.sms_gateway",
        "policy.handbook",
        "launch.test_run", "launch.invite_parents",
    ],
    "international-school": [
        "brand.identity", "brand.contact_info", "brand.domain",
        "calendar.academic_year", "calendar.terms", "calendar.holidays",
        "people.admin_roles", "people.teachers", "people.bursar_role",
        "curriculum.classrooms", "curriculum.subjects", "curriculum.grading_scale", "curriculum.timetable",
        "students.import", "students.guardian_links",
        "finance.currency", "finance.fee_schedule", "finance.payment_gateway",
        "comms.email_sender", "comms.sms_gateway",
        "policy.handbook", "policy.consent_records",
        "ai.policy_review",
        "launch.test_run", "launch.invite_parents",
    ],
    "ib-world-school": [
        "brand.identity", "brand.contact_info", "brand.domain",
        "calendar.academic_year", "calendar.terms",
        "people.admin_roles", "people.teachers", "people.bursar_role",
        "curriculum.classrooms", "curriculum.subjects", "curriculum.grading_scale", "curriculum.timetable",
        "students.import", "students.guardian_links",
        "finance.currency", "finance.fee_schedule", "finance.payment_gateway",
        "comms.email_sender", "comms.sms_gateway",
        "policy.handbook", "policy.consent_records",
        "ai.policy_review",
        "launch.test_run",
    ],
    "tertiary-university": [
        "brand.identity", "brand.contact_info", "brand.domain",
        "calendar.academic_year", "calendar.terms",
        "people.admin_roles", "people.teachers", "people.bursar_role",
        "curriculum.classrooms", "curriculum.subjects", "curriculum.grading_scale", "curriculum.timetable",
        "students.import", "students.guardian_links",
        "finance.currency", "finance.fee_schedule", "finance.payment_gateway",
        "comms.email_sender",
        "policy.handbook", "policy.consent_records",
        "launch.test_run",
    ],
    "technical-vocational": [
        "brand.identity", "brand.contact_info",
        "calendar.academic_year", "calendar.terms",
        "people.admin_roles", "people.teachers", "people.bursar_role",
        "curriculum.classrooms", "curriculum.subjects", "curriculum.grading_scale",
        "students.import", "students.guardian_links",
        "finance.currency", "finance.fee_schedule",
        "comms.sms_gateway",
        "launch.test_run",
    ],
}


def list_step_keys() -> list[str]:
    return sorted(ONBOARDING_STEPS.keys())


def get_step(key: str) -> dict | None:
    return ONBOARDING_STEPS.get(key)


def steps_for_blueprint(slug: str | None) -> list[dict]:
    """Return ordered list of step dicts (with key) for a blueprint slug.

    Falls back to the universal ``default`` order if ``slug`` is None
    or not in the per-blueprint map.
    """
    key_list = STEPS_BY_BLUEPRINT_PACK.get(slug or "", STEPS_BY_BLUEPRINT_PACK["default"])
    out = []
    for k in key_list:
        body = ONBOARDING_STEPS.get(k)
        if not body:
            continue
        item = dict(body)
        item["key"] = k
        out.append(item)
    return out


def required_steps_for_blueprint(slug: str | None) -> list[str]:
    return [
        s["key"] for s in steps_for_blueprint(slug)
        if s.get("required", False)
    ]
