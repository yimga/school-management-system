"""Non-teaching staff roles, and the base staff identity that holds nothing.

A school runs on more than teachers -- drivers, security officers, librarians,
nurses, workshop technicians, storekeepers, cleaners, cooks, receptionists,
counsellors, coordinators. ``User.Role`` could name none of them, so a real
staff directory (Gilead Technical High School, 49 rows, 2026-09-04) had four
people the system could not represent at all:

    COORDINATOR, ADMINISTRATIVE ASSISTANT / IT, DRIVER, SECURITY

``staff_role_map`` correctly refused to collapse them onto TEACHER -- TEACHER is
not an inert token; the ``post_save`` in ``apps/accounts/signals.py`` attaches
the TEACHER AccessRole, whose seeded codes include ``attendance.manage`` and
``grades.enter``, so a bus driver would have become a school-wide attendance and
grade reader. But the refusal meant the PEOPLE did not exist: no user, no
membership, no profile, nothing to edit.

Both halves are fixed here. The roles now exist with permission sets that match
what each job actually does, and SUPPORT_STAFF is the base staff identity that
holds NO capability at all -- a real, editable person, granted nothing. That is
what an unreadable or blank role cell becomes now, in place of TEACHER.

Additive only: no existing Permission or AccessRole row is altered or removed,
and permissions are added rather than set, so a tenant's own edits to a role
survive a re-run.
"""

from django.db import migrations, models


# Domains that HAVE models in apps/schoolops but had no permission code, so no
# role could ever be granted them: Bus/Route/TransportAssignment, LibraryItem/
# LibraryLoan, HealthRecord/ImmunizationRecord, VisitorCheckIn,
# MaintenanceRequest, CanteenMeal/MealPlanBalance.
NEW_PERMISSIONS = [
    ("transport.view", "Transport view", "View routes, buses, and student transport assignments."),
    ("transport.manage", "Transport management", "Manage routes, buses, boarding events and assignments."),
    ("library.view", "Library view", "View library catalogue and loans."),
    ("library.manage", "Library management", "Manage library items, loans and returns."),
    ("health.view", "Health view", "View health records and immunisation status."),
    ("health.manage", "Health management", "Record clinic visits, immunisations and health notes."),
    ("visitors.view", "Visitor log view", "View the visitor and gate log."),
    ("visitors.manage", "Visitor log management", "Check visitors in and out; manage the gate log."),
    ("maintenance.view", "Maintenance view", "View maintenance and facility requests."),
    ("maintenance.manage", "Maintenance management", "Triage and close maintenance requests."),
    ("canteen.view", "Canteen view", "View meals, menus and meal-plan balances."),
    ("canteen.manage", "Canteen management", "Manage meals, menus and meal-plan balances."),
]

# Each role gets what the JOB needs and nothing adjacent to it. A driver sees
# transport; a driver does not see the library. Read-only where the job is
# read-only: COORDINATOR oversees a programme and needs to SEE attendance and
# reports, so it gets the .view codes and never attendance.manage.
NEW_ROLE_DEFINITIONS = {
    "SUPPORT_STAFF": {
        "name": "Support Staff",
        "description": (
            "Base staff identity. A real, editable member of staff who holds no "
            "capability. Assigned when a source document names a role this system "
            "cannot map, or names none at all, so the person exists and can be "
            "corrected by hand instead of being dropped or over-granted."
        ),
        "permissions": [],
    },
    "COORDINATOR": {
        "name": "Coordinator",
        "description": "Programme / specialty coordinator: oversees a cohort's attendance and results without editing them.",
        "permissions": ["attendance.view", "reports.view", "analytics.view"],
    },
    "LIBRARIAN": {
        "name": "Librarian",
        "description": "Runs the library: catalogue, loans, returns and stock of books and media.",
        "permissions": ["library.view", "library.manage", "stock.view"],
    },
    "NURSE": {
        "name": "School Nurse",
        "description": "Clinic and infirmary: health records, immunisation tracking, and who is absent sick.",
        "permissions": ["health.view", "health.manage", "attendance.view"],
    },
    "LAB_TECHNICIAN": {
        "name": "Laboratory / Workshop Technician",
        "description": "Prepares and maintains laboratory and technical-workshop equipment and consumables.",
        "permissions": ["stock.view", "stock.manage", "maintenance.view"],
    },
    "STOREKEEPER": {
        "name": "Storekeeper",
        "description": "Custody of stores and inventory: receipts, issues and stock counts.",
        "permissions": ["stock.view", "stock.manage"],
    },
    "DRIVER": {
        "name": "Driver",
        "description": "Drives a school vehicle on assigned routes. Sees the routes and rosters, changes nothing.",
        "permissions": ["transport.view"],
    },
    "SECURITY": {
        "name": "Security Officer",
        "description": "Gate and campus security: visitor check-in and the gate log.",
        "permissions": ["visitors.view", "visitors.manage"],
    },
    "MAINTENANCE": {
        "name": "Maintenance Officer",
        "description": "Buildings, grounds and facility repairs; triages and closes maintenance requests.",
        "permissions": ["maintenance.view", "maintenance.manage"],
    },
    "CATERING_STAFF": {
        "name": "Catering Staff",
        "description": "Canteen and kitchen: meals, menus, meal-plan balances and kitchen stock.",
        "permissions": ["canteen.view", "canteen.manage", "stock.view"],
    },
    "RECEPTIONIST": {
        "name": "Receptionist",
        "description": "Front desk: greets and logs visitors, directs enquiries.",
        "permissions": ["visitors.view", "visitors.manage"],
    },
    "COUNSELOR": {
        "name": "Guidance Counsellor",
        "description": "Pastoral care and guidance: may refer a discipline concern, and sees attendance and reports.",
        "permissions": ["discipline.refer", "attendance.view", "reports.view"],
    },
}


def seed_support_staff_roles(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")

    perm_map = {p.code: p for p in Permission.objects.all()}
    for code, name, description in NEW_PERMISSIONS:
        if code not in perm_map:
            perm_map[code] = Permission.objects.create(
                code=code, name=name, description=description
            )

    for code, data in NEW_ROLE_DEFINITIONS.items():
        # school=None: these are platform-wide TEMPLATE roles, which is what
        # _apply_role_template binds to (it filters school__isnull=True, and
        # attaching a tenant-scoped row there was itself a cross-tenant bug).
        role, _created = AccessRole.objects.get_or_create(
            code=code,
            school=None,
            defaults={"name": data["name"], "description": data["description"]},
        )
        perms = [perm_map[p] for p in data["permissions"] if p in perm_map]
        if perms:
            # add(), not set(): additive so a tenant's own grant on a re-run is
            # never silently withdrawn. SUPPORT_STAFF has an empty list and so
            # is left holding nothing, which is the whole point of it.
            role.permissions.add(*perms)


def noop(apps, schema_editor):
    """No reverse. Removing a role would orphan every account holding it."""


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0064_rls_force_and_null_arm_postgresql'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(choices=[('SUPERADMIN', 'Super Administrator'), ('ADMIN', 'Administrator'), ('LEADERSHIP', 'Leadership'), ('PRINCIPAL', 'Principal'), ('VICE_PRINCIPAL', 'Vice Principal'), ('DEAN', 'Dean'), ('CENSOR', 'Censor'), ('BURSAR', 'Bursar'), ('HOD', 'Head of Department'), ('DEPT_LEAD', 'Department Lead'), ('FINANCE_STAFF', 'Finance Staff'), ('ACADEMICS_STAFF', 'Academics Staff'), ('COMMS_STAFF', 'Communications Staff'), ('SECRETARY', 'Secretary'), ('EXECUTIVE_ASSISTANT', 'Executive Assistant'), ('VIRTUAL_ASSISTANT', 'Virtual Assistant'), ('TEACHER', 'Teacher'), ('IT_ADMIN', 'IT Administrator'), ('DPO', 'Data Protection Officer'), ('BOARDING_MANAGER', 'Boarding Manager'), ('ACCOUNTANT', 'Accountant'), ('PROPRIETOR', 'Proprietor'), ('DISCIPLINE_MASTER', 'Discipline Master'), ('SUPPORT_STAFF', 'Support Staff'), ('COORDINATOR', 'Coordinator'), ('LIBRARIAN', 'Librarian'), ('NURSE', 'School Nurse'), ('LAB_TECHNICIAN', 'Laboratory / Workshop Technician'), ('STOREKEEPER', 'Storekeeper'), ('DRIVER', 'Driver'), ('SECURITY', 'Security Officer'), ('MAINTENANCE', 'Maintenance Officer'), ('CATERING_STAFF', 'Catering Staff'), ('RECEPTIONIST', 'Receptionist'), ('COUNSELOR', 'Guidance Counsellor'), ('PARENT', 'Parent'), ('STUDENT', 'Student'), ('EMPLOYER', 'Employer (apprentice portal)')], default='PARENT', max_length=20),
        ),
        migrations.RunPython(seed_support_staff_roles, noop),
    ]
